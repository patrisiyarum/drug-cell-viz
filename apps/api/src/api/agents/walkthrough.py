"""Conversational walkthrough agent.

Talks the patient through their pharmacogenomic analysis results in
plain English. Has access to:
    - The structured analysis result (HRD score + label, drug + target,
      variants, patient indication, lab tile outputs the frontend has
      already computed).
    - Claude's native web_search tool, so it can pull current
      information (e.g. recent guideline changes, ongoing trials) and
      cite the source URLs back to the patient.

This agent is multi-turn: the frontend persists the message history
client-side and re-sends it on every turn. The system prompt is locked
to a "explain, don't prescribe" stance and tells Claude to cite the
analysis context when it can rather than re-searching for known facts.

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
from typing import Any

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
  - Translate medical terms on first use ("pathogenic — meaning harmful").
  - Short replies. Two short paragraphs is usually enough.
  - When you cite a source, say where it's from (e.g. "according to
     the FDA label for olaparib") so she knows it's real.

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


def _parse_followups(text: str) -> tuple[str, list[str]]:
    """Split the model's text into (reply_without_block, followups list).

    Looks for the literal "FOLLOWUPS:" marker at the start of a line.
    Everything before becomes the visible reply; everything after is
    parsed as a hyphenated list. Defensive: if the block is missing or
    malformed we just return ([], full_text) so the user still sees the
    reply.
    """
    if FOLLOWUPS_MARKER not in text:
        return text.strip(), []
    body, _, raw_block = text.partition(FOLLOWUPS_MARKER)
    items: list[str] = []
    for line in raw_block.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading "- ", "* ", or "1. " style markers.
        if line.startswith(("-", "*", "•")):
            line = line[1:].strip()
        elif len(line) > 2 and line[0].isdigit() and line[1] in (".", ")"):
            line = line[2:].strip()
        if line:
            items.append(line)
    # Cap at 4 to keep the UI tidy.
    return body.strip(), items[:4]


def _format_context(context: dict[str, Any]) -> str:
    """Serialize the analysis context into a compact JSON block the
    model can read without us having to flatten it into prose."""
    return json.dumps(context, indent=2, default=str)


async def reply(
    messages: list[dict[str, str]],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Run one turn of the walkthrough conversation.

    Args:
        messages: chat history. Each entry is {"role": "user"|"assistant",
            "content": str}. The latest user message is the prompt
            being responded to; everything before it is history.
        context: structured analysis result + indication. Passed verbatim
            into the system prompt as JSON so the model has the full
            picture without needing tool calls to retrieve it.

    Returns:
        {
            "reply": str,            # assistant's text response
            "citations": [{url, title}, ...],  # web_search citations
            "model": str,            # the model id used
            "duration_ms": int,
        }

    Falls back to a stub response if ANTHROPIC_API_KEY is missing so the
    UI still works in dev / offline.
    """
    t0 = time.time()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return {
            "reply": (
                "The chat agent is offline because no ANTHROPIC_API_KEY "
                "is set on this server. Once it's configured, this is "
                "where I'd walk you through your results in plain English "
                "and answer your questions."
            ),
            "citations": [],
            "followups": [],
            "model": "stub",
            "duration_ms": int((time.time() - t0) * 1000),
        }

    import anthropic

    system = (
        SYSTEM_PROMPT
        + "\n\n--- ANALYSIS CONTEXT (JSON) ---\n"
        + _format_context(context)
    )

    # Anthropic's native web_search server-side tool. The `max_uses`
    # cap keeps a chatty model from burning the API budget on trivial
    # questions; if it needs more it can ask the user to be specific.
    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        }
    ]

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=CLAUDE_TIMEOUT_SECONDS)

    # Retry transient overloaded / rate-limit errors with exponential
    # backoff. Anthropic returns 529 ("Overloaded") during capacity
    # spikes; retrying after a short pause is the documented mitigation.
    msg = None
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            msg = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools,
                messages=messages,
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
            "reply": friendly,
            "citations": [],
            "followups": [],
            "model": CLAUDE_MODEL,
            "duration_ms": int((time.time() - t0) * 1000),
        }

    # Extract the assistant's text and any web-search citations the
    # model attached. The web_search tool emits citation objects inside
    # text blocks when it grounds a sentence on a source.
    reply_parts: list[str] = []
    citations: list[dict[str, str]] = []
    for block in msg.content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            reply_parts.append(getattr(block, "text", ""))
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

    full_text = "".join(reply_parts)
    visible_reply, followups = _parse_followups(full_text)

    return {
        "reply": visible_reply,
        "citations": unique_citations,
        "followups": followups,
        "model": CLAUDE_MODEL,
        "duration_ms": int((time.time() - t0) * 1000),
    }
