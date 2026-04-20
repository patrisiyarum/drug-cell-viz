from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, HTTPException

from api.db import session_scope
from api.models import DockingPose, MolecularResult, MolecularResultRow

router = APIRouter(prefix="/api/molecular", tags=["molecular"])


@router.get("/{result_id}", response_model=MolecularResult)
async def get_molecular_result(result_id: str) -> MolecularResult:
    async with session_scope() as session:
        row = await session.get(MolecularResultRow, result_id)
    if row is None:
        raise HTTPException(status_code=404, detail="molecular result not found")
    poses = [DockingPose(**p) for p in json.loads(row.poses_json)]
    source = cast(
        "str",
        row.source if row.source in {"alphafold_db", "alphafold2_colabfold", "pdb"} else "alphafold_db",
    )
    return MolecularResult(
        id=row.id,
        uniprot_id=row.uniprot_id,
        smiles=row.smiles,
        protein_pdb_url=row.protein_pdb_url,
        poses=poses,
        source=source,  # type: ignore[arg-type]
    )
