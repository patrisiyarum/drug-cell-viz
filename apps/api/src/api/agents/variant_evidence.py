"""LangGraph agent that pulls variant evidence from 4 public databases
and synthesizes it into a clinician-ready summary.

Architecture:

    ┌──────────────────────┐
    │   /api/agent/...     │  user request: {gene, variant, indication}
    └──────────┬───────────┘
               │
       ┌───────┴───────┐
       │  build_state  │  initialize evidence dict
       └───────┬───────┘
               │
       ┌───────┴────────┬──────────────┬─────────────┐
       │                │              │             │     (parallel)
   ┌───▼───┐       ┌────▼────┐    ┌────▼───┐   ┌────▼────┐
   │ClinVar│       │ COSMIC  │    │OpenFDA │   │ gnomAD  │
   └───┬───┘       └────┬────┘    └────┬───┘   └────┬────┘
       │                │              │             │
       └───────┬────────┴──────────────┴─────────────┘
               │
       ┌───────▼────────┐
       │   synthesize   │  Claude formats the evidence
       └───────┬────────┘
               │
       ┌───────▼────────┐
       │     return     │
       └────────────────┘

Why a graph instead of a sequential chain:
    - The four lookups are independent. LangGraph runs them in parallel.
    - Failures don't cascade. If COSMIC's API key is missing, the
      synthesis step still has ClinVar + OpenFDA + gnomAD to work with.
    - The graph is a real artifact you can show in a demo (visualize via
      `app.get_graph().draw_ascii()`).

Why constrain Claude to formatting:
    Medical AI hallucination is the failure mode that destroys trust.
    The system prompt explicitly forbids the model from inventing claims
    that aren't in the retrieved evidence. The model's job is *formatting*
    the evidence dict into clinician-readable English, not making
    medical recommendations. We surface that constraint to the user
    in the response too — so they know the LLM didn't fabricate anything.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from api.agents.tools import clinvar, cosmic, gnomad, openfda

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
CLAUDE_TIMEOUT_SECONDS = 30.0

SYSTEM_PROMPT = """\
You are a clinical-evidence formatter for a patient-facing cancer-treatment
app. You will be given a JSON dict of evidence retrieved from four public
clinical databases: ClinVar, COSMIC, OpenFDA, and gnomAD.

Output ONLY a JSON object that conforms exactly to this schema:

{
  "pathogenicity": "<2-3 sentence summary of what ClinVar (and similar
                    pathogenicity sources) report about this variant.
                    Name ClinVar specifically. Mention the conditions it
                    is associated with and the review-status quality.>",
  "drugs": [
    {
      "generic": "<lowercase generic drug name, e.g. 'olaparib'>",
      "brand": "<brand name from the FDA label, or null if not present>",
      "indication": "<one-line plain-English summary of the labeled
                      indication. Cancer type + maintenance/treatment role.
                      Keep under 20 words.>"
    }
  ],
  "rarity": "<optional 1-sentence claim about population frequency, ONLY
              if gnomAD returned status='ok' or status='absent' with
              meaningful data. Use null if gnomAD failed.>"
}

Rules — followed strictly:
  • Only describe data from sources that returned status="ok" (or
    "absent" for gnomAD, which is itself a useful answer). SKIP sources
    that returned status="error", "auth_required", "not_found", or
    "no_curated_drugs". Do NOT mention what failed. Do NOT mention
    missing sources.
  • One drug entry per OpenFDA hit with status="ok". Do NOT include
    drugs that returned status="missing".
  • Do NOT invent any value that isn't in the evidence dict. If a brand
    is not in the OpenFDA payload, set brand to null.
  • Do NOT make treatment recommendations. The agent reports evidence;
    it does not prescribe.

