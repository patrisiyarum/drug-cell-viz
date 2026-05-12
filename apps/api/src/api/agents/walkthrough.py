"""Conversational walkthrough agent.

Talks the patient through her pharmacogenomic analysis results in plain
English. Has access to:
    - The structured analysis result (HRD score + label, drug + target,
      variants, patient indication, lab tile outputs the frontend has
      already computed).
    - Claude's native web_search tool, so it can pull current
      information (e.g. recent guideline changes, ongoing trials) and
      cite the source URLs back to the patient.

Implemented as a LangGraph state machine so the per-turn pipeline is
explicit and extensible:

    START
      |
      v
    build_context        — assembles the system prompt + context JSON
      |
      v
    call_claude          — invokes Anthropic with the web_search tool,
      |                    retries transient 5xx/529 with exp backoff
      v
    parse_response       — splits the FOLLOWUPS block out of the text
      |                    and dedupes web_search citations
      v
    END

Adding a new step later (custom tool node, indication-router, etc.)
just means wiring another node into the graph — see build_graph().

We keep this agent separate from `variant_evidence` because the two
have very different jobs:
    - variant_evidence is a one-shot, parallel-fan-out retrieval that
      returns structured fields (pathogenicity / drugs / rarity).
    - walkthrough is a stateful conversation that explains those
      results and answers follow-ups, allowed to search the web.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


# Transient Anthropic errors that should trigger a retry rather than be
# surfaced as a hard chat failure. 529 ("Overloaded") happens during
# capacity spikes on Anthropic's side; 429 is our rate limit. Both
# typically clear within a few seconds.
RETRYABLE_STATUS_CODES = {429, 503, 529}
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.5

CLAUDE_MODEL = "claude-opus-4-7"
CLAUDE_TIMEOUT_SECONDS = 60.0
MAX_TOKENS = 1500

SYSTEM_PROMPT = """\
You are talking with a woman who has cancer about her pharmacogenomic
results. She has no medical training. Be warm, plain-spoken, and brief.
Imagine she's reading on her phone in a waiting room.

