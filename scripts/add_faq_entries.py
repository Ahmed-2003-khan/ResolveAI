"""Add targeted FAQ entries to kb_chunks to fix retrieval gaps.

These are clean Q/A chunks for questions where the existing KB has wrong
or missing content. English only — the multilingual embedding model
(text-embedding-3-small) bridges cross-lingual queries automatically.

Usage (inside Docker):
    docker compose exec -T api python -m scripts.add_faq_entries
"""

from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import text

from app.core.db import async_session_factory
from app.models.kb_chunk import KBChunk
from app.services.rag.embedder import get_embedder

log = structlog.get_logger(__name__)

# Each entry: (source_id, title, question, answer, product_area)
_FAQ_ENTRIES = [
    (
        "faq_std_001",
        "General Refund Policy",
        "What is your refund policy?",
        "Our refund policy allows refunds within 30 days of delivery for most products. "
        "Refunds are processed within 3-5 business days after the returned item is received "
        "and inspected at our warehouse. The refund is credited back to your original payment "
        "method — Easypaisa, JazzCash, bank account, or card.",
        "refunds",
    ),
    (
        "faq_std_002",
        "Standard Delivery Time",
        "How long does delivery take? What is the standard delivery time?",
        "Standard delivery takes 3-5 business days nationwide. Same-day delivery is available "
        "in Karachi, Lahore, and Islamabad for orders placed before 12 PM PKT — coverage zones "
        "include DHA, Gulshan, Clifton, Model Town, F-sector, and G-sector. Express delivery "
        "(next business day) is available for orders placed before 3 PM PKT. Remote areas like "
        "Gilgit-Baltistan may take 7-10 business days.",
        "orders",
    ),
    (
        "faq_std_005",
        "Accepted Payment Methods",
        "What payment methods do you accept?",
        "We accept the following payment methods: Easypaisa, JazzCash, bank transfer "
        "(all major Pakistani banks), and credit/debit cards (Visa, Mastercard). "
        "Cash on Delivery (COD) is also available in most areas. "
        "Installment plans (BNPL) are available for select products.",
        "payments",
    ),
    (
        "faq_std_011",
        "Product Return Policy",
        "What is the return policy? How do I return a product?",
        "You can return any product within 30 days of delivery for a full refund. "
        "The item must be in its original condition with all tags and packaging intact. "
        "To initiate a return, contact our support team with your order ID. "
        "A pickup is scheduled within 24-48 hours. Refund is processed within 3-5 business days "
        "after the item is received at our warehouse. Sale items can be returned within 14 days.",
        "refunds",
    ),
    (
        "faq_std_017",
        "Cash on Delivery Availability",
        "Is Cash on Delivery (COD) available? Can I place an order and pay cash on delivery?",
        "Yes, Cash on Delivery (COD) is available across most of Pakistan. "
        "However, COD is not available in some remote zones such as parts of Gilgit-Baltistan. "
        "A COD handling fee of PKR 100 applies to orders below PKR 2,000. "
        "Please have the exact amount ready as couriers may not carry change. "
        "COD orders are dispatched after prepaid orders in the queue.",
        "orders",
    ),
]


async def main() -> None:
    embedder = get_embedder()

    # Build content strings (same format as chunker for faq source_type)
    contents = [f"Q: {q}\n\nA: {a}" for _, _, q, a, _ in _FAQ_ENTRIES]

    log.info("embedding_faq_entries", count=len(contents))
    embeddings = await embedder.embed_batch(contents)

    async with async_session_factory() as session:
        for (source_id, title, _, _, product_area), content, embedding in zip(
            _FAQ_ENTRIES, contents, embeddings, strict=False
        ):
            # Check if already exists
            existing = await session.scalar(
                text("SELECT id FROM kb_chunks WHERE source_id = :sid LIMIT 1"),
                {"sid": source_id},
            )
            if existing:
                log.info("faq_entry_already_exists", source_id=source_id)
                continue

            chunk = KBChunk(
                id=uuid.uuid4(),
                source_id=source_id,
                source_type="faq",
                title=title,
                content=content,
                embedding=embedding,
                language="en",
                product_area=product_area,
                confidentiality="public",
                metadata_={"chunk_index": 0, "total_chunks": 1},
            )
            session.add(chunk)
            log.info("faq_entry_added", source_id=source_id, title=title)

        await session.commit()

    print(f"\nDone — {len(_FAQ_ENTRIES)} FAQ entries processed.")


if __name__ == "__main__":
    import app.core.logging  # noqa: F401

    asyncio.run(main())
