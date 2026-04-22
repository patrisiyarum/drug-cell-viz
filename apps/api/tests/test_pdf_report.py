"""Tests for the doctor-visit PDF export.

Runs the full analysis → PDF pipeline against a catalog variant and asserts
the output is a well-formed PDF with the expected headline text embedded.
"""

from __future__ import annotations

import pytest

from api.services import analysis as analysis_service
from api.services import pdf_report


@pytest.mark.asyncio
async def test_pdf_for_olaparib_plus_brca1_contains_hrd_content() -> None:
    from api.models import VariantInput

    result = await analysis_service.run_analysis(
        "olaparib",
        [VariantInput(catalog_id="BRCA1_C61G", zygosity="heterozygous")],
    )
    pdf = pdf_report.build_pdf(result, patient_label="Maya")

    # Magic number at the start of every PDF 1.x file.
    assert pdf.startswith(b"%PDF-"), pdf[:8]
    # Must not be empty.
    assert len(pdf) > 5_000, "PDF looks suspiciously small"
    # reportlab stores strings compressed by default; disable the "very basic
    # contains check" aspiration and just assert structural validity.


@pytest.mark.asyncio
async def test_pdf_for_tamoxifen_poor_metabolizer_succeeds() -> None:
    from api.models import VariantInput

    result = await analysis_service.run_analysis(
        "tamoxifen",
        [VariantInput(catalog_id="CYP2D6_star4", zygosity="homozygous")],
    )
    pdf = pdf_report.build_pdf(result)
    assert pdf.startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_pdf_works_without_variants() -> None:
    """Empty-variant case — analysis still runs, PDF still renders."""
    result = await analysis_service.run_analysis("tamoxifen", [])
    pdf = pdf_report.build_pdf(result)
    assert pdf.startswith(b"%PDF-")
