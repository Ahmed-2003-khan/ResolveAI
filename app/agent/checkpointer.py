"""Checkpointer factory for LangGraph conversation persistence.

Production target: AsyncPostgresSaver (requires psycopg3).
Dev/test fallback: MemorySaver (in-process, no dependencies).
"""

from __future__ import annotations

import structlog
from langgraph.checkpoint.memory import MemorySaver

log = structlog.get_logger(__name__)


def get_memory_saver() -> MemorySaver:
    """Return an in-memory checkpointer — suitable for tests and single-process dev."""
    return MemorySaver()


async def get_postgres_saver(conn_string: str):
    """Return an AsyncPostgresSaver connected to Postgres.

    Falls back to MemorySaver if psycopg is not installed so the app can
    still run without the optional dependency.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore

        saver = AsyncPostgresSaver.from_conn_string(conn_string)
        await saver.setup()
        log.info("checkpointer_postgres_ready")
        return saver
    except ImportError:
        log.warning(
            "psycopg_not_installed",
            reason="AsyncPostgresSaver unavailable — falling back to MemorySaver",
        )
        return MemorySaver()
    except Exception as exc:
        log.error("checkpointer_postgres_failed", error=str(exc))
        return MemorySaver()
