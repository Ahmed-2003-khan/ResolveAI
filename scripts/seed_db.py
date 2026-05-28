"""Seed the users table from data/seed/user_profiles.jsonl.

Usage:
    python scripts/seed_db.py

Upserts on phone column so repeated runs are idempotent.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.db import async_session_factory
from app.models.user_profile import UserProfile

logger = structlog.get_logger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "seed"


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


async def main() -> None:
    records = _load_jsonl(DATA_DIR / "user_profiles.jsonl")
    logger.info("loaded_user_profiles", count=len(records))

    async with async_session_factory() as session:
        for rec in records:
            stmt = (
                pg_insert(UserProfile)
                .values(
                    id=uuid.UUID(rec["id"]),
                    phone=rec["phone"],
                    email=rec.get("email"),
                    full_name=rec.get("full_name"),
                    plan_tier=rec.get("plan_tier"),
                    account_status=rec.get("account_status", "active"),
                    language_pref=rec.get("language_pref", "en"),
                    metadata_=rec.get("metadata"),
                )
                .on_conflict_do_update(
                    index_elements=["phone"],
                    set_={
                        "email": rec.get("email"),
                        "full_name": rec.get("full_name"),
                        "plan_tier": rec.get("plan_tier"),
                        "account_status": rec.get("account_status", "active"),
                        "language_pref": rec.get("language_pref", "en"),
                        "metadata_": rec.get("metadata"),
                    },
                )
            )
            await session.execute(stmt)
        await session.commit()

    print(f"\nSeeded {len(records)} user profiles into the users table.")


if __name__ == "__main__":
    asyncio.run(main())
