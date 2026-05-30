"""ARQ worker configuration."""

from __future__ import annotations

import structlog
from arq.connections import RedisSettings

from app.config import get_settings
from app.core.logging import setup_logging
from app.workers.tasks import process_inbound_message

log = structlog.get_logger(__name__)

_settings = get_settings()


async def startup(ctx: dict) -> None:
    setup_logging()
    # Pre-warm the reranker so its model is loaded before the first job arrives.
    # Without this the first job always times out while the model downloads.
    import asyncio

    log.info("arq_worker_prewarm_reranker_start")
    try:
        from app.services.rag.reranker import get_reranker
        reranker = get_reranker()
        # Triggers _load() + one predict pass so the model is hot for real jobs
        await reranker.rerank("warmup", [{"content": "warmup"}], k=1)
        log.info("arq_worker_prewarm_reranker_done")
    except Exception as exc:
        log.warning("arq_worker_prewarm_reranker_failed", error=str(exc))
    log.info("arq_worker_startup")


async def shutdown(ctx: dict) -> None:
    from app.core.redis import close_redis

    await close_redis()
    log.info("arq_worker_shutdown")


class WorkerSettings:
    functions = [process_inbound_message]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 120  # seconds — increased to survive cold reranker load
    keep_result = 3600  # keep job results for 1 h for debugging