You will be given:
  1. The full structured analysis result (drug, target gene, HRD label
     and score, variants, suggested drugs, off-target genes).
  2. The cancer type she entered (her indication).
  3. A `lab_results` dict containing the actual outputs of any lab
     tiles that have already run (CT imaging model, tumor scar score,
     HRDetect, BRCA1 DNA-repair classifier). If a tile is missing
     from `lab_results`, the patient hasn't run it yet — say so
     plainly ("the CT imaging model hasn't been run yet — open the
     Lab tab and click Run") rather than inventing a number.
  4. The conversation history.

When she asks about her lab results, ALWAYS quote the actual numbers
from `lab_results` (e.g. "your CT model put your HRD probability at
91% — that's the 'predicted_hr_deficient' bucket"). Don't generalize
about what the tile does without grounding it in her specific number.

Your job:
  - Help her understand what the results mean for her cancer.
  - Connect the dots across the lab tiles (HRD score, CT model,
     scar score, variant evidence) into a coherent story.
  - Answer follow-up questions in plain English.
  - When relevant, use the web_search tool to find current information
     (recent FDA approvals, guideline updates, ongoing trials for her
     specific indication). Cite sources when you do.

Hard rules:
  - You are NOT her doctor and NOT giving medical advice.
  - Never tell her to start, stop, or change a medication. Always
     redirect those questions back to her oncologist.
  - Don't invent results. If something isn't in the analysis context
     or the web search results, say you don't know.
  - Translate medical terms on first use ("pathogenic, meaning harmful").
  - Short replies. Two short paragraphs is usually enough.
  - When you cite a source, say where it's from (e.g. "according to
     the FDA label for olaparib") so she knows it's real.
  - DO NOT use any markdown formatting. No **bold**, no *italics*,
     no # headers, no `code`, no bullet points in the body of your
     reply. The chat renders text plain, so asterisks would show up
     as literal characters. Write everything as normal prose.

If the patient asks about something outside her cancer (e.g. a different
disease, a different drug class), politely note the tool is built for
her female-specific cancer context and redirect.

OUTPUT FORMAT — every reply must end with a follow-up block in this
exact format on its own lines, with no trailing text after it:

FOLLOWUPS:
- <one short question she might want to ask next, <=12 words>
- <a second short question, <=12 words>
- <a third short question, <=12 words>

The follow-ups should be concrete next questions tied to what you just
said — not generic prompts. If you can only think of two good ones,
return two. Never invent a topic outside her actual context to fill
the slots. The block will be parsed out and rendered as buttons; do
not number or punctuate the items differently.
"""

FOLLOWUPS_MARKER = "FOLLOWUPS:"


# ----------------------------------------------------------------------
# State definition
# ----------------------------------------------------------------------


class WalkthroughState(TypedDict, total=False):
    """LangGraph state for one turn of the chat.

    Inputs (set before invoke):
        messages: chat history (latest user turn last).
        context: structured analysis context (drug, HRD, lab_results, ...).

    Mutated through the graph:
        system_prompt: SYSTEM_PROMPT + the context JSON.
        raw_text: Claude's full assistant text BEFORE follow-up parsing.
        citations: web_search citations extracted from Claude's blocks.
        reply: visible text after the FOLLOWUPS block is stripped.
        followups: parsed list of suggested next questions.
        model: model id used (or "stub" when API key missing).
        duration_ms: wall-clock for the turn.
        error: human-readable error string when the turn could not be
            completed; takes the place of `reply` in the response.
    """

    messages: list[dict[str, str]]
    context: dict[str, Any]

    system_prompt: str
    raw_text: str
    citations: list[dict[str, str]]
    reply: str
    followups: list[str]
    model: str
    duration_ms: int
    error: str
    _start_time: float


# ----------------------------------------------------------------------
# Nodes
# ----------------------------------------------------------------------


def build_context(state: WalkthroughState) -> dict[str, Any]:
    """Assemble the system prompt: base instructions + analysis JSON.

    Pure transformation — no I/O. Keeps the prompt-construction logic
    inspectable as a discrete graph step instead of inlined into the
    LLM call.
    """
    context_json = json.dumps(state.get("context", {}), indent=2, default=str)
    return {
        "system_prompt": (
            SYSTEM_PROMPT + "\n\n--- ANALYSIS CONTEXT (JSON) ---\n" + context_json
        ),
        "_start_time": time.time(),
    }


async def call_claude(state: WalkthroughState) -> dict[str, Any]:
    """Call Anthropic with the web_search tool and retry transient errors.

    Returns either {raw_text, citations, model} on success or {error}
    on terminal failure. Parsing of follow-ups happens in the next node.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {
            "raw_text": "",
            "citations": [],
            "model": "stub",
            "error": (
                "The chat agent is offline because no ANTHROPIC_API_KEY "
                "is set on this server. Once it's configured, this is "
                "where I'd walk you through your results in plain English "
                "and answer your questions."
            ),
        }

    import anthropic

    # Anthropic's native server-side web_search tool. max_uses keeps a
    # chatty model from burning the API budget on trivial questions.
    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }
    ]

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=CLAUDE_TIMEOUT_SECONDS)

    msg = None
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            msg = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=state["system_prompt"],
                tools=tools,
                messages=state["messages"],
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            status = getattr(exc, "status_code", None)
            if status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                backoff = INITIAL_BACKOFF_SECONDS * (2**attempt)
                logger.warning(
                    "walkthrough chat got %s, retrying in %.1fs (attempt %d/%d)",
                    status, backoff, attempt + 1, MAX_RETRIES,
                )
                await asyncio.sleep(backoff)
                continue
            logger.exception("walkthrough chat failed (no more retries)")
            break

    if msg is None:
        status = getattr(last_exc, "status_code", None)
        friendly = (
            "Claude is briefly overloaded — try again in a few seconds."
            if status == 529
            else f"Something went wrong reaching the chat agent: {last_exc}. Try again in a moment."
        )
        return {
            "raw_text": "",
            "citations": [],
            "model": CLAUDE_MODEL,
            "error": friendly,
        }

    # Pull every text block + each block's web_search citations. The
    # web_search server-side tool emits citation objects inside text
    # blocks when it grounds a sentence on a source.
    text_parts: list[str] = []
    citations: list[dict[str, str]] = []
    for block in msg.content:
        if getattr(block, "type", None) != "text":
            continue
        text_parts.append(getattr(block, "text", ""))
        for cite in getattr(block, "citations", None) or []:
            url = getattr(cite, "url", None)
            title = getattr(cite, "title", None) or url
            if url:
                citations.append({"url": url, "title": title})

    # Dedupe citations by URL while preserving order.
    seen: set[str] = set()
    unique_citations: list[dict[str, str]] = []
    for c in citations:
        if c["url"] in seen:
            continue
        seen.add(c["url"])
        unique_citations.append(c)

    return {
        "raw_text": "".join(text_parts),
        "citations": unique_citations,
        "model": CLAUDE_MODEL,
    }


