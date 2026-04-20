from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from api.db import session_scope
from api.models import MorphologyMatch, MorphologyResult, MorphologyResultRow

router = APIRouter(prefix="/api/morphology", tags=["morphology"])


@router.get("/{result_id}", response_model=MorphologyResult)
async def get_morphology_result(result_id: str) -> MorphologyResult:
    async with session_scope() as session:
        row = await session.get(MorphologyResultRow, result_id)
    if row is None:
        raise HTTPException(status_code=404, detail="morphology result not found")
    payload = json.loads(row.matches_json)
    matches = [MorphologyMatch(**m) for m in payload["matches"]]
    return MorphologyResult(
        id=row.id,
        smiles=row.smiles,
        query_fingerprint=payload["query_fingerprint"],
        matches=matches,
        control_url=row.control_url,
    )
