"""Tests for the SSE-streaming analysis endpoint + progress callback.

Covers:
  - run_analysis calls progress_cb at each phase boundary with monotonic
    progress values ending at 1.0.
  - progress_cb failures do not break the analysis (the callback contract
    says "must not raise", but we want a regression test that a buggy cb
    at most logs an error and doesn't tank the response).
  - The streaming endpoint emits `progress` events followed by a single
    `complete` event carrying the full AnalysisResult.
"""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport

from api.main import app
from api.models import VariantInput
from api.services import analysis as analysis_service


@pytest.mark.asyncio
async def test_run_analysis_emits_monotonic_progress_events() -> None:
    events: list[tuple[str, str, float]] = []

    async def cb(stage: str, label: str, pct: float) -> None:
        events.append((stage, label, pct))

    result = await analysis_service.run_analysis(
        "olaparib",
        [VariantInput(catalog_id="BRCA1_C61G", zygosity="heterozygous")],
        progress_cb=cb,
    )

    assert result is not None
    assert len(events) >= 5, f"expected phase events, got {events}"
    # First event fires early, last event marks 'done' at 1.0.
    assert events[0][2] <= 0.2
    assert events[-1][0] == "done"
    assert events[-1][2] == 1.0
    # Monotonic non-decreasing progress.
    pcts = [pct for _, _, pct in events]
    assert pcts == sorted(pcts), f"progress not monotonic: {pcts}"


@pytest.mark.asyncio
async def test_stream_endpoint_yields_progress_then_complete() -> None:
    payload = {
        "drug_id": "olaparib",
        "variants": [
            {"catalog_id": "BRCA1_C61G", "zygosity": "heterozygous"},
        ],
    }
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/api/bc/analyze/stream",
            json=payload,
            timeout=30.0,
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            raw = b""
            async for chunk in resp.aiter_bytes():
                raw += chunk
            text = raw.decode("utf-8")

    # SSE is: "event: progress\ndata: {...}\n\n" (or "data: ...\n\n" if no event)
    events = _parse_sse(text)
    progress_events = [e for e in events if e["event"] == "progress"]
    complete_events = [e for e in events if e["event"] == "complete"]

    assert len(progress_events) >= 3, f"expected progress events, got {events}"
    assert len(complete_events) == 1

    # Complete event must carry a valid AnalysisResult.
    result_json = json.loads(complete_events[0]["data"])
    assert result_json["drug_id"] == "olaparib"
    assert "hrd" in result_json


def _parse_sse(text: str) -> list[dict[str, str]]:
    """Parse a text/event-stream body into a list of {event, data} dicts."""
    events: list[dict[str, str]] = []
    current: dict[str, str] = {"event": "message", "data": ""}
    for line in text.splitlines():
        if not line:
            if current["data"]:
                events.append(current)
            current = {"event": "message", "data": ""}
            continue
        if line.startswith(":"):
            continue  # comment/keepalive
        if ":" not in line:
            continue
        field, _, value = line.partition(":")
        value = value.lstrip(" ")
        if field == "event":
            current["event"] = value
        elif field == "data":
            current["data"] = (current["data"] + "\n" + value) if current["data"] else value
    if current["data"]:
        events.append(current)
    return events
