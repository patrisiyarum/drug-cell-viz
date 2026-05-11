"""LangGraph agent that pulls variant evidence from 3 public databases
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
       ┌───────┴──────────────┬─────────────┐
       │                      │             │     (parallel)
   ┌───▼───┐             ┌────▼───┐   ┌────▼────┐
   │ClinVar│             │OpenFDA │   │ gnomAD  │
   └───┬───┘             └────┬───┘   └────┬────┘
       │                      │             │
       └──────────┬───────────┴─────────────┘
                  │
          ┌───────▼────────┐
          │   synthesize   │  Claude formats the evidence
          └───────┬────────┘
                  │
          ┌───────▼────────┐
          │     return     │
          └────────────────┘

Why a graph instead of a sequential chain:
    - The three lookups are independent. LangGraph runs them in parallel.
    - Failures don't cascade. If gnomAD is unreachable, the synthesis
      step still has ClinVar + OpenFDA to work with.
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

from api.agents.tools import clinvar, gnomad, openfda

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-4-7"
CLAUDE_TIMEOUT_SECONDS = 30.0

SYSTEM_PROMPT = """\
You are writing for a woman with cancer who has no medical training,
reading this on her phone. Be brief, warm, and plain-spoken.

You will be given a JSON dict of evidence from public clinical
databases (ClinVar, OpenFDA, gnomAD). Output ONLY a JSON object with
this exact schema:

{
  "pathogenicity": "<ONE short sentence. <=20 words. Lead with what this
                    mutation means for the patient in everyday words.
                    Translate any clinical term in parentheses on first
                    use, e.g. 'pathogenic (harmful)'. Always name ClinVar
                    as the source.>",
  "drugs": [
    {
      "generic": "<lowercase generic drug name>",
      "brand": "<brand name from the FDA label, or null>",
      "indication": "<<=8 words. Lead with the cancer type. e.g.
                      'For ovarian cancer with BRCA mutations.' Never
                      'Maintenance treatment of adult patients with...'>"
    }
  ],
  "rarity": "<ONE short sentence (<=15 words) about how rare this
              mutation is, or null if gnomAD failed. Use everyday words
              ('very rare', 'common') and convert scientific notation
              to '1 in N people'.>"
}

Hard rules:
  - Brevity wins. If a sentence reads long out loud, cut it.
  - No jargon by default. Translate clinical terms in parentheses on
    first use. Never lecture.
  - Skip sources that returned status='error', 'auth_required',
    'not_found', or 'no_curated_drugs'. Don't mention missing sources.
  - Don't invent values. If a brand is missing, return null.
  - Don't make treatment recommendations. Evidence only. Doctors prescribe.

Output ONLY the JSON. No markdown, no prose, no commentary.
"""


class AgentState(TypedDict, total=False):
    # Inputs
    gene: str
    hgvs_protein: str
    indication: str | None

    # Tool outputs (populated in parallel)
    clinvar: dict[str, Any]
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
    structured fields directly from the evidence dict in plain language,
    so the frontend's rendering doesn't need a separate code path."""
    cv = state.get("clinvar") or {}
    fda = state.get("openfda") or {}
    gn = state.get("gnomad") or {}

    pathogenicity = ""
    if cv.get("status") == "ok":
        sig = (cv.get("significance") or "").lower()
        plain_sig = _plain_significance(sig)
        pathogenicity = (
            f"ClinVar reports this {state['gene']} mutation as "
            f"{plain_sig}."
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
                # First clause of the FDA indication often runs ~200 words.
                # Trim hard for plain-English fallback.
                "indication": _plain_indication(d.get("indication_excerpt") or ""),
            })

    rarity: str | None = None
    if gn.get("status") == "absent":
        rarity = "This mutation is very rare — not seen in 800,000 people gnomAD has sequenced."
    elif gn.get("status") == "ok":
        af = gn.get("allele_frequency") or 0.0
        rarity = _plain_rarity(af)

    summary = _render_summary(pathogenicity, drugs, rarity)
    return {
        "pathogenicity": pathogenicity,
        "drugs": drugs,
        "rarity": rarity,
        "summary": summary + (f"\n\n[LLM-synthesis offline: {reason}]" if summary else f"[LLM-synthesis offline: {reason}]"),
        "model": "stub",
    }


def _plain_significance(sig: str) -> str:
    """Translate ClinVar's clinical-significance string into plain English."""
    sig = sig.lower()
    if "pathogenic" in sig and "likely" not in sig and "benign" not in sig:
        return "harmful (it raises cancer risk)"
    if "likely pathogenic" in sig:
        return "probably harmful (multiple labs lean toward raising cancer risk)"
    if "benign" in sig and "likely" not in sig:
        return "harmless"
    if "likely benign" in sig:
        return "probably harmless"
    if "uncertain" in sig or "vus" in sig:
        return "uncertain — not enough evidence yet to say"
    return sig or "unknown significance"


def _plain_indication(indication: str) -> str:
    """Strip a long FDA indication paragraph down to a plain phrase."""
    if not indication:
        return ""
    # Lower-case opening, keep first clause.
    first = indication.split(".")[0]
    # Drop boilerplate prefixes like "Maintenance treatment of adult
    # patients with deleterious or suspected deleterious germline or
    # somatic BRCA-mutated".
    drops = [
        "maintenance treatment of adult patients with",
        "treatment of adult patients with",
        "for the treatment of",
        "indicated for",
    ]
    f = first.strip()
    for d in drops:
        if f.lower().startswith(d):
            f = f[len(d):].strip()
            break
    if len(f) > 80:
        f = f[:80].rsplit(" ", 1)[0] + "…"
    return f or first


def _plain_rarity(af: float) -> str:
    """Translate gnomAD allele frequency into plain English."""
    if af <= 0:
        return "Not seen in gnomAD's general population — very rare."
    if af < 1e-5:
        return f"Extremely rare — fewer than 1 in 100,000 people carry it."
    if af < 1e-4:
        return f"Very rare — about 1 in {int(1 / af):,} people carry it."
    if af < 1e-3:
        return f"Rare — about 1 in {int(1 / af):,} people carry it."
    if af < 0.01:
        return f"Uncommon — about {af * 100:.2f}% of people carry it."
    return f"Common — about {af * 100:.1f}% of people carry it."


# ============================================================================
# Graph wiring
# ============================================================================


def build_graph() -> Any:
    """Compile the LangGraph state machine.

    Topology: START fans out to the three fetch nodes in parallel, all
    three converge on `synthesize`, which goes to END.
    """
    g = StateGraph(AgentState)

    g.add_node("fetch_clinvar", fetch_clinvar)
    g.add_node("fetch_openfda", fetch_openfda)
    g.add_node("fetch_gnomad", fetch_gnomad)
    g.add_node("synthesize", synthesize)

    # Parallel fan-out: START -> all three fetches simultaneously
    for node in ("fetch_clinvar", "fetch_openfda", "fetch_gnomad"):
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
        name for name in ("clinvar", "openfda", "gnomad")
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
            "openfda": result.get("openfda"),
            "gnomad": result.get("gnomad"),
        },
        "tool_calls_succeeded": succeeded,
        "tool_calls_attempted": ["clinvar", "openfda", "gnomad"],
        "duration_ms": duration_ms,
        "constrained": (
            "The synthesis step is constrained by a system prompt that "
            "forbids inventing claims not present in the retrieved "
            "evidence. The agent does not make treatment recommendations."
        ),
    }