Output ONLY the JSON. No markdown, no prose before or after, no commentary.
"""


class AgentState(TypedDict, total=False):
    # Inputs
    gene: str
    hgvs_protein: str
    indication: str | None

    # Tool outputs (populated in parallel)
    clinvar: dict[str, Any]
    cosmic: dict[str, Any]
    openfda: dict[str, Any]
    gnomad: dict[str, Any]

    # Synthesis (structured — Claude returns JSON we parse into fields)
    pathogenicity: str
    drugs: list[dict[str, Any]]  # {generic, brand, indication}
    rarity: str | None
    summary: str  # backward-compat: rendered text version of the above
    model: str
    duration_ms: int
    tool_calls_succeeded: list[str]
    tool_calls_attempted: list[str]


# ============================================================================
# Tool nodes — each one calls a single public DB, writes its result into
# the state under a known key, and returns the partial state update.
# LangGraph merges parallel partial updates automatically.
# ============================================================================


async def fetch_clinvar(state: AgentState) -> dict[str, Any]:
    result = await clinvar.lookup_variant(state["gene"], state["hgvs_protein"])
    return {"clinvar": result}


async def fetch_cosmic(state: AgentState) -> dict[str, Any]:
    result = await cosmic.lookup_variant(state["gene"], state["hgvs_protein"])
    return {"cosmic": result}


async def fetch_openfda(state: AgentState) -> dict[str, Any]:
    result = await openfda.drugs_for_gene(state["gene"])
    return {"openfda": result}


async def fetch_gnomad(state: AgentState) -> dict[str, Any]:
    result = await gnomad.allele_frequency(state["gene"], state["hgvs_protein"])
    return {"gnomad": result}


# ============================================================================
# Synthesis node — Claude formats the evidence dict into prose, with the
# constraint that it can only describe what's already in the dict.
# ============================================================================


async def synthesize(state: AgentState) -> dict[str, Any]:
    """Format the four evidence dicts into structured JSON sections.

    Claude returns a JSON object with `pathogenicity` (prose paragraph),
    `drugs` (list of {generic, brand, indication}), and optional
    `rarity` (one-sentence allele-frequency claim). The agent parses the
    JSON, falls back to the structured stub on any parsing or API
    failure, and surfaces both the structured fields and a flat `summary`
    string (built from those fields) for non-UI consumers like the PDF.
    """
    import json

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return _stub_synthesis(
            state,
            reason="ANTHROPIC_API_KEY is unset — the agent ran the tool calls "
                   "successfully but the LLM-formatting step is offline.",
        )

    evidence = {
        "clinvar": state.get("clinvar", {}),
        "cosmic": state.get("cosmic", {}),
        "openfda": state.get("openfda", {}),
        "gnomad": state.get("gnomad", {}),
    }
    user_message = (
        f"Variant: {state['gene']} {state['hgvs_protein']}\n"
        f"Patient indication: {state.get('indication') or 'unspecified'}\n\n"
        f"Evidence retrieved from public databases:\n"
        f"{evidence}\n\n"
        "Return the JSON object."
    )

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=CLAUDE_TIMEOUT_SECONDS)
    try:
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        # Pull the text out of the first content block.
        text = ""
        for block in message.content:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "")
                break
    except Exception as exc:  # noqa: BLE001
        logger.exception("Claude synthesis failed")
        return _stub_synthesis(state, reason=f"Claude synthesis failed: {exc}")

    # Parse the JSON. Be defensive — sometimes the model wraps it in a
    # markdown fence or prepends a courtesy sentence despite the prompt.
    payload = _extract_json(text)
    if payload is None:
        logger.warning("Claude returned non-JSON; falling back to stub. Output was: %r", text[:200])
        return _stub_synthesis(state, reason="Claude returned non-JSON output")

    pathogenicity = str(payload.get("pathogenicity") or "").strip()
    drugs_raw = payload.get("drugs") or []
    drugs: list[dict[str, Any]] = []
    for d in drugs_raw:
        if not isinstance(d, dict):
            continue
        generic = (d.get("generic") or "").strip()
        if not generic:
            continue
        drugs.append({
            "generic": generic,
            "brand": (d.get("brand") or None),
            "indication": (d.get("indication") or "").strip(),
        })
    rarity = payload.get("rarity")
    if isinstance(rarity, str):
        rarity = rarity.strip() or None

    summary = _render_summary(pathogenicity, drugs, rarity)

    return {
        "pathogenicity": pathogenicity,
        "drugs": drugs,
        "rarity": rarity,
        "summary": summary,
        "model": CLAUDE_MODEL,
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    """Tolerantly parse the LLM's response. Strips markdown fences if
    present, then takes the first { ... } block. Returns None if no
    valid JSON object can be recovered."""
    import json

    s = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences if Claude added them.
    if s.startswith("```"):
        s = s.strip("`")
        # Drop a leading "json" language tag.
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
    # Find the first {...} block.
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(s[start : end + 1])
    except Exception:  # noqa: BLE001
        return None


def _render_summary(
    pathogenicity: str,
    drugs: list[dict[str, Any]],
    rarity: str | None,
) -> str:
    """Build a flat-text rendering of the structured synthesis. Used by
    the PDF generator and any other consumer that expects a single
    string field. The frontend renders the structured fields directly."""
    parts: list[str] = []
    if pathogenicity:
        parts.append(pathogenicity)
    if drugs:
        drug_lines = []
        for d in drugs:
            label = f"{d['generic']}"
            if d.get("brand"):
                label += f" ({d['brand']})"
            if d.get("indication"):
                label += f" — {d['indication']}"
            drug_lines.append(label)
        parts.append("FDA-approved drugs:\n" + "\n".join(f"  • {line}" for line in drug_lines))
    if rarity:
        parts.append(rarity)
    return "\n\n".join(parts)


def _stub_synthesis(state: AgentState, reason: str) -> dict[str, Any]:
    """Fallback synthesis when the LLM step can't run. Builds the same
    structured fields directly from the evidence dict so the frontend's
    rendering doesn't need a separate code path."""
    cv = state.get("clinvar") or {}
    fda = state.get("openfda") or {}
    gn = state.get("gnomad") or {}

    pathogenicity = ""
    if cv.get("status") == "ok":
        pathogenicity = (
            f"ClinVar classifies {state['gene']} {state['hgvs_protein']} as "
            f"{cv.get('significance', 'unspecified')} "
            f"(review status: {cv.get('review_status', 'unknown')})."
        )

    drugs: list[dict[str, Any]] = []
    if fda.get("status") == "ok":
        for d in fda.get("drugs", []) or []:
            if d.get("status") != "ok":
                continue
            brand_list = d.get("brand_names") or []
            drugs.append({
                "generic": d.get("generic_name", ""),
                "brand": brand_list[0] if brand_list else None,
                "indication": (d.get("indication_excerpt") or "").split(".")[0][:200],
            })

    rarity: str | None = None
    if gn.get("status") == "absent":
        rarity = "Variant is absent from gnomAD's 800,000 sequenced individuals — consistent with rare."
    elif gn.get("status") == "ok":
        af = gn.get("allele_frequency") or 0.0
        rarity = f"gnomAD reports an allele frequency of {af:.6g} in the general population."

    summary = _render_summary(pathogenicity, drugs, rarity)
    return {
        "pathogenicity": pathogenicity,
        "drugs": drugs,
        "rarity": rarity,
        "summary": summary + (f"\n\n[LLM-synthesis offline: {reason}]" if summary else f"[LLM-synthesis offline: {reason}]"),
        "model": "stub",
    }


