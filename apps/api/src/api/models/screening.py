"""Pydantic contracts for the virtual-screening endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScreeningCandidate(BaseModel):
    id: str = Field(..., description="Stable id for this compound (client-chosen).")
    name: str = Field(..., description="Display name, e.g. 'Talazoparib'.")
    smiles: str = Field(..., description="Canonical SMILES.")


class ScreeningRequest(BaseModel):
    target_gene: str = Field(
        ...,
        description="Target gene symbol (must be in the curated GENES catalog).",
    )
    candidates: list[ScreeningCandidate]


class CandidateScoreOut(BaseModel):
    candidate_id: str
    name: str
    smiles: str
    pocket_fit: float
    chem_similarity: float
    closest_reference: str | None
    fit_score: float
    heavy_atom_count: int
    rank: int


class ScreeningResponse(BaseModel):
    target_gene: str
    target_uniprot: str
    pocket_radius_angstrom: float
    reference_binders: list[str]
    ranked: list[CandidateScoreOut]
