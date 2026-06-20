"""Drop and recreate the entire database schema.

Drops the public schema (removing all tables, types, and extensions),
recreates it, then runs `alembic upgrade head` to rebuild from scratch.

Usage:
    python scripts/reset_db.py
"""

import asyncio
import subprocess
import sys

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


async def _drop_and_recreate_schema() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("DROP SCHEMA public CASCADE"))
            await conn.execute(sa.text("CREATE SCHEMA public"))
            await conn.execute(sa.text("GRANT ALL ON SCHEMA public TO PUBLIC"))
    finally:
        await engine.dispose()


def _run_migrations() -> None:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)


def main() -> None:
    print("Dropping and recreating public schema…")
    asyncio.run(_drop_and_recreate_schema())
    print("Running migrations…")
    _run_migrations()
    print("Database reset complete.")


if __name__ == "__main__":
    main()
