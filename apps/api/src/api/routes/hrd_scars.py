"""HRD scar scoring endpoint.

Patients (or their clinical labs) submit pre-computed scar feature counts
— HRD-LOH, LST, NTAI — and get back a three-tier HRD-sum classification:
`hr_deficient_scar` at sum >= 42 (Myriad myChoice cutoff), `borderline_scar`
at 33-41, `hr_proficient_scar` below.

The feature counts typically come from an upstream genome-graph SV call
pipeline (vg call / minigraph-cactus) feeding a scarHRD-style aggregator
— see `pipelines/rules/genome_graph_sv.smk` for the turnkey version. For
users who already have myChoice / FoundationOne CDx reports, the three
counts are exactly what's printed on the assay summary page.

Separate from the germline-variant HRD composite at `/api/bc/analyze`
because scar scoring requires tumor sequencing, not the germline VCF the
main analysis path consumes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services.hrd_scars import HrdScarFeatures, score

router = APIRouter(prefix="/api/hrd", tags=["hrd-scars"])


class ScarRequest(BaseModel):
    loh: int = Field(..., ge=0, description="HRD-LOH count (large partial LOH regions).")
    lst: int = Field(..., ge=0, description="Large-scale state transition breakpoints.")
    ntai: int = Field(..., ge=0, description="Telomeric allelic-imbalance regions.")


class ScarResponse(BaseModel):
    loh: int
    lst: int
    ntai: int
    hrd_sum: int
    label: str
    summary: str
    interpretation: str
    caveats: list[str]


@router.post("/scars", response_model=ScarResponse, status_code=201)
async def score_scars(payload: ScarRequest) -> ScarResponse:
    try:
        result = score(
            HrdScarFeatures(loh=payload.loh, lst=payload.lst, ntai=payload.ntai)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ScarResponse(
        loh=result.features.loh,
        lst=result.features.lst,
        ntai=result.features.ntai,
        hrd_sum=result.hrd_sum,
        label=result.label,
        summary=result.summary,
        interpretation=result.interpretation,
        caveats=result.caveats,
    )
