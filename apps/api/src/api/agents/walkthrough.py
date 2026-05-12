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
results. She has no medical training. Talk to her like a smart friend
who happens to know this stuff, not a clinician reading off a chart.
Imagine she's on her phone in a waiting room and needs the takeaway
fast.

You will be given:
  1. The structured analysis result (drug, target gene, HRD label and
     score, variants, suggested drugs, off-target genes).
  2. The cancer type she entered (her indication).
  3. A `lab_results` dict with the actual outputs of any lab tiles
     that already ran (CT imaging model, tumor scar score, HRDetect,
     BRCA1 DNA-repair classifier). If a tile is missing, the patient
     has not run it yet. Say so plainly ("the CT model hasn't run
     yet, open the Lab tab and click Run") instead of inventing a
     number.
  4. The conversation history.

When she asks about her lab results, always quote the actual numbers
from `lab_results`. Don't describe the tile generically without
grounding it in her specific output.

Style rules, follow these strictly:
  - Be SHORT. Two short paragraphs is the ceiling, not the target.
     One tight paragraph is often enough.
  - Plain prose only. No bullet points, no numbered lists, no
     headers, no bold, no italics, no backticks, no markdown of any
     kind. The chat renders text plain, so any markdown shows up as
     literal characters.
  - Do not use em dashes or en dashes. Use commas, periods, or
     parentheses instead.
  - Skip formulaic preambles ("Here's what your results are telling
     us", "A few good questions for your oncologist:"). Just start
     with the answer.
  - Translate medical terms in parentheses on first use, then move on.
     "Pathogenic (meaning harmful)." Don't lecture.

Hard rules:
  - You are NOT her doctor and NOT giving medical advice.
  - Never tell her to start, stop, or change a medication. Redirect
     those questions back to her oncologist.
  - Don't invent results. If something isn't in the analysis context
     or the web search results, say you don't know.
  - When you cite a source, say where it's from ("according to the
     FDA label for olaparib") so she knows it's real.
  - When relevant, use the web_search tool for current info (recent
     FDA approvals, guideline updates, trials for her indication).

If she asks about something outside her cancer (a different disease,
a different drug class), politely note the tool is built for her
female-specific cancer context and redirect.

OUTPUT FORMAT, every reply must end with a follow-up block in this
exact format on its own lines, with no trailing text after it:

FOLLOWUPS:
- <one short question she might want to ask next, <=12 words>
- <a second short question, <=12 words>
- <a third short question, <=12 words>

The follow-ups should be concrete next questions tied to what you
just said, not generic prompts. If you can only think of two good
ones, return two. Never invent a topic outside her actual context
to fill the slots. The block will be parsed out and rendered as
buttons; do not number or punctuate the items differently.
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


# Lazily-compiled regexes for cleaning up anything the model emits that
# the chat bubble can't render properly (markdown, em/en dashes, list
# bullets in the body).
_MARKDOWN_BOLD_RE = None
_MARKDOWN_ITALIC_RE = None
_MARKDOWN_HEADER_RE = None
_BACKTICK_RE = None
_BULLET_LINE_RE = None


def _strip_markdown(text: str) -> str:
    """Strip markdown markers, em/en dashes, and inline list bullets
    from the visible reply. The chat renders with whitespace-pre-wrap,
    so any of those would show up as literal characters to the patient.
    """
    import re

    global _MARKDOWN_BOLD_RE, _MARKDOWN_ITALIC_RE
    global _MARKDOWN_HEADER_RE, _BACKTICK_RE, _BULLET_LINE_RE
    if _MARKDOWN_BOLD_RE is None:
        _MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
        # *italic* / _italic_ with word-boundary guards so we don't
        # munge things like 5*10 or snake_case identifiers.
        _MARKDOWN_ITALIC_RE = re.compile(
            r"(?<![\w*])\*([^*\n]+)\*(?!\w)|(?<![\w_])_([^_\n]+)_(?!\w)"
        )
        # Leading "# ", "## ", etc. on a line.
        _MARKDOWN_HEADER_RE = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
        # `inline code` -> inline code.
        _BACKTICK_RE = re.compile(r"`([^`\n]+)`")
        # A line that is just a bullet ("- foo" / "* foo" / "1. foo").
        # We convert these to plain sentences by stripping the marker.
        _BULLET_LINE_RE = re.compile(
            r"^[ \t]*(?:[-*•]|\d+[.)])[ \t]+", re.MULTILINE
        )

    text = _MARKDOWN_BOLD_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _MARKDOWN_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", text)
    text = _MARKDOWN_HEADER_RE.sub("", text)
    text = _BACKTICK_RE.sub(lambda m: m.group(1), text)
    text = _BULLET_LINE_RE.sub("", text)
    # Em / en dashes -> regular commas to keep the prose clean and
    # match the project's house style.
    text = text.replace("—", ",").replace("–", ",")
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
