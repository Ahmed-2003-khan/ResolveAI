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
    job_timeout = 60  # seconds — one full agent run budget
    keep_result = 3600  # keep job results for 1 h for debugging
