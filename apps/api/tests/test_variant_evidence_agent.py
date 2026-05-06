"""Smoke + integration tests for the variant-evidence agent.

These tests are designed to run without network access (the LangGraph
graph is exercised against monkey-patched tool functions) and without
an Anthropic API key (the synthesis step falls through to the stub
helper). When ANTHROPIC_API_KEY is set in the environment, a separate
test exercises the real Claude path; that test is skipped otherwise.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from api.agents import variant_evidence
from api.agents.tools import clinvar, cosmic, gnomad, openfda

pytestmark = pytest.mark.asyncio


# ----- Fixtures: known-good Maya BRCA1 p.Cys61Gly evidence ------------------

MAYA_CLINVAR = {
    "status": "ok",
    "variation_id": "55470",
    "title": "NM_007294.4(BRCA1):c.181T>G (p.Cys61Gly)",
    "significance": "Pathogenic",
    "review_status": "reviewed by expert panel",
    "last_evaluated": "2024-08-01",
    "conditions": ["Hereditary breast ovarian cancer syndrome"],
    "url": "https://www.ncbi.nlm.nih.gov/clinvar/variation/55470/",
    "raw_term": "BRCA1[gene] AND p.Cys61Gly",
    "gene": "BRCA1",
    "hgvs_protein": "p.Cys61Gly",
}

MAYA_COSMIC_AUTH_REQUIRED = {
    "status": "auth_required",
    "reason": "COSMIC API requires a personal access token (env: COSMIC_API_TOKEN).",
    "gene": "BRCA1",
    "hgvs_protein": "p.Cys61Gly",
}

MAYA_OPENFDA = {
    "status": "ok",
    "gene": "BRCA1",
    "drugs": [
        {
            "status": "ok",
            "generic_name": "olaparib",
            "brand_names": ["Lynparza"],
            "manufacturer": "AstraZeneca",
            "indication_excerpt": "Maintenance treatment of adult patients with deleterious or suspected deleterious germline or somatic BRCA-mutated advanced epithelial ovarian, fallopian tube or primary peritoneal cancer.",
            "set_id": "abc123",
            "label_url": "https://labels.fda.gov/abc123.xml",
        },
        {"status": "ok", "generic_name": "niraparib", "brand_names": ["Zejula"], "manufacturer": "GSK", "indication_excerpt": "...", "set_id": "def", "label_url": None},
    ],
    "n_drugs_curated": 4,
    "n_drugs_with_label": 2,
}

MAYA_GNOMAD = {
    "status": "absent",
    "reason": "Variant absent from gnomAD v4.",
    "gene": "BRCA1",
    "hgvs_protein": "p.Cys61Gly",
    "is_rare": True,
}


# ----- Tests --------------------------------------------------------------


async def test_agent_runs_end_to_end_with_stub_synthesis(monkeypatch):
    """The full graph runs with monkeypatched tools and the LLM-offline
    fallback path. Verifies parallel fan-out + state merge work."""
    async def fake_clinvar(g, h): return MAYA_CLINVAR
    async def fake_cosmic(g, h): return MAYA_COSMIC_AUTH_REQUIRED
    async def fake_openfda(g): return MAYA_OPENFDA
    async def fake_gnomad(g, h): return MAYA_GNOMAD

    monkeypatch.setattr(clinvar, "lookup_variant", fake_clinvar)
    monkeypatch.setattr(cosmic, "lookup_variant", fake_cosmic)
    monkeypatch.setattr(openfda, "drugs_for_gene", fake_openfda)
    monkeypatch.setattr(gnomad, "allele_frequency", fake_gnomad)

    # Force the synthesis step into stub mode by stripping the API key.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Force a fresh graph build to pick up the new monkey-patched fns.
    monkeypatch.setattr(variant_evidence, "_GRAPH", None)

    result = await variant_evidence.run_agent(
        gene="BRCA1",
        hgvs_protein="p.Cys61Gly",
        indication="ovarian cancer",
    )

    # All four tools attempted.
    assert result["tool_calls_attempted"] == ["clinvar", "cosmic", "openfda", "gnomad"]
    # ClinVar + OpenFDA succeeded; COSMIC auth_required and gnomAD absent
    # both have non-"ok" status, so they don't appear in succeeded list.
    assert "clinvar" in result["tool_calls_succeeded"]
    assert "openfda" in result["tool_calls_succeeded"]
    # The summary mentions ClinVar's pathogenic call (from the stub).
    assert "Pathogenic" in result["summary"]
    # The summary mentions FDA-approved drugs.
    assert "olaparib" in result["summary"].lower()
    # Constrained-by-prompt disclosure is in the response.
    assert "without making" not in result["constrained"]  # negative check
    assert "evidence" in result["constrained"].lower()


async def test_agent_handles_partial_tool_failures(monkeypatch):
    """If two tools fail, the agent still produces a summary from the
    remaining two. Demonstrates the parallel-graph's fault-tolerance."""
    async def fake_clinvar(g, h):
        return {"status": "error", "reason": "NCBI down", "gene": g, "hgvs_protein": h}
    async def fake_cosmic(g, h): return MAYA_COSMIC_AUTH_REQUIRED
    async def fake_openfda(g): return MAYA_OPENFDA
    async def fake_gnomad(g, h):
        return {"status": "error", "reason": "GraphQL 502", "gene": g, "hgvs_protein": h}

    monkeypatch.setattr(clinvar, "lookup_variant", fake_clinvar)
    monkeypatch.setattr(cosmic, "lookup_variant", fake_cosmic)
    monkeypatch.setattr(openfda, "drugs_for_gene", fake_openfda)
    monkeypatch.setattr(gnomad, "allele_frequency", fake_gnomad)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(variant_evidence, "_GRAPH", None)

    result = await variant_evidence.run_agent(
        gene="BRCA1",
        hgvs_protein="p.Cys61Gly",
    )

    # Only OpenFDA returned ok; ClinVar errored, gnomAD errored, COSMIC auth-required.
    assert result["tool_calls_succeeded"] == ["openfda"]
    # The agent didn't crash and still emitted a summary.
    assert result["summary"]
    assert result["evidence"]["clinvar"]["status"] == "error"
    assert result["evidence"]["gnomad"]["status"] == "error"


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY", "").strip(),
    reason="Requires ANTHROPIC_API_KEY for the real Claude synthesis step",
)
async def test_agent_with_real_claude(monkeypatch):
    """Integration test: the real Claude API formats the evidence dict.
    Skipped when ANTHROPIC_API_KEY isn't set in CI."""
    async def fake_clinvar(g, h): return MAYA_CLINVAR
    async def fake_cosmic(g, h): return MAYA_COSMIC_AUTH_REQUIRED
    async def fake_openfda(g): return MAYA_OPENFDA
    async def fake_gnomad(g, h): return MAYA_GNOMAD

    monkeypatch.setattr(clinvar, "lookup_variant", fake_clinvar)
    monkeypatch.setattr(cosmic, "lookup_variant", fake_cosmic)
    monkeypatch.setattr(openfda, "drugs_for_gene", fake_openfda)
    monkeypatch.setattr(gnomad, "allele_frequency", fake_gnomad)
    monkeypatch.setattr(variant_evidence, "_GRAPH", None)

    result = await variant_evidence.run_agent(
        gene="BRCA1",
        hgvs_protein="p.Cys61Gly",
        indication="ovarian cancer",
    )

    # Real Claude output should mention the constrained sources.
    s = result["summary"].lower()
    assert "clinvar" in s
    assert "olaparib" in s or "parp" in s
    # And the model name should be the real one, not "stub".
    assert result["model"].startswith("claude-")
