"""Tests for the HRD composite score.

This is THE headline clinical output of the app post-pivot — PARP-inhibitor
eligibility across breast, ovarian, pancreatic, and prostate cancer. Worth
pinning the expected behavior in tests.
"""

from __future__ import annotations

import pytest

from api.services.hrd import CORE_HR_GENES, MODERATE_HR_GENES, compute_hrd


def _resolved(catalog_id: str, gene: str, zyg: str = "heterozygous") -> dict:
    """Mimic the shape of `_resolve_variants`' output."""
    return {
        "gene_symbol": gene,
        "position": 0,
        "catalog_id": catalog_id,
        "zygosity": zyg,
        "label": catalog_id,
    }


def test_germline_brca1_pathogenic_calls_hr_deficient() -> None:
    """Heterozygous germline BRCA1 pathogenic → HR-deficient tumor.

    Classic olaparib-eligible profile. Must produce the headline label.
    """
    hrd = compute_hrd([_resolved("BRCA1_C61G", "BRCA1")], classifiable_brca1_hgvs=None)
    assert hrd.label == "hr_deficient"
    assert hrd.score >= 60
    assert any(e.source == "catalog_pathogenic" for e in hrd.evidence)
    assert "PARP inhibitor" in hrd.parp_inhibitor_context


def test_germline_brca2_pathogenic_calls_hr_deficient() -> None:
    hrd = compute_hrd([_resolved("BRCA2_6174delT", "BRCA2")])
    assert hrd.label == "hr_deficient"


def test_germline_palb2_pathogenic_calls_hr_deficient() -> None:
    hrd = compute_hrd([_resolved("PALB2_1592delT", "PALB2")])
    assert hrd.label == "hr_deficient"


def test_chek2_alone_does_not_call_hr_deficient() -> None:
    """CHEK2 is moderate-penetrance; by itself it must not drive HR-deficient.

    This is the single most important correctness property: CHEK2 carriers
    are at elevated hereditary cancer risk but their tumors are NOT
    reliably PARPi-sensitive, and the app must not suggest they are.
    """
    hrd = compute_hrd([_resolved("CHEK2_1100delC", "CHEK2")])
    assert hrd.label == "indeterminate"
    assert hrd.score < 60
    # The summary must explicitly distinguish moderate-penetrance from HR-deficient.
    assert "moderate" in hrd.summary.lower()


def test_empty_variant_set_is_indeterminate() -> None:
    hrd = compute_hrd([])
    assert hrd.label == "indeterminate"
    assert hrd.evidence == []
    assert hrd.score == 0


def test_drug_response_variant_alone_is_not_hr_deficient() -> None:
    """ESR1 resistance, CYP2D6*4, PIK3CA hotspot etc. aren't HR genes.

    The HRD call must only fire on actual HR-pathway evidence.
    """
    hrd = compute_hrd([_resolved("CYP2D6_star4", "CYP2D6")])
    assert hrd.label == "indeterminate"
    hrd2 = compute_hrd([_resolved("PIK3CA_H1047R", "PIK3CA")])
    assert hrd2.label == "indeterminate"


def test_brca1_ml_prediction_contributes_when_high_confidence() -> None:
    """If the user pastes a BRCA1 sequence with a p.Cys61Gly change, the ML
    classifier call should push the HRD composite into hr_deficient.
    """
    hrd = compute_hrd(
        resolved_variants=[],
        classifiable_brca1_hgvs=["p.Cys61Gly"],
    )
    # Cys61Gly comes out at ~0.955 from the ensemble, so the composite should
    # light up based on the ML call alone.
    assert hrd.label == "hr_deficient"
    assert any(e.source == "ml_prediction" for e in hrd.evidence)


def test_synonymous_brca1_does_not_trigger_hr_deficient() -> None:
    """A synonymous BRCA1 change should NOT push toward HR deficiency."""
    hrd = compute_hrd(
        resolved_variants=[],
        classifiable_brca1_hgvs=["p.Ala85Ala"],
    )
    assert hrd.label != "hr_deficient"


def test_core_and_moderate_panels_are_disjoint() -> None:
    """Property: CORE and MODERATE HR gene sets must not overlap.

    Mixing them would mean a gene counts twice, inflating the score.
    """
    assert CORE_HR_GENES.isdisjoint(MODERATE_HR_GENES)


def test_combined_core_plus_moderate_still_hr_deficient() -> None:
    """A patient with both BRCA2+ and CHEK2+ is still HR-deficient."""
    hrd = compute_hrd(
        [
            _resolved("BRCA2_6174delT", "BRCA2"),
            _resolved("CHEK2_1100delC", "CHEK2"),
        ]
    )
    assert hrd.label == "hr_deficient"
    # Both pieces of evidence should surface.
    genes = {e.gene for e in hrd.evidence}
    assert "BRCA2" in genes and "CHEK2" in genes
