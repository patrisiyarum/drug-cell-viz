"""Virtual-screening endpoint.

Takes a target gene + a small compound library of SMILES and returns a
ranked list scored by composite pocket-fit + chemical similarity. This is
the "do chemistry on a computer before you ever touch the wet lab" path —
the same core move Bioptic automates at industrial scale.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.models.screening import (
    CandidateScoreOut,
    ScreeningRequest,
    ScreeningResponse,
)
from api.services.screening import (
    CandidateInput,
    ScreeningError,
    run_screening,
)

router = APIRouter(prefix="/api/screening", tags=["screening"])


@router.post("/run", response_model=ScreeningResponse, status_code=201)
async def run(payload: ScreeningRequest) -> ScreeningResponse:
    if not payload.candidates:
        raise HTTPException(status_code=400, detail="candidates list is empty")
    if len(payload.candidates) > 50:
        # Keep the request bounded — larger libraries should be scheduled via
        # the ARQ worker, not the synchronous request path.
        raise HTTPException(
            status_code=413,
            detail="at most 50 candidates per request; split into batches or "
            "use the async screening worker",
        )

    try:
        result = await run_screening(
            payload.target_gene,
            [
                CandidateInput(id=c.id, name=c.name, smiles=c.smiles)
                for c in payload.candidates
            ],
        )
    except ScreeningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ScreeningResponse(
        target_gene=result.target_gene,
        target_uniprot=result.target_uniprot,
        pocket_radius_angstrom=result.pocket_radius_angstrom,
        reference_binders=result.reference_binders,
        protein_pdb_url=result.protein_pdb_url,
        ranked=[
            CandidateScoreOut(
                candidate_id=s.candidate_id,
                name=s.name,
                smiles=s.smiles,
                pocket_fit=s.pocket_fit,
                chem_similarity=s.chem_similarity,
                closest_reference=s.closest_reference,
                fit_score=s.fit_score,
                heavy_atom_count=s.heavy_atom_count,
                pose_pdb_url=s.pose_pdb_url,
                rank=s.rank,
            )
            for s in result.ranked
        ],
    )
