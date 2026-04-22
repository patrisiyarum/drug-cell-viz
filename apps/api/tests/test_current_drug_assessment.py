"""Tests for the 'is this drug right for me?' assessment.

The 'second opinion' use case: a patient already on a medication, plus
known variants, gets an explicit verdict instead of having to infer one
from CPIC rule text.
"""

from __future__ import annotations

import pytest

from api.models import VariantInput
from api.services import analysis as analysis_service


@pytest.mark.asyncio
async def test_olaparib_plus_brca1_pathogenic_is_well_matched() -> None:
    """Germline BRCA1+ on olaparib — an FDA biomarker match."""
    result = await analysis_service.run_analysis(
        "olaparib",
        [VariantInput(catalog_id="BRCA1_C61G", zygosity="heterozygous")],
    )
    assert result.current_drug_assessment is not None
    assert result.current_drug_assessment.verdict == "well_matched"
    assert "olaparib" in result.current_drug_assessment.headline.lower()
    assert result.current_drug_assessment.better_options == []


@pytest.mark.asyncio
async def test_tamoxifen_plus_poor_metabolizer_needs_review() -> None:
    """CYP2D6*4/*4 on tamoxifen — CPIC says consider alternatives."""
    result = await analysis_service.run_analysis(
        "tamoxifen",
        [VariantInput(catalog_id="CYP2D6_star4", zygosity="homozygous")],
    )
    assert result.current_drug_assessment is not None
    assert result.current_drug_assessment.verdict == "review_needed"
    assert "oncologist" in result.current_drug_assessment.headline.lower() or \
           "review" in result.current_drug_assessment.headline.lower()


@pytest.mark.asyncio
async def test_capecitabine_plus_dpyd_homozygous_flags_avoid() -> None:
    """Homozygous DPYD*2A + capecitabine is explicitly contraindicated."""
    result = await analysis_service.run_analysis(
        "capecitabine",
        [VariantInput(catalog_id="DPYD_star2A", zygosity="homozygous")],
    )
    assert result.current_drug_assessment is not None
    assert result.current_drug_assessment.verdict == "review_needed"
    # Rationale should cite the avoid recommendation
    assert "avoid" in result.current_drug_assessment.rationale.lower() or \
           "fluoropyrimidine" in result.current_drug_assessment.rationale.lower()


@pytest.mark.asyncio
async def test_tamoxifen_plus_brca1_warns_and_surfaces_olaparib() -> None:
    """BRCA1 variant on tamoxifen — wrong pathway. Should flag + suggest olaparib."""
    result = await analysis_service.run_analysis(
        "tamoxifen",
        [VariantInput(catalog_id="BRCA1_C61G", zygosity="heterozygous")],
    )
    cda = result.current_drug_assessment
    assert cda is not None
    assert cda.verdict == "review_needed"
    better_ids = {b.id for b in cda.better_options}
    assert "olaparib" in better_ids


@pytest.mark.asyncio
async def test_empty_variants_returns_unknown() -> None:
    result = await analysis_service.run_analysis("tamoxifen", [])
    assert result.current_drug_assessment is not None
    assert result.current_drug_assessment.verdict == "unknown"
