"""Distill durable facts about the user from a transcript session.

P1's only extractor: it reads one rendered session and returns a list of short,
self-contained facts about the user, their projects, decisions, and
constraints. Capability (how the expert reasons) is deliberately *not*
harvested — only the personal layer. See docs/LEARNING_FROM_TRANSCRIPTS.md §2.

Facts produced here are tagged `unverified` at write time: they come from
conversation and haven't been checked. The richer certainty / volatility /
provenance grading is deferred (ARCHITECTURE.md §4 L4).
"""

from __future__ import annotations

import json
import re
from typing import Protocol

_SYSTEM = (
    "You extract durable, personal facts about a user from a transcript of their "
    "conversation with an AI coding assistant. You output only JSON."
)

_PROMPT = """\
Below is a transcript between a user and an AI assistant. Extract durable facts
about THE USER that would help a personal assistant remember them later:
their projects, goals, decisions, preferences, constraints, environment, and
relationships.

Rules:
- Only facts about the user or their world. Ignore general knowledge, and
  ignore facts about the AI assistant itself.
- Each fact must be one short, self-contained sentence that stands alone
  without the transcript.
- Skip anything ephemeral or trivial (greetings, one-off debugging chatter).
- If there are no durable facts, return an empty array.

Output ONLY a JSON array of strings. No prose, no markdown.

TRANSCRIPT:
{transcript}
"""


class _Completer(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


def parse_facts(raw: str) -> list[str]:
    """Parse a model response into a clean list of fact strings.

    Tolerant: strips `<think>` blocks (qwen3), then takes the outermost JSON
    array. Accepts arrays of strings or of objects with a `fact`/`text` key.
    Returns [] on anything it can't read, rather than raising.
    """
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    facts: list[str] = []
    for item in data:
        if isinstance(item, str):
            fact = item.strip()
        elif isinstance(item, dict):
            fact = str(item.get("fact") or item.get("text") or "").strip()
        else:
            continue
        if fact:
            facts.append(fact)
    return facts


def extract_facts(client: _Completer, session_text: str) -> list[str]:
    """Run the fact extractor over one rendered session."""
    if not session_text.strip():
        return []
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _PROMPT.format(transcript=session_text)},
    ]
    return parse_facts(client.complete(messages))
