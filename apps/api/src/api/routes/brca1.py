"""BRCA1 variant-effect classifier endpoint (Tier-3 research prototype).

Wraps the XGBoost model trained on Findlay 2018 SGE functional scores. Every
response includes the held-out performance metrics so the UI can be honest
about model quality.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.ml.infer import (
    VariantParseError,
    classify,
    load_metadata,
    parse_hgvs_protein,
)
from api.services import brca_exchange

router = APIRouter(prefix="/api/brca1", tags=["brca1-classifier"])


class BrcaExchangeRecord(BaseModel):
    hgvs_cdna: str | None = None
    hgvs_protein: str | None = None
    enigma_classification: str | None = None
    enigma_date_evaluated: str | None = None
    enigma_method: str | None = None
    clinvar_classification: str | None = None
    sources: str | None = None
    link: str | None = None


class Brca1ClassifyRequest(BaseModel):
    hgvs_protein: str = Field(..., description="HGVS protein notation, e.g. 'p.Cys61Gly' or 'p.C61G'")


class Brca1ComponentScores(BaseModel):
    xgb_probability: float
    alphamissense_score: float | None
    alphamissense_class: str | None
    alphamissense_covered: bool
    alphamissense_value_used: float | None


class Brca1Conformal(BaseModel):
    coverage: float
    threshold: float
    prediction_set: list[str]
    label: str  # "loss_of_function" | "functional" | "uncertain"


class Brca1ClassifyResponse(BaseModel):
    hgvs_protein: str
    ref_aa: str
    position: int
    alt_aa: str
    consequence: str
    domain: str
    in_assayed_region: bool
    probability_loss_of_function: float
    label: str
    confidence: str
    # Component scores so the UI can show the ensemble's inputs honestly.
    components: Brca1ComponentScores
    # Calibrated conformal-prediction set at 80% coverage by default.
    conformal: Brca1Conformal
    # Model provenance so the UI can show "trained on X, validated on Y"
    model_version: str
    training_citation: str
    holdout_auroc: float
    holdout_auprc: float
    caveats: list[str]


_DEFAULT_CAVEATS = [
    "This is a research-grade v0 baseline. It is NOT a substitute for ENIGMA / "
    "BRCA Exchange expert classification, or for genetic counseling.",
    "Training data covers the RING and BRCT domains (Findlay SGE assay). "
    "Predictions for variants outside those regions are extrapolation.",
    "Do not make treatment decisions from this prediction. Always consult a "
    "certified clinical lab and a genetic counselor.",
]


@router.post("/classify", response_model=Brca1ClassifyResponse)
async def classify_brca1(payload: Brca1ClassifyRequest) -> Brca1ClassifyResponse:
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
            f"Residue {pos} is outside the Findlay assay's covered domains "
            "(RING + BRCT). Treat this prediction with extra caution.",
        )

    return Brca1ClassifyResponse(
        hgvs_protein=payload.hgvs_protein,
        ref_aa=ref,
        position=pos,
        alt_aa=alt,
        consequence=result["consequence"],
        domain=result["domain"],
        in_assayed_region=result["in_assayed_region"],
        probability_loss_of_function=result["probability_loss_of_function"],
        label=result["label"],
        confidence=result["confidence"],
        components=Brca1ComponentScores(**result["components"]),
        conformal=Brca1Conformal(**result["conformal"]),
        model_version=meta.get("model_version", "brca1_xgb_v1"),
        training_citation=meta.get(
            "training_citation",
            "Findlay GM et al. Nature 562, 217-222 (2018).",
        ),
        holdout_auroc=float(holdout.get("auroc", 0.0)),
        holdout_auprc=float(holdout.get("auprc", 0.0)),
        caveats=caveats,
    )


@router.get("/metadata")
async def get_metadata() -> dict:
    """Full model metadata, including per-domain holdout AUROC + top features."""
    return load_metadata()


@router.get("/exchange", response_model=BrcaExchangeRecord | None)
async def lookup_brca_exchange(hgvs_protein: str) -> BrcaExchangeRecord | None:
    """Opportunistic BRCA Exchange lookup. Returns null if not found or upstream fails."""
    data = await brca_exchange.lookup(hgvs_protein)
    if data is None:
        return None
    return BrcaExchangeRecord(
        hgvs_cdna=data.get("hgvs_cdna"),
        hgvs_protein=data.get("hgvs_protein"),
        enigma_classification=data.get("enigma_classification"),
        enigma_date_evaluated=data.get("enigma_date_evaluated"),
        enigma_method=data.get("enigma_method"),
        clinvar_classification=data.get("clinvar_classification"),
        sources=data.get("sources"),
        link=data.get("link"),
    )
