"""ARQ worker entrypoint. Run with: `uv run arq api.workers.settings.WorkerSettings`."""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as redis
from arq.connections import RedisSettings

from api.config import settings
from api.db import init_db
from api.workers.tasks import run_job


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def startup(ctx: dict[str, Any]) -> None:
    logging.basicConfig(level=settings.log_level)
    await init_db()
    ctx["redis"] = redis.from_url(settings.redis_url, decode_responses=True)


async def shutdown(ctx: dict[str, Any]) -> None:
    if "redis" in ctx:
        await ctx["redis"].close()


class WorkerSettings:
    functions = [run_job]
    redis_settings = _redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 60 * 10
