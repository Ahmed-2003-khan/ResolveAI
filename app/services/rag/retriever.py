"""Hybrid retrieval: dense (pgvector cosine) + BM25 (tsvector) fused with RRF, then reranked."""

from __future__ import annotations

from functools import lru_cache

import structlog
from sqlalchemy import text

from app.core.db import async_session_factory
from app.services.rag.embedder import get_embedder
from app.services.rag.reranker import get_reranker

log = structlog.get_logger(__name__)

_DENSE_CANDIDATES = 30
_BM25_CANDIDATES = 30
_RRF_K = 60
_PRE_RERANK = 20


def _reciprocal_rank_fusion(
    dense: list[dict], bm25: list[dict], k: int = _RRF_K
) -> list[dict]:
    """Merge two ranked lists using Reciprocal Rank Fusion."""
    scores: dict[str, dict] = {}
    for rank, doc in enumerate(dense):
        doc_id = str(doc["id"])
        if doc_id not in scores:
            scores[doc_id] = {"score": 0.0, "doc": doc}
        scores[doc_id]["score"] += 1.0 / (k + rank + 1)
    for rank, doc in enumerate(bm25):
        doc_id = str(doc["id"])
        if doc_id not in scores:
            scores[doc_id] = {"score": 0.0, "doc": doc}
        scores[doc_id]["score"] += 1.0 / (k + rank + 1)
    return [v["doc"] for v in sorted(scores.values(), key=lambda x: x["score"], reverse=True)]


class Retriever:
    """Hybrid dense + BM25 retriever with RRF fusion and BGE reranking."""

    async def retrieve(
        self, query: str, filters: dict | None = None, k: int = 5
    ) -> list[dict]:
        """Return the top-k most relevant chunks for *query*.

        Returns an empty list on any error so callers are never blocked by
        retrieval failures.
        """
        if not query.strip():
            return []

        try:
            embedder = get_embedder()
            q_vec = await embedder.embed_one(query)
        except Exception as exc:
            log.warning("retriever_embed_failed", error=str(exc))
            return []

        try:
            dense, bm25 = await self._query_db(query, q_vec, filters)
        except Exception as exc:
            log.warning("retriever_db_failed", error=str(exc))
            return []

        merged = _reciprocal_rank_fusion(dense, bm25)[:_PRE_RERANK]

        try:
            reranker = get_reranker()
            return await reranker.rerank(query, merged, k=k)
        except Exception as exc:
            log.warning("retriever_rerank_failed", error=str(exc))
            return merged[:k]

    async def _query_db(
        self, query: str, q_vec: list[float], filters: dict | None
    ) -> tuple[list[dict], list[dict]]:
        product_area = (filters or {}).get("product_area")
        vec_str = "[" + ",".join(str(v) for v in q_vec) + "]"

        dense_sql = text(
            """
            SELECT id, source_id, source_type, title, content, product_area
            FROM kb_chunks
            WHERE (:product_area IS NULL OR product_area = :product_area)
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :limit
            """
        )
        bm25_sql = text(
            """
            SELECT id, source_id, source_type, title, content, product_area
            FROM kb_chunks
            WHERE content_tsv @@ plainto_tsquery('english', :query)
              AND (:product_area IS NULL OR product_area = :product_area)
            ORDER BY ts_rank(content_tsv, plainto_tsquery('english', :query)) DESC
            LIMIT :limit
            """
        )

        async with async_session_factory() as session:
            dense_rows = (
                await session.execute(
                    dense_sql,
                    {"vec": vec_str, "product_area": product_area, "limit": _DENSE_CANDIDATES},
                )
            ).mappings().all()

            bm25_rows = (
                await session.execute(
                    bm25_sql,
                    {"query": query, "product_area": product_area, "limit": _BM25_CANDIDATES},
                )
            ).mappings().all()

        def _row_to_dict(row) -> dict:
            return {
                "id": str(row["id"]),
                "source_id": row["source_id"],
                "source_type": row["source_type"],
                "title": row.get("title") or "",
                "content": row["content"],
                "product_area": row.get("product_area") or "",
            }

        return [_row_to_dict(r) for r in dense_rows], [_row_to_dict(r) for r in bm25_rows]


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever()
