"""Tests for the HRDetect-style genomic-scar scorer + its API endpoint.

Pins:
  - label thresholds align with the Myriad myChoice 42 / 33 cutoffs
  - negative feature counts raise
  - POST /api/hrd/scars returns the scoring + caveats
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from api.main import app
from api.services.hrd_scars import (
    HRD_BORDERLINE_CUTOFF,
    HRD_POSITIVE_CUTOFF,
    HrdScarFeatures,
    score,
)


def test_positive_scar_burden_is_hr_deficient() -> None:
    # Classic HR-deficient tumor profile: lots of LOH, many LST, high NTAI.
    s = score(HrdScarFeatures(loh=25, lst=30, ntai=15))
    assert s.label == "hr_deficient_scar"
    assert s.hrd_sum == 70
    assert s.hrd_sum >= HRD_POSITIVE_CUTOFF


def test_borderline_scar_burden_routes_to_borderline() -> None:
    # Right at the borderline band (33-41).
    s = score(HrdScarFeatures(loh=15, lst=12, ntai=8))
    assert s.label == "borderline_scar"
    assert HRD_BORDERLINE_CUTOFF <= s.hrd_sum < HRD_POSITIVE_CUTOFF


def test_low_scar_burden_is_hr_proficient() -> None:
    s = score(HrdScarFeatures(loh=3, lst=5, ntai=2))
    assert s.label == "hr_proficient_scar"
    assert s.hrd_sum == 10


def test_exact_cutoff_is_hr_deficient() -> None:
    # The cutoff is inclusive: 42 counts as positive.
    s = score(HrdScarFeatures(loh=14, lst=14, ntai=14))
    assert s.hrd_sum == HRD_POSITIVE_CUTOFF
    assert s.label == "hr_deficient_scar"


def test_negative_counts_reject() -> None:
    with pytest.raises(ValueError):
        score(HrdScarFeatures(loh=-1, lst=0, ntai=0))


@pytest.mark.asyncio
async def test_api_endpoint_returns_scoring() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/hrd/scars",
            json={"loh": 20, "lst": 18, "ntai": 10},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["hrd_sum"] == 48
    assert body["label"] == "hr_deficient_scar"
    assert len(body["caveats"]) >= 2
    assert "Myriad" in body["summary"] or "scar" in body["summary"].lower()


@pytest.mark.asyncio
async def test_api_endpoint_rejects_negative_counts() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/hrd/scars",
            json={"loh": -1, "lst": 0, "ntai": 0},
        )
    # Pydantic validation kicks in before the handler runs, returning 422.
    assert resp.status_code == 422
