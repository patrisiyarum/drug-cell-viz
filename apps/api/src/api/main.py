from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.config import settings
from api.db import check_db, init_db
from api.routes import (
    bc_router,
    brca1_router,
    brca2_router,
    export_router,
    jobs_limiter,
    jobs_router,
    molecular_router,
    morphology_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=settings.log_level)
    settings.local_storage_root.mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="drug-cell-viz API", version="0.1.0", lifespan=lifespan)

# CORS: the Next.js dev server runs on a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = jobs_limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_req: Any, exc: RateLimitExceeded) -> Any:
    raise HTTPException(status_code=429, detail=f"rate limit exceeded: {exc.detail}")


app.include_router(jobs_router)
app.include_router(molecular_router)
app.include_router(morphology_router)
app.include_router(export_router)
app.include_router(bc_router)
app.include_router(brca1_router)
app.include_router(brca2_router)

# Serve local blob storage so the frontend can fetch PDBs and thumbnails by URL.
if settings.storage_backend == "local":
    settings.local_storage_root.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/blobs",
        StaticFiles(directory=str(settings.local_storage_root)),
        name="blobs",
    )


_redis: redis.Redis = redis.from_url(settings.redis_url, decode_responses=True)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    try:
        checks["redis"] = bool(await _redis.ping())
    except Exception:
        checks["redis"] = False
    try:
        checks["db"] = await check_db()
    except Exception:
        checks["db"] = False

    if not all(checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}
