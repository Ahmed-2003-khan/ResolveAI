from __future__ import annotations

from functools import lru_cache

import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = structlog.get_logger(__name__)

_BATCH_SIZE = 100


class Embedder:
    """OpenAI text-embedding-3-small wrapper with batching and retry."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _embed_batch_raw(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(input=texts, model=self._model)
        # API returns items in order but be explicit
        ordered = sorted(resp.data, key=lambda x: x.index)
        return [item.embedding for item in ordered]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, splitting into batches of _BATCH_SIZE."""
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        for offset in range(0, len(texts), _BATCH_SIZE):
            batch = texts[offset : offset + _BATCH_SIZE]
            logger.info("embedding_batch", offset=offset, size=len(batch), total=len(texts))
            embeddings = await self._embed_batch_raw(batch)
            all_embeddings.extend(embeddings)
        return all_embeddings

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
