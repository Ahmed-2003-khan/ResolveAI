"""Ingest knowledge-base seed data into PostgreSQL kb_chunks table.

Usage:
    python scripts/ingest_kb.py

Reads:
    data/seed/kb_articles.jsonl
    data/seed/synthetic_tickets.jsonl

Each record is chunked, embedded (OpenAI text-embedding-3-small), and
inserted into the kb_chunks table with a tsvector computed server-side.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path

import structlog
from sqlalchemy import text

from app.core.db import async_session_factory
from app.models.kb_chunk import KBChunk
from app.services.rag.chunker import chunk_document
from app.services.rag.embedder import get_embedder

logger = structlog.get_logger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "seed"
BATCH_SIZE = 50  # DB insert batch

# Matches the synthetic "[ref #123]" markers that make otherwise-identical
# tickets look unique.
_REF_RE = re.compile(r"\[ref\s*#?\d+\]", re.IGNORECASE)
_NONWORD_RE = re.compile(r"[^a-z\s]+")


def _dedup_key(content: str) -> str:
    """Normalize a chunk so near-identical tickets collapse to one key.

    Strips [ref #N] markers, digits, and punctuation, then lowercases and
    collapses whitespace. This catches the bulk-generated tickets that differ
    only by a reference number or ID — they pollute the vector space and bias
    retrieval toward whichever boilerplate was generated most often.
    """
    text_ = _REF_RE.sub("", content.lower())
    text_ = _NONWORD_RE.sub(" ", text_)
    return " ".join(text_.split())


def _dedup_rows(rows: list[dict]) -> list[dict]:
    """Keep the first row for each normalized content key."""
    seen: set[str] = set()
    kept: list[dict] = []
    for row in rows:
        key = _dedup_key(row["content"])
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _build_rows(records: list[dict]) -> list[dict]:
    """Return flat list of raw dicts ready for bulk insert (no embeddings yet)."""
    rows: list[dict] = []
    for rec in records:
        source_type = rec.get("source_type", "ticket")
        content_field = rec.get("content", "")
        question = rec.get("question")
        answer = rec.get("answer")

        chunks = chunk_document(
            content_field,
            source_type,
            question=question,
            answer=answer,
        )
        for chunk in chunks:
            rows.append(
                {
                    "_id": str(rec.get("id", uuid.uuid4())),
                    "source_id": str(rec.get("id", uuid.uuid4())),
                    "source_type": source_type,
                    "title": rec.get("title"),
                    "content": chunk.content,
                    "language": rec.get("language", "en"),
                    "product_area": rec.get("product_area"),
                    "confidentiality": rec.get("confidentiality", "public"),
                    "metadata_": {
                        "chunk_index": chunk.chunk_index,
                        "total_chunks": chunk.total_chunks,
                    },
                }
            )
    return rows


async def _insert_batch(session, rows: list[dict], embeddings: list[list[float]]) -> None:
    for row, emb in zip(rows, embeddings, strict=False):
        chunk_id = uuid.uuid4()
        tsv = await session.scalar(
            text("SELECT to_tsvector('english', :t)"),
            {"t": row["content"]},
        )
        chunk = KBChunk(
            id=chunk_id,
            source_id=row["source_id"],
            source_type=row["source_type"],
            title=row["title"],
            content=row["content"],
            content_tsv=tsv,
            embedding=emb,
            language=row["language"],
            product_area=row["product_area"],
            confidentiality=row["confidentiality"],
            metadata_=row["metadata_"],
        )
        session.add(chunk)
    await session.commit()


async def main() -> None:
    articles = _load_jsonl(DATA_DIR / "kb_articles.jsonl")
    tickets = _load_jsonl(DATA_DIR / "synthetic_tickets.jsonl")

    logger.info("loaded_source_records", articles=len(articles), tickets=len(tickets))

    raw_rows = _build_rows(articles) + _build_rows(tickets)
    all_rows = _dedup_rows(raw_rows)
    logger.info(
        "deduped_chunks",
        before=len(raw_rows),
        after=len(all_rows),
        removed=len(raw_rows) - len(all_rows),
    )
    logger.info("total_chunks_to_embed", count=len(all_rows))

    embedder = get_embedder()
    texts = [r["content"] for r in all_rows]

    logger.info("embedding_all_chunks", count=len(texts))
    embeddings = await embedder.embed_batch(texts)

    async with async_session_factory() as session:
        inserted = 0
        for offset in range(0, len(all_rows), BATCH_SIZE):
            batch_rows = all_rows[offset : offset + BATCH_SIZE]
            batch_embs = embeddings[offset : offset + BATCH_SIZE]
            await _insert_batch(session, batch_rows, batch_embs)
            inserted += len(batch_rows)
            logger.info("inserted_batch", inserted=inserted, total=len(all_rows))

    print(f"\nIngestion complete: {inserted} rows inserted into kb_chunks.")


if __name__ == "__main__":
    asyncio.run(main())
