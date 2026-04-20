from __future__ import annotations

import asyncio
import json
from datetime import datetime
from uuid import uuid4

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from api.config import settings
from api.db import session_scope
from api.models import Job, JobCreate, JobKind, JobRead, JobStatus

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
limiter = Limiter(key_func=get_remote_address)

_arq_pool: ArqRedis | None = None


async def get_arq() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _arq_pool


def _row_to_read(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        kind=job.kind,
        status=job.status,
        smiles=job.smiles,
        uniprot_id=job.uniprot_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
        molecular_result_id=job.molecular_result_id,
        morphology_result_id=job.morphology_result_id,
    )


@router.post("", response_model=JobRead, status_code=201)
@limiter.limit(f"{settings.rate_limit_jobs_per_hour}/hour")
async def create_job(request: Request, payload: JobCreate) -> JobRead:
    job_id = uuid4().hex
    now = datetime.utcnow()
    job = Job(
        id=job_id,
        kind=payload.kind,
        status=JobStatus.PENDING,
        smiles=payload.smiles,
        uniprot_id=payload.uniprot_id,
        created_at=now,
        updated_at=now,
    )
    async with session_scope() as session:
        session.add(job)
        await session.commit()

    arq = await get_arq()
    await arq.enqueue_job("run_job", job_id)
    return _row_to_read(job)


@router.get("/{job_id}", response_model=JobRead)
async def get_job(job_id: str) -> JobRead:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _row_to_read(job)


@router.get("/{job_id}/stream")
async def stream_job(job_id: str, request: Request) -> EventSourceResponse:
    """SSE stream of job status. Emits `status`, `complete`, or `error` events."""

    async def event_gen():
        last_status: JobStatus | None = None
        while True:
            if await request.is_disconnected():
                break
            async with session_scope() as session:
                job = await session.get(Job, job_id)
            if job is None:
                yield {
                    "event": "error",
                    "data": json.dumps({"job_id": job_id, "error": "job not found"}),
                }
                return
            if job.status != last_status:
                last_status = job.status
                progress = _progress_for(job)
                yield {
                    "event": "status",
                    "data": json.dumps(
                        {"job_id": job_id, "status": job.status.value, "progress": progress}
                    ),
                }
            if job.status == JobStatus.COMPLETED:
                yield {
                    "event": "complete",
                    "data": json.dumps(
                        {
                            "job_id": job_id,
                            "molecular_result_id": job.molecular_result_id,
                            "morphology_result_id": job.morphology_result_id,
                        }
                    ),
                }
                return
            if job.status == JobStatus.FAILED:
                yield {
                    "event": "error",
                    "data": json.dumps({"job_id": job_id, "error": job.error or "unknown"}),
                }
                return
            await asyncio.sleep(1.0)

    return EventSourceResponse(event_gen())


def _progress_for(job: Job) -> float:
    if job.status == JobStatus.PENDING:
        return 0.0
    if job.status == JobStatus.COMPLETED:
        return 1.0
    if job.status == JobStatus.FAILED:
        return 1.0
    # Rough: counts how many of the two branches have landed.
    done = int(job.molecular_result_id is not None) + int(job.morphology_result_id is not None)
    total = 2 if job.kind == JobKind.COMBINED else 1
    return min(0.95, 0.1 + 0.85 * (done / total))
