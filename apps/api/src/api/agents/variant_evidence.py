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

Your job is to write a 3–5 sentence summary that:
  • Reports what the retrieved evidence shows.
  • Names the source of every claim (e.g. "ClinVar classifies this as
    pathogenic" not "this is pathogenic").
  • Flags missing or uncertain data instead of glossing over it. If
    COSMIC returned auth_required or gnomAD returned absent, say so.
  • Mentions the labeled drug indications when OpenFDA returned drugs.

You MUST NOT:
  • Invent any clinical claim that isn't in the evidence dict.
  • Make a treatment recommendation. The agent points at evidence; it
    does not prescribe.
  • Use hedging language to imply more certainty than the data provides.

Voice: clear, concrete, neutral. Patient-readable but not condescending.
The output is a single paragraph of plain text — no markdown, no headers,
no bullet points.
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

    # Synthesis
    summary: str
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
    """Format the four evidence dicts into a single patient-readable paragraph.

    The LLM is constrained to *describing* the retrieved data, not
    inventing new claims. The system prompt enforces this and we surface
    the constraint in the response so users can audit it.
    """
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
        "Write the summary."
    )

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=CLAUDE_TIMEOUT_SECONDS)
    try:
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
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

    return {"summary": text.strip(), "model": CLAUDE_MODEL}


def _stub_synthesis(state: AgentState, reason: str) -> dict[str, Any]:
    """Fallback summary when the LLM step can't run. Surfaces the raw
    evidence as a structured paragraph so the agent still produces
    *something* useful even without Claude."""
    parts: list[str] = []
    cv = state.get("clinvar") or {}
    if cv.get("status") == "ok":
        parts.append(
            f"ClinVar classifies {state['gene']} {state['hgvs_protein']} as "
            f"{cv.get('significance', 'unspecified')} "
            f"(review status: {cv.get('review_status', 'unknown')})."
        )
    fda = state.get("openfda") or {}
    if fda.get("status") == "ok":
        drug_names = [d["generic_name"] for d in fda.get("drugs", []) if d.get("status") == "ok"]
        if drug_names:
            parts.append(
                f"FDA-approved drugs targeting {state['gene']}: {', '.join(drug_names)}."
            )
    gn = state.get("gnomad") or {}
    if gn.get("status") in ("ok", "absent"):
        if gn.get("status") == "absent":
            parts.append("gnomAD: variant absent from 800,000 sequenced individuals (consistent with rare).")
        else:
            af = gn.get("allele_frequency", 0.0)
            parts.append(f"gnomAD allele frequency: {af:.6g} (rare: {gn.get('is_rare', False)}).")
    parts.append(f"[LLM-synthesis offline: {reason}]")
    return {"summary": " ".join(parts), "model": "stub"}


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
