"""Breast-cancer pharmacogenomic + variant-analysis routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from api.db import session_scope
from api.models import AnalysisCreate, AnalysisResult, AnalysisRow
from api.services import analysis as analysis_service
from api.services.bc_catalog import DRUGS, GENES, VARIANTS

router = APIRouter(prefix="/api/bc", tags=["breast-cancer"])


@router.get("/catalog")
async def get_catalog() -> dict:
    """Return drugs + genes + variants for the frontend pickers."""
    return {
        "drugs": [
            {
                "id": d["id"],
                "name": d["name"],
                "category": d["category"],
                "primary_target_gene": d["primary_target_gene"],
                "metabolizing_gene": d["metabolizing_gene"],
                "mechanism": d["mechanism"],
                "indication": d["breast_cancer_indication"],
                "supports_docking": bool(d["smiles"]),
            }
            for d in DRUGS.values()
        ],
        "genes": [
            {
                "symbol": g["symbol"],
                "name": g["name"],
                "uniprot_id": g["uniprot_id"],
                "role": g["role"],
            }
            for g in GENES.values()
        ],
        "variants": [
            {
                "id": v["id"],
                "gene_symbol": v["gene_symbol"],
                "name": v["name"],
                "hgvs_protein": v["hgvs_protein"],
                "residue_positions": v["residue_positions"],
                "clinical_significance": v["clinical_significance"],
                "effect_summary": v["effect_summary"],
            }
            for v in VARIANTS.values()
        ],
    }


@router.post("/analyze", response_model=AnalysisResult, status_code=201)
async def analyze(payload: AnalysisCreate) -> AnalysisResult:
    try:
        result = await analysis_service.run_analysis(payload.drug_id, payload.variants)
    except analysis_service.AnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with session_scope() as session:
        row = AnalysisRow(
            id=result.id,
            drug_id=result.drug_id,
            target_gene=result.target_gene,
            payload_json=result.model_dump_json(),
        )
        session.add(row)
        await session.commit()
    return result


@router.get("/analysis/{result_id}", response_model=AnalysisResult)
async def get_analysis(result_id: str) -> AnalysisResult:
    async with session_scope() as session:
        row = await session.get(AnalysisRow, result_id)
    if row is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return AnalysisResult(**json.loads(row.payload_json))
