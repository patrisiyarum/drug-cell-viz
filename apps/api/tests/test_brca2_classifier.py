"""Tests for the BRCA2 DBD v0 classifier."""

from __future__ import annotations


def _classify(hgvs: str) -> dict:
    from api.ml.infer_brca2 import classify, parse_hgvs_protein

    ref, pos, alt = parse_hgvs_protein(hgvs)
    return classify(ref, pos, alt)


def test_known_pathogenic_variant_scores_positive() -> None:
    r = _classify("p.D2723H")
    assert r["in_assayed_region"] is True
    assert r["probability_pathogenic"] >= 0.55


def test_outside_dbd_is_flagged() -> None:
    r = _classify("p.E1000K")
    assert r["in_assayed_region"] is False


def test_metadata_present() -> None:
    from api.ml.infer_brca2 import load_metadata

    m = load_metadata()
    assert m.get("model_version") == "brca2_xgb_v1"
    assert 0.5 < m["holdout_metrics"]["auroc"] <= 1.0
