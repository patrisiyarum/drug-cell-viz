"""Tests for the virtual-screening endpoint.

Ground truth: screening a handful of PARP1 candidates should rank known
PARP inhibitors (olaparib, niraparib) above an unrelated compound
(aspirin). This pins that the composite fit_score = 0.6 * pocket_fit +
0.4 * chem_similarity is directionally correct on a toy library.
"""

from __future__ import annotations

import pytest

from api.services.bc_catalog import DRUGS
from api.services.screening import (
    CandidateInput,
    run_screening,
)

# Aspirin SMILES — canonical, widely cited. Small, polar, and structurally
# unrelated to PARP inhibitors. A decent negative control.
ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"


@pytest.mark.asyncio
async def test_parp1_ranks_known_parp_inhibitors_above_aspirin() -> None:
    candidates = [
        CandidateInput(
            id="olaparib",
            name="Olaparib",
            smiles=DRUGS["olaparib"]["smiles"],
        ),
        CandidateInput(
            id="niraparib",
            name="Niraparib",
            smiles=DRUGS["niraparib"]["smiles"],
        ),
        CandidateInput(id="aspirin", name="Aspirin", smiles=ASPIRIN_SMILES),
    ]

    result = await run_screening("PARP1", candidates)

    assert result.target_gene == "PARP1"
    assert len(result.ranked) == 3
    # Aspirin must NOT be rank 1 — the other two are actual PARP inhibitors.
    top = result.ranked[0]
    assert top.candidate_id != "aspirin", (
        f"aspirin ranked above PARPi — something is wrong with the score: {result.ranked}"
    )
    # Chem-similarity for the PARP inhibitors must beat aspirin's (they're in
    # the reference set after all — olaparib IS a reference binder).
    aspirin = next(s for s in result.ranked if s.candidate_id == "aspirin")
    parp_scores = [s for s in result.ranked if s.candidate_id != "aspirin"]
    assert all(p.chem_similarity >= aspirin.chem_similarity for p in parp_scores)


@pytest.mark.asyncio
async def test_screening_returns_ranks_in_order() -> None:
    candidates = [
        CandidateInput(id="a", name="A", smiles=DRUGS["olaparib"]["smiles"]),
        CandidateInput(id="b", name="B", smiles=DRUGS["niraparib"]["smiles"]),
    ]
    result = await run_screening("PARP1", candidates)
    # rank is 1-indexed and strictly ascending in the returned order.
    assert [s.rank for s in result.ranked] == [1, 2]
    # fit_score is non-increasing by rank.
    scores = [s.fit_score for s in result.ranked]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_screening_unknown_gene_raises() -> None:
    from api.services.screening import ScreeningError

    with pytest.raises(ScreeningError):
        await run_screening(
            "NOT_A_GENE",
            [CandidateInput(id="x", name="X", smiles=DRUGS["olaparib"]["smiles"])],
        )
