"""Variant-evidence agent endpoint.

POST /api/agent/variant-evidence accepts a (gene, variant, indication)
triple and returns a structured response with:
    - A clinician-ready summary (Claude-formatted, but constrained to
      describing the retrieved evidence dict, not inventing claims)
    - The raw evidence from each of four public databases
    - Metadata: which tool calls succeeded, total duration, model id

The agent itself lives in api.agents.variant_evidence; this route is a
thin wrapper that validates input, runs the LangGraph state machine,
and serializes the result.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.agents import variant_evidence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


class VariantEvidenceRequest(BaseModel):
    gene: str = Field(..., description="HGNC gene symbol, e.g. BRCA1")
    variant: str = Field(
        ...,
        description=(
            "HGVS protein notation, e.g. 'p.Cys61Gly' or 'Cys61Gly'. "
            "cDNA notation (e.g. 'c.181T>G') also works for ClinVar but "
            "won't match in gnomAD's protein-indexed search."
        ),
    )
    indication: str | None = Field(
        default=None,
        description=(
            "Optional clinical context (e.g. 'ovarian cancer'). The "
            "agent uses it to scope the OpenFDA drug filter and to "
            "frame the summary; not required."
        ),
    )


class ToolCallResult(BaseModel):
    """Structured output from one of the four tool calls. The shape
    differs per tool — we forward the raw dict from each so the
    frontend can render whatever fields exist."""
    status: str
    payload: dict


class VariantEvidenceResponse(BaseModel):
    gene: str
    hgvs_protein: str
    indication: str | None
    summary: str
    model: str
    evidence: dict
    tool_calls_succeeded: list[str]
    tool_calls_attempted: list[str]
    duration_ms: int
    constrained: str


@router.post("/variant-evidence", response_model=VariantEvidenceResponse)
async def variant_evidence_endpoint(req: VariantEvidenceRequest) -> VariantEvidenceResponse:
    if not req.gene.strip():
        raise HTTPException(400, "gene is required")
    if not req.variant.strip():
        raise HTTPException(400, "variant is required")

    try:
        result = await variant_evidence.run_agent(
            gene=req.gene.strip(),
            hgvs_protein=req.variant.strip(),
            indication=(req.indication.strip() if req.indication else None),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("variant-evidence agent failed")
        raise HTTPException(500, f"agent execution failed: {exc}") from exc

    return VariantEvidenceResponse(**result)
