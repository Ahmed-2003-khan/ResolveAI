"""Hybrid retrieval: dense (pgvector cosine) + BM25 (tsvector) fused with RRF, then reranked."""

from __future__ import annotations

import re
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

# Coarse cosine-distance cutoff for dense candidates. text-embedding-3-small
# puts clearly off-topic chunks above ~0.72; we keep everything below this and
# let the cross-encoder reranker do the fine-grained ordering. Tuned to be
# lenient on purpose — the reranker, not this cutoff, separates near-ties.
_MAX_COSINE_DISTANCE = 0.72

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _build_or_tsquery(query: str) -> str:
    """Turn a free-text query into an OR-joined to_tsquery string.

    plainto_tsquery ANDs every term, so a mixed Roman-Urdu/English query like
    "mera order ORD-001 kahan hai" matches nothing in an English corpus. We
    OR the lexemes instead so any single overlapping term (e.g. "order") can
    match, then rely on ts_rank + the reranker for ordering.
    """
    tokens = [t.lower() for t in _TOKEN_RE.findall(query) if len(t) > 1]
    # Dedupe while preserving order.
    seen: set[str] = set()
    unique = [t for t in tokens if not (t in seen or seen.add(t))]
    return " | ".join(unique)


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

        # asyncpg cannot infer the type of a bare NULL parameter in a comparison.
        # Build WHERE fragments dynamically to avoid the ambiguous-parameter error.
        area_filter = "AND product_area = :product_area" if product_area else ""

        # Dense: drop clearly off-topic chunks via a coarse distance cutoff.
        dense_sql = text(
            f"""
            SELECT id, source_id, source_type, title, content, product_area
            FROM kb_chunks
            WHERE (embedding <=> CAST(:vec AS vector)) < :max_dist {area_filter}
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :limit
            """
        )

        # BM25: OR the lexemes against the language-agnostic `simple` tsvector
        # so Roman-Urdu terms survive (no English stemming / stopword removal).
        or_query = _build_or_tsquery(query)
        bm25_sql = text(
            f"""
            SELECT id, source_id, source_type, title, content, product_area
            FROM kb_chunks
            WHERE content_tsv_simple @@ to_tsquery('simple', :tsq)
              {area_filter}
            ORDER BY ts_rank(content_tsv_simple, to_tsquery('simple', :tsq)) DESC
            LIMIT :limit
            """
        )

        dense_params: dict = {
            "vec": vec_str,
            "limit": _DENSE_CANDIDATES,
            "max_dist": _MAX_COSINE_DISTANCE,
        }
        bm25_params: dict = {"tsq": or_query, "limit": _BM25_CANDIDATES}
        if product_area:
            dense_params["product_area"] = product_area
            bm25_params["product_area"] = product_area

        async with async_session_factory() as session:
            dense_rows = (
                await session.execute(dense_sql, dense_params)
            ).mappings().all()

            # An empty token set produces an invalid tsquery — skip BM25 then.
            if or_query:
                bm25_rows = (
                    await session.execute(bm25_sql, bm25_params)
                ).mappings().all()
            else:
                bm25_rows = []

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
