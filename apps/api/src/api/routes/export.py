"""Zip export: given a job_id, produce a zip with the pose PDB, a confidence
CSV, and the control thumbnail + match thumbnails. One-shot, no background task.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from api.db import session_scope
from api.models import Job, MolecularResultRow, MorphologyResultRow
from api.services import storage

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{job_id}.zip")
async def export_job(job_id: str) -> StreamingResponse:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "job.json",
            json.dumps(
                {
                    "id": job.id,
                    "kind": job.kind.value,
                    "status": job.status.value,
                    "smiles": job.smiles,
                    "uniprot_id": job.uniprot_id,
                    "error": job.error,
                },
                indent=2,
            ),
        )

        if job.molecular_result_id:
            async with session_scope() as session:
                mrow = await session.get(MolecularResultRow, job.molecular_result_id)
            if mrow is not None:
                poses = json.loads(mrow.poses_json)
                csv_buf = io.StringIO()
                writer = csv.writer(csv_buf)
                writer.writerow(["rank", "confidence", "affinity_kcal_mol", "pdb_url"])
                for p in poses:
                    writer.writerow(
                        [p["rank"], p["confidence"], p.get("affinity_kcal_mol"), p["pdb_url"]]
                    )
                zf.writestr("poses.csv", csv_buf.getvalue())
                for p in poses:
                    key = p["pdb_url"].rsplit("/blobs/", 1)[-1]
                    data = await storage.get(key)
                    if data is not None:
                        zf.writestr(f"pose_{p['rank']}.pdb", data)

        if job.morphology_result_id:
            async with session_scope() as session:
                morow = await session.get(MorphologyResultRow, job.morphology_result_id)
            if morow is not None:
                payload = json.loads(morow.matches_json)
                zf.writestr("morphology.json", json.dumps(payload, indent=2))

    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{job_id}.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
