"""Semantic cache backed by pgvector cosine similarity.

Workflow:
  1. On agent entry – embed the user message, look for an unexpired row with
     cosine similarity >= threshold (configurable, default 0.97).
  2. Cache hit  → return the stored response immediately; no graph run needed.
  3. Cache miss → run the graph, then store the final response for future hits.
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import structlog
from sqlalchemy import text

from app.config import get_settings
from app.core.db import async_session_factory
from app.services.rag.embedder import get_embedder

log = structlog.get_logger(__name__)


class SemanticCacheService:
    """Check and populate the semantic_cache table using pgvector cosine distance."""

    def __init__(self) -> None:
        settings = get_settings()
        self._threshold = settings.semantic_cache_similarity_threshold
        self._ttl_hours = settings.semantic_cache_ttl_hours

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(query: str) -> str:
        """NFKC-normalise, lowercase, collapse internal whitespace."""
        q = unicodedata.normalize("NFKC", query).lower().strip()
        return " ".join(q.split())

    @staticmethod
    def _vec_str(embedding: list[float]) -> str:
        return "[" + ",".join(str(v) for v in embedding) + "]"

    # ── Public API ────────────────────────────────────────────────────────────

    async def get(self, query: str) -> str | None:
        """Return a cached response if a sufficiently similar query was seen before.

        Returns ``None`` on miss or any DB / embedding error.
        """
        normalized = self._normalize(query)
        if not normalized:
            return None

        try:
            embedder = get_embedder()
            q_vec = await embedder.embed_one(normalized)
        except Exception as exc:
            log.warning("cache_embed_failed", error=str(exc))
            return None

        # pgvector cosine *distance* = 1 − similarity; hit when dist <= (1 − threshold)
        dist_threshold = 1.0 - self._threshold
        vec_str = self._vec_str(q_vec)

        sql = text("""
            SELECT id, response, (query_embedding <=> CAST(:vec AS vector)) AS distance
            FROM semantic_cache
            WHERE expires_at > now()
              AND (query_embedding <=> CAST(:vec AS vector)) <= :dist_thresh
            ORDER BY distance
            LIMIT 1
            """)
        try:
            async with async_session_factory() as session:
                row = (
                    (await session.execute(sql, {"vec": vec_str, "dist_thresh": dist_threshold}))
                    .mappings()
                    .first()
                )

                if row is None:
                    return None

                update_sql = text(
                    "UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = :id"
                )
                await session.execute(update_sql, {"id": row["id"]})
                await session.commit()

            log.info("semantic_cache_hit", distance=float(row["distance"]))
            return str(row["response"])
        except Exception as exc:
            log.warning("cache_get_failed", error=str(exc))
            return None

    async def set(self, query: str, response: str) -> None:
        """Insert a new entry into the cache.  Silently ignores errors."""
        normalized = self._normalize(query)
        if not normalized or not response:
            return

        try:
            embedder = get_embedder()
            q_vec = await embedder.embed_one(normalized)
        except Exception as exc:
            log.warning("cache_embed_failed_on_set", error=str(exc))
            return

        vec_str = self._vec_str(q_vec)
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=self._ttl_hours)

        sql = text("""
            INSERT INTO semantic_cache
                (id, query_normalized, query_embedding, response, created_at, expires_at)
            VALUES
                (gen_random_uuid(), :query, CAST(:vec AS vector), :response, :created_at, :expires_at)
            """)
        try:
            async with async_session_factory() as session:
                await session.execute(
                    sql,
                    {
                        "query": normalized,
                        "vec": vec_str,
                        "response": response,
                        "created_at": now,
                        "expires_at": expires_at,
                    },
                )
                await session.commit()
            log.info("semantic_cache_set", ttl_hours=self._ttl_hours)
        except Exception as exc:
            log.warning("cache_set_failed", error=str(exc))


@lru_cache(maxsize=1)
def get_semantic_cache() -> SemanticCacheService:
    return SemanticCacheService()
