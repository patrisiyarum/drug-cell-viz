"""Tests for the drug/gene relevance check.

Critical user-facing behaviour: a BRCA1 variant with olaparib must NOT
trigger a warning (synthetic lethality context), and a BRCA1 variant with
tamoxifen MUST warn + suggest olaparib. Prior regression did this wrong.
"""

from __future__ import annotations

from api.services.analysis import _relevance_check


def test_olaparib_plus_brca1_is_relevant_via_synthetic_lethality() -> None:
    resolved = [{"gene_symbol": "BRCA1", "position": 61, "catalog_id": "BRCA1_C61G"}]
    warning, suggested = _relevance_check("olaparib", resolved)
    assert warning is None
    assert suggested == []


def test_tamoxifen_plus_brca1_warns_and_suggests_olaparib() -> None:
    resolved = [{"gene_symbol": "BRCA1", "position": 61, "catalog_id": "BRCA1_C61G"}]
    warning, suggested = _relevance_check("tamoxifen", resolved)
    assert warning is not None
    ids = {s.id for s in suggested}
    assert "olaparib" in ids, suggested


def test_tamoxifen_plus_cyp2d6_is_relevant_via_metabolism() -> None:
    resolved = [{"gene_symbol": "CYP2D6", "position": 0, "catalog_id": "CYP2D6_star4"}]
    warning, suggested = _relevance_check("tamoxifen", resolved)
    assert warning is None


def test_empty_variants_is_relevant_everywhere() -> None:
    for drug in ["olaparib", "tamoxifen", "capecitabine", "imatinib"]:
        warning, suggested = _relevance_check(drug, [])
        assert warning is None, f"unexpected warning for {drug} with no variants"


def test_capecitabine_plus_esr1_warns_and_suggests_hormone_drugs() -> None:
    resolved = [{"gene_symbol": "ESR1", "position": 537, "catalog_id": "ESR1_Y537S"}]
    warning, suggested = _relevance_check("capecitabine", resolved)
    assert warning is not None
    ids = {s.id for s in suggested}
    assert any(d in ids for d in ["tamoxifen", "fulvestrant"])