# ============================================================================
# Graph wiring
# ============================================================================


def build_graph() -> Any:
    """Compile the LangGraph state machine.

    Topology: START fans out to the four fetch nodes in parallel, all
    four converge on `synthesize`, which goes to END.
    """
    g = StateGraph(AgentState)

    g.add_node("fetch_clinvar", fetch_clinvar)
    g.add_node("fetch_cosmic", fetch_cosmic)
    g.add_node("fetch_openfda", fetch_openfda)
    g.add_node("fetch_gnomad", fetch_gnomad)
    g.add_node("synthesize", synthesize)

    # Parallel fan-out: START -> all four fetches simultaneously
    for node in ("fetch_clinvar", "fetch_cosmic", "fetch_openfda", "fetch_gnomad"):
        g.add_edge(START, node)
        g.add_edge(node, "synthesize")

    g.add_edge("synthesize", END)
    return g.compile()


# Compile once at import — graph is stateless, threadsafe, reusable.
_GRAPH = None


def graph() -> Any:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


async def run_agent(
    gene: str,
    hgvs_protein: str,
    indication: str | None = None,
) -> dict[str, Any]:
    """Run the full agent pipeline. Returns a dict with the summary,
    every tool's structured output, and metadata (duration, model, which
    tool calls actually succeeded).

    This is the API-facing entrypoint.
    """
    t0 = time.time()
    state: AgentState = {
        "gene": gene,
        "hgvs_protein": hgvs_protein,
        "indication": indication,
    }
    result = await graph().ainvoke(state)
    duration_ms = int((time.time() - t0) * 1000)

    succeeded = [
        name for name in ("clinvar", "cosmic", "openfda", "gnomad")
        if (result.get(name) or {}).get("status") == "ok"
    ]
    return {
        "gene": gene,
        "hgvs_protein": hgvs_protein,
        "indication": indication,
        # Structured synthesis (the frontend renders these directly).
        "pathogenicity": result.get("pathogenicity", ""),
        "drugs": result.get("drugs", []),
        "rarity": result.get("rarity"),
        # Flat-text rendering for non-UI consumers (PDF, CLI, etc).
        "summary": result.get("summary", ""),
        "model": result.get("model", "unknown"),
        "evidence": {
            "clinvar": result.get("clinvar"),
            "cosmic": result.get("cosmic"),
            "openfda": result.get("openfda"),
            "gnomad": result.get("gnomad"),
        },
        "tool_calls_succeeded": succeeded,
        "tool_calls_attempted": ["clinvar", "cosmic", "openfda", "gnomad"],
        "duration_ms": duration_ms,
        "constrained": (
            "The synthesis step is constrained by a system prompt that "
            "forbids inventing claims not present in the retrieved "
            "evidence. The agent does not make treatment recommendations."
        ),
    }
