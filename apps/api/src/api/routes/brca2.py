"""BRCA2 DNA-binding-domain variant-effect classifier endpoint (v0 baseline).

Wraps the XGBoost model trained on Huang et al. 2025 SGE functional scores
for BRCA2 DBD missense variants. Much smaller scope than the BRCA1 classifier:
no AlphaMissense ensemble, no conformal calibration (v0).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.ml.infer_brca2 import (
    VariantParseError,
    classify,
    load_metadata,
    parse_hgvs_protein,
)

router = APIRouter(prefix="/api/brca2", tags=["brca2-classifier"])


class Brca2ClassifyRequest(BaseModel):
    hgvs_protein: str = Field(..., description="HGVS protein notation, e.g. 'p.D2723H' or 'p.Asp2723His'")


class Brca2ClassifyResponse(BaseModel):
    hgvs_protein: str
    ref_aa: str
    position: int
    alt_aa: str
    consequence: str
    in_assayed_region: bool
    probability_pathogenic: float
    label: str
    confidence: str
    model_version: str
    training_citation: str
    holdout_auroc: float
    holdout_auprc: float
    caveats: list[str]


_DEFAULT_CAVEATS = [
    "Research-grade v0 baseline. BRCA2 DBD only (residues 2479-3216).",
    "Trained on Huang et al. 2025 SGE functional scores. Not a substitute for ENIGMA / BRCA Exchange expert classification, or for genetic counseling.",
    "Features are not BRCA2-domain aware yet (no OB1/OB2/OB3/tower encoding). Predictions outside the DBD are extrapolation.",
    "Do not make treatment decisions from this prediction. Consult a certified clinical lab and a genetic counselor.",
]


@router.post("/classify", response_model=Brca2ClassifyResponse)
async def classify_brca2(payload: Brca2ClassifyRequest) -> Brca2ClassifyResponse:
    try:
        ref, pos, alt = parse_hgvs_protein(payload.hgvs_protein)
    except VariantParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = classify(ref, pos, alt)
    meta = load_metadata()
    holdout = meta.get("holdout_metrics", {})

    caveats = list(_DEFAULT_CAVEATS)
    if not result["in_assayed_region"]:
        caveats.insert(
            0,
            f"Residue {pos} is outside the Huang 2025 assay's covered region "
            "(BRCA2 DBD 2479-3216). Treat this prediction with extra caution.",
        )

    return Brca2ClassifyResponse(
        hgvs_protein=payload.hgvs_protein,
        ref_aa=ref,
        position=pos,
        alt_aa=alt,
        consequence=result["consequence"],
        in_assayed_region=result["in_assayed_region"],
        probability_pathogenic=result["probability_pathogenic"],
        label=result["label"],
        confidence=result["confidence"],
        model_version=meta.get("model_version", "brca2_xgb_v1"),
        training_citation=meta.get(
            "training_citation",
            "Huang H, Hu C, Ji J, et al. Nature 638, 528-537 (2025).",
        ),
        holdout_auroc=float(holdout.get("auroc", 0.0)),
        holdout_auprc=float(holdout.get("auprc", 0.0)),
        caveats=caveats,
    )


@router.get("/metadata")
async def get_metadata() -> dict:
    return load_metadata()
