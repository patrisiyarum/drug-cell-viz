"""Tests for the BRCA1 ensemble classifier (Tier-3)."""

from __future__ import annotations

import pytest


def _classify(hgvs: str) -> dict:
    from api.ml.infer import classify, parse_hgvs_protein

    ref, pos, alt = parse_hgvs_protein(hgvs)
    return classify(ref, pos, alt)


def test_well_known_pathogenic_cys61gly_is_lof() -> None:
    """BRCA1 p.Cys61Gly is the canonical RING-domain pathogenic variant."""
    r = _classify("p.Cys61Gly")
    assert r["label"] == "likely_loss_of_function", r
    assert r["probability_loss_of_function"] >= 0.70, r
    assert r["in_assayed_region"] is True
    assert r["domain"] == "RING"
    assert r["conformal"]["label"] == "loss_of_function"
    assert r["components"]["alphamissense_covered"] is True


def test_synonymous_variant_is_functional() -> None:
    r = _classify("p.Ala85Ala")
    assert r["label"] == "likely_functional", r
    assert r["probability_loss_of_function"] <= 0.30, r


def test_outside_assayed_region_flagged() -> None:
    r = _classify("p.K800E")
    assert r["in_assayed_region"] is False
    assert r["domain"] == "Linker1"


def test_accepts_both_one_letter_and_three_letter_notation() -> None:
    a = _classify("p.C61G")
    b = _classify("p.Cys61Gly")
    assert abs(a["probability_loss_of_function"] - b["probability_loss_of_function"]) < 1e-6


def test_invalid_hgvs_raises() -> None:
    from api.ml.infer import VariantParseError, parse_hgvs_protein

    for bad in ["", "garbage", "p.", "p.61", "p.X100Z"]:
        with pytest.raises(VariantParseError):
            parse_hgvs_protein(bad)


def test_components_report_honest_alphamissense_status() -> None:
    r = _classify("p.Ala85Ala")
    assert r["components"]["alphamissense_covered"] is False
    assert r["components"]["alphamissense_score"] is None


def test_metadata_contains_performance_numbers() -> None:
    from api.ml.infer import load_metadata

    m = load_metadata()
    assert "holdout_metrics" in m
    assert 0.5 < m["holdout_metrics"]["auroc"] <= 1.0
    assert "conformal" in m
