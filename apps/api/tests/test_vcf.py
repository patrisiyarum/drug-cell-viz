"""Tests for VCF ingestion.

Fixture: `tests/fixtures/test_sample.vcf` is a 6-record synthetic VCF with
hg38 coordinates that exactly match our catalog coordinate map. Verifies:
  - every catalog coordinate resolves
  - zygosity extraction from GT field
  - PASS/LowQual filter is surfaced but doesn't drop records
  - detections feed cleanly into the run_analysis pipeline
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "test_sample.vcf"


def _ingest():
    from api.services.vcf import ingest

    return ingest(FIXTURE)


def test_fixture_exists() -> None:
    assert FIXTURE.exists(), "synthetic VCF fixture is missing"


def test_ingests_all_records() -> None:
    r = _ingest()
    assert r.total_records == 5
    # 4 PASS + 1 LowQual
    assert r.records_pass == 4


def test_detects_every_catalog_variant_in_fixture() -> None:
    r = _ingest()
    ids = {d.catalog_id for d in r.detections}
    # Every BC-relevant coordinate in the fixture should resolve.
    assert ids == {
        "DPYD_c2846A_T",
        "DPYD_star2A",
        "BRCA1_C61G",
        "CYP2D6_star4",
    }


def test_zygosity_read_from_gt_field() -> None:
    r = _ingest()
    zyg = {d.catalog_id: d.zygosity for d in r.detections}
    # Fixture INFO note documents the intended genotype per record.
    assert zyg["DPYD_c2846A_T"] == "heterozygous"
    assert zyg["DPYD_star2A"] == "heterozygous"
    assert zyg["BRCA1_C61G"] == "heterozygous"
    assert zyg["CYP2D6_star4"] == "homozygous"


def test_detections_flow_into_variant_inputs() -> None:
    from api.services.vcf import detections_to_variant_inputs

    r = _ingest()
    variants = detections_to_variant_inputs(r.detections)
    # 4 distinct catalog_ids → 4 VariantInputs (no duplicates).
    assert len(variants) == 4
    catalog_ids = {v.catalog_id for v in variants}
    assert "CYP2D6_star4" in catalog_ids
    assert "BRCA1_C61G" in catalog_ids


@pytest.mark.asyncio
async def test_fixture_plus_tamoxifen_produces_caution_verdict() -> None:
    """End-to-end: VCF fixture feeds the analysis pipeline, which should pick up
    the homozygous CYP2D6*4 and emit the tamoxifen poor-metabolizer verdict."""
    from api.services import analysis as analysis_service
    from api.services.vcf import detections_to_variant_inputs

    r = _ingest()
    variants = detections_to_variant_inputs(r.detections)
    result = await analysis_service.run_analysis("tamoxifen", variants)
    # Must fire the CPIC PGx rule for CYP2D6*4 homozygous → poor metabolizer.
    phenotypes = {v.phenotype.lower() for v in result.pgx_verdicts}
    assert any("poor metabolizer" in p for p in phenotypes), result.pgx_verdicts


def test_count_supported_coordinates_is_stable() -> None:
    from api.services.vcf import count_supported_coordinates

    # 4 distinct catalog variants reachable via chrom/pos: CYP2D6*4, DPYD*2A,
    # DPYD c.2846A>T, BRCA1_C61G.
    assert count_supported_coordinates() == 4
