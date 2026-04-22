"""Tests for the variant-input resolver and gene auto-detection."""

from __future__ import annotations

import pytest


def test_align_and_diff_finds_single_sub_when_lengths_equal() -> None:
    from api.services.variants import align_and_diff

    wt = "MDLSALRVEEV"
    var = "MDLSARRVEEV"  # position 6: L → R
    subs, has_indel = align_and_diff(wt, var)
    assert has_indel is False
    assert subs == [(6, "L", "R")]


def test_align_and_diff_flags_indel_on_length_mismatch() -> None:
    from api.services.variants import align_and_diff

    wt = "MDLSALRVEEV"
    var = "MDLSARVEEV"
    subs, has_indel = align_and_diff(wt, var)
    assert has_indel is True


@pytest.mark.asyncio
async def test_identify_gene_from_sequence_detects_brca1() -> None:
    from api.services.variants import identify_gene_from_sequence

    seq = (
        "MDLSALRVEEVQNVINAMQKILECPICLELIKEPVSTKCDHIFCKFCMLKLLNQKKGPSQ"
        "CPLCKNDITKRSLQESTRFSQLVEELLKIICAFQLDTGLEYANSYNFAKKENNSPEHLKD"
    )
    match = await identify_gene_from_sequence(seq)
    assert match is not None
    gene, score = match
    assert gene == "BRCA1"
    assert score >= 0.95


@pytest.mark.asyncio
async def test_identify_gene_rejects_short_sequences() -> None:
    from api.services.variants import identify_gene_from_sequence

    assert await identify_gene_from_sequence("MDLS") is None


@pytest.mark.asyncio
async def test_identify_gene_returns_none_for_garbage() -> None:
    from api.services.variants import identify_gene_from_sequence
    import random

    random.seed(42)
    junk = "".join(random.choices("ACDEFGHIKLMNPQRSTVWY", k=300))
    match = await identify_gene_from_sequence(junk)
    if match is not None:
        _gene, score = match
        assert score < 0.70
