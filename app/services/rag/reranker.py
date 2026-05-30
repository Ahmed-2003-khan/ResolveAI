"""BGE reranker — singleton CrossEncoder that runs in a thread-pool to avoid blocking."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import structlog

log = structlog.get_logger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reranker")


class Reranker:
    """Wraps a CrossEncoder reranker with a lazy load and async interface.

    Default model is cross-encoder/ms-marco-MiniLM-L-6-v2 (~85 MB) which
    runs comfortably on 8 GB machines. Swap to BAAI/bge-reranker-v2-m3 on
    servers with 16 GB+ RAM for higher quality.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        self._model_name = model_name
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            log.info("reranker_loading", model=self._model_name)
            self._model = CrossEncoder(self._model_name)
            log.info("reranker_loaded", model=self._model_name)
        except Exception as exc:
            log.error("reranker_load_failed", model=self._model_name, error=str(exc))
            raise

    def _rerank_sync(self, query: str, docs: list[dict], k: int) -> list[dict]:
        self._load()
        if not docs:
            return []
        pairs = [(query, doc.get("content", "")) for doc in docs]
        scores = self._model.predict(pairs)
        ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        return [doc for _, doc in ranked[:k]]

    async def rerank(self, query: str, docs: list[dict], k: int = 5) -> list[dict]:
        """Rerank docs asynchronously by running the CrossEncoder in a thread."""
        if not docs:
            return []
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                _executor, self._rerank_sync, query, docs, k
            )
        except Exception as exc:
            log.warning("reranker_failed_fallback", error=str(exc))
            return docs[:k]


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    import os
    model = os.environ.get("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    return Reranker(model_name=model)
