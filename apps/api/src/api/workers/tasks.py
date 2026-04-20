"""ARQ worker tasks. Orchestrate AlphaFold fetch → docking → morphology.

One public entry point per job: `run_job(ctx, job_id)`. The worker updates the
Job row as it progresses so the frontend can poll status. Redis is used both
as the ARQ broker and as a result cache keyed on `(smiles, uniprot_id)` so
that repeated submissions don't re-run the expensive docking step.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlmodel import select

from api.db import session_scope
from api.models import (
    DockingPose,
    Job,
    JobKind,
    JobStatus,
    MolecularResultRow,
    MorphologyResultRow,
)
from api.services import alphafold, docking, morphology, storage

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 24 * 60 * 60  # 1 day


async def run_job(ctx: dict[str, Any], job_id: str) -> None:
    job = await _load_job(job_id)
    if job is None:
        logger.warning("job %s vanished before worker picked it up", job_id)
        return
    await _set_status(job.id, JobStatus.RUNNING)

    try:
        if job.kind in (JobKind.MOLECULAR, JobKind.COMBINED):
            mol_id = await _run_molecular(ctx, job)
            await _set_molecular_id(job.id, mol_id)
        if job.kind in (JobKind.MORPHOLOGY, JobKind.COMBINED):
            morph_id = await _run_morphology(job)
            await _set_morphology_id(job.id, morph_id)
        await _set_status(job.id, JobStatus.COMPLETED)
    except Exception as exc:  # noqa: BLE001 — we want to persist any failure mode
        logger.exception("job %s failed: %s", job_id, exc)
        await _set_status(job.id, JobStatus.FAILED, error=str(exc))


async def _run_molecular(ctx: dict[str, Any], job: Job) -> str:
    cache_key = f"molecular:{job.uniprot_id}:{job.smiles}"
    redis = ctx.get("redis")

    if redis is not None:
        cached_id = await redis.get(cache_key)
        if cached_id is not None:
            cached_id_str = cached_id if isinstance(cached_id, str) else cached_id.decode()
            if await _molecular_exists(cached_id_str):
                logger.info("molecular cache hit %s → %s", cache_key, cached_id_str)
                return cached_id_str

    pdb_bytes, protein_url = await alphafold.fetch_structure(job.uniprot_id)
    poses_raw = await docking.dock(pdb_bytes, job.smiles)

    poses: list[DockingPose] = []
    for rank, res in enumerate(poses_raw, start=1):
        pose_key = f"poses/{job.id}/pose_{rank}.pdb"
        pose_url = await storage.put(pose_key, res.pose_pdb.encode("utf-8"), "chemical/x-pdb")
        poses.append(
            DockingPose(
                rank=rank,
                confidence=res.confidence,
                affinity_kcal_mol=None,
                pdb_url=pose_url,
            )
        )

    result_id = uuid4().hex
    from api.config import settings
    source = "alphafold_db"
    async with session_scope() as session:
        row = MolecularResultRow(
            id=result_id,
            uniprot_id=job.uniprot_id,
            smiles=job.smiles,
            protein_pdb_url=protein_url,
            poses_json=json.dumps([p.model_dump() for p in poses]),
            source=source,
        )
        session.add(row)
        await session.commit()

    if redis is not None:
        await redis.set(cache_key, result_id, ex=CACHE_TTL_SECONDS)
    _ = settings  # keep reference so mypy doesn't complain about unused import in some branches
    return result_id


async def _run_morphology(job: Job) -> str:
    fp_hex, matches, control_url = await morphology.query(job.smiles, k=7)
    result_id = uuid4().hex
    async with session_scope() as session:
        row = MorphologyResultRow(
            id=result_id,
            smiles=job.smiles,
            matches_json=json.dumps(
                {
                    "query_fingerprint": fp_hex,
                    "matches": [m.model_dump() for m in matches],
                }
            ),
            control_url=control_url,
        )
        session.add(row)
        await session.commit()
    return result_id


async def _load_job(job_id: str) -> Job | None:
    async with session_scope() as session:
        return await session.get(Job, job_id)


async def _set_status(job_id: str, status: JobStatus, *, error: str | None = None) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = status
        job.updated_at = datetime.utcnow()
        if error is not None:
            job.error = error
        session.add(job)
        await session.commit()


async def _set_molecular_id(job_id: str, result_id: str) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.molecular_result_id = result_id
        job.updated_at = datetime.utcnow()
        session.add(job)
        await session.commit()


async def _set_morphology_id(job_id: str, result_id: str) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.morphology_result_id = result_id
        job.updated_at = datetime.utcnow()
        session.add(job)
        await session.commit()


async def _molecular_exists(result_id: str) -> bool:
    async with session_scope() as session:
        result = await session.execute(
            select(MolecularResultRow).where(MolecularResultRow.id == result_id)
        )
        return result.scalar_one_or_none() is not None
