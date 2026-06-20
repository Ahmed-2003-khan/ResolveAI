from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    ok: bool
    env: str


class ReadyResponse(BaseModel):
    ok: bool
    db: bool
    redis: bool


@router.get("/healthz", response_model=HealthResponse, tags=["health"])
async def healthz() -> HealthResponse:
    from app.config import get_settings

    settings = get_settings()
    return HealthResponse(ok=True, env=settings.app_env)


@router.get("/readyz", response_model=ReadyResponse, tags=["health"])
async def readyz() -> ReadyResponse:
    db_ok = False
    redis_ok = False

    try:
        from sqlalchemy import text

        from app.core.db import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    try:
        from app.core.redis import get_redis

        r = await get_redis()
        await r.ping()
        redis_ok = True
    except Exception:
        pass

    return ReadyResponse(ok=db_ok and redis_ok, db=db_ok, redis=redis_ok)