def parse_response(state: WalkthroughState) -> dict[str, Any]:
    """Split the FOLLOWUPS block out of the raw text. Pure transformation.

    If the model didn't include a FOLLOWUPS block, `followups` ends up
    empty and the entire raw text becomes the visible reply. If an
    earlier node populated `error`, we surface that as the reply.
    """
    t0 = state.get("_start_time", time.time())
    if state.get("error"):
        return {
            "reply": state["error"],
            "followups": [],
            "duration_ms": int((time.time() - t0) * 1000),
        }

    raw = state.get("raw_text", "")
    visible, followups = _parse_followups(raw)
    return {
        "reply": visible,
        "followups": followups,
        "duration_ms": int((time.time() - t0) * 1000),
    }


def _parse_followups(text: str) -> tuple[str, list[str]]:
    """Split the model's text into (reply_without_block, followups list).

    Looks for the literal "FOLLOWUPS:" marker. Everything before becomes
    the visible reply; everything after is parsed as a hyphenated list.
    Defensive: if the block is missing or malformed we just return the
    full text + empty list so the user still sees the reply.
    """
    if FOLLOWUPS_MARKER not in text:
        return _strip_markdown(text.strip()), []
    body, _, raw_block = text.partition(FOLLOWUPS_MARKER)
    items: list[str] = []
    for line in raw_block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(("-", "*", "•")):
            line = line[1:].strip()
        elif len(line) > 2 and line[0].isdigit() and line[1] in (".", ")"):
            line = line[2:].strip()
        if line:
            items.append(_strip_markdown(line))
    return _strip_markdown(body.strip()), items[:4]


# Bold / italic markers we strip from the visible reply because the
# chat bubble renders text plain (no markdown), so the literal
# asterisks would show up to the patient as characters.
_MARKDOWN_BOLD_RE = None
_MARKDOWN_ITALIC_RE = None


def _strip_markdown(text: str) -> str:
    """Remove markdown bold/italic markers from text. The chat renders
    with whitespace-pre-wrap, so anything like **word** would render as
    literal asterisks. We unwrap them rather than letting them through.
    """
    import re

    global _MARKDOWN_BOLD_RE, _MARKDOWN_ITALIC_RE
    if _MARKDOWN_BOLD_RE is None:
        # **bold** or __bold__, including across spaces but not newlines.
        _MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
        # *italic* or _italic_, only single markers, no newlines, and
        # only when not adjacent to word chars on the outside (so we
        # don't munge things like 5*10 = 50 or snake_case identifiers).
        _MARKDOWN_ITALIC_RE = re.compile(
            r"(?<![\w*])\*([^*\n]+)\*(?!\w)|(?<![\w_])_([^_\n]+)_(?!\w)"
        )

    text = _MARKDOWN_BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _MARKDOWN_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    return text


# ----------------------------------------------------------------------
# Graph wiring
# ----------------------------------------------------------------------


def build_graph() -> Any:
    """Compile the linear LangGraph pipeline.

    START -> build_context -> call_claude -> parse_response -> END.

    The graph is intentionally shallow today — the value of using
    LangGraph here is making each stage swappable. To add e.g. an
    indication-router node that picks a different model for trial
    questions vs. general explainer questions, insert a new node
    between build_context and call_claude with conditional edges.
    """
    g = StateGraph(WalkthroughState)
    g.add_node("build_context", build_context)
    g.add_node("call_claude", call_claude)
    g.add_node("parse_response", parse_response)

    g.add_edge(START, "build_context")
    g.add_edge("build_context", "call_claude")
    g.add_edge("call_claude", "parse_response")
    g.add_edge("parse_response", END)
    return g.compile()


_GRAPH = None


def graph() -> Any:
    """Lazy-compile the graph once at first use (cheap, but no need to
    pay the cost at import time when the module is loaded for tests)."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


# ----------------------------------------------------------------------
# Public entrypoint
# ----------------------------------------------------------------------


async def reply(
    messages: list[dict[str, str]],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Run one turn of the walkthrough conversation through the graph.

    Args:
        messages: chat history with the latest user turn last.
        context: structured analysis result + indication. Passed into
            the system prompt as JSON so the model can reason over it
            without separate tool calls to fetch it.

    Returns:
        {
            "reply": str,
            "citations": [{url, title}, ...],
            "followups": [str, ...],
            "model": str,
            "duration_ms": int,
        }
    """
    initial: WalkthroughState = {
        "messages": messages,
        "context": context,
    }
    result = await graph().ainvoke(initial)
    return {
        "reply": result.get("reply", ""),
        "citations": result.get("citations", []),
        "followups": result.get("followups", []),
        "model": result.get("model", "unknown"),
        "duration_ms": result.get("duration_ms", 0),
    }
