"""G2 fact grading — batched local-LLM volatility refinement.

Where G1 (grading.py) classifies by surface pattern and stays conservative, G2
asks the local model to bucket each fact's volatility — adding the `static`
bucket G1 never assigns, and catching the cases patterns miss (e.g. "Chrome tab
active for 6 days" is ephemeral, not slow).

Scope is deliberately just volatility + lifecycle. Certainty grading belongs to
G4 (cross-session corroboration), not a single-transcript guess; dedup and
supersession are G3. The pass is idempotent: only facts not already
`grade_method='llm'` are re-graded, batched to bound the number of model calls.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from personal_llm.config import VaultConfig
from personal_llm.learning.grading import (
    DEFAULT_TTL_DAYS,
    VOLATILITY_BUCKETS,
    GradeChange,
    GradeResult,
    lifecycle_status,
)
from personal_llm.memory import MemoryBackend

BATCH_SIZE = 12
_FALLBACK = "slow"  # used when the model omits or mislabels a fact

# Returns one volatility label per input fact text, in order.
BatchGrader = Callable[[list[str]], list[str]]

_SYSTEM = (
    "You classify how quickly each fact about a user goes stale. You output only JSON."
)

_PROMPT = """\
Classify each numbered fact into exactly ONE volatility bucket:
- static: a stable trait, preference, relationship, or environment fact that
  rarely or never changes.
- slow: changes over months (tech stack, ongoing projects, habits).
- volatile: changes over days or weeks (current task, status, plans,
  uncommitted work).
- ephemeral: momentary machine or runtime state that should not be remembered
  at all (CPU load, temperature, what is running right now, transient counts).

Return ONLY a JSON array, one object per fact, in order:
[{{"i": 1, "v": "static"}}, {{"i": 2, "v": "volatile"}}, ...]

FACTS:
{facts}
"""


class _Completer(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


def parse_volatility(raw: str, n: int) -> list[str]:
    """Parse the model's response into exactly `n` volatility labels.

    Accepts `[{"i":1,"v":"slow"}, ...]` (mapped by 1-based index) or a bare
    `["slow", ...]` (positional). Unknown/missing entries fall back to `slow`,
    so a single fact's mislabel never drops the whole batch.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end < start:
        return [_FALLBACK] * n
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return [_FALLBACK] * n
    if not isinstance(data, list):
        return [_FALLBACK] * n

    labels = [_FALLBACK] * n
    for pos, item in enumerate(data):
        if isinstance(item, dict):
            idx = item.get("i")
            value = str(item.get("v", "")).strip().lower()
            slot = idx - 1 if isinstance(idx, int) else pos
        else:
            value = str(item).strip().lower()
            slot = pos
        if 0 <= slot < n and value in VOLATILITY_BUCKETS:
            labels[slot] = value
    return labels


def llm_grade_batch(client: _Completer, texts: list[str]) -> list[str]:
    """Grade one batch of fact texts with the local model."""
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(texts, start=1))
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _PROMPT.format(facts=numbered)},
    ]
    return parse_volatility(client.complete(messages), len(texts))


def _default_grader(config: VaultConfig) -> BatchGrader:
    from personal_llm.inference.local import LocalModelClient

    client = LocalModelClient(config.local_model.name, config.local_model.endpoint)
    return lambda texts: llm_grade_batch(client, texts)


def grade_facts_llm(
    backend: MemoryBackend,
    config: VaultConfig | None = None,
    ttl_days: int = DEFAULT_TTL_DAYS,
    dry_run: bool = False,
    now: datetime | None = None,
    grader: BatchGrader | None = None,
) -> GradeResult:
    """Re-grade volatility with the local model for facts G2 hasn't seen.

    `grader` is injectable so tests run the whole pass without a live model.
    """
    now = now or datetime.now(UTC)
    if grader is None:
        if config is None:
            raise ValueError("grade_facts_llm needs a config or an injected grader")
        grader = _default_grader(config)

    pending = [f for f in backend.facts_for_grading() if f["grade_method"] != "llm"]
    result = GradeResult(dry_run=dry_run)

    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        labels = grader([f["text"] for f in batch])
        for fact, label in zip(batch, labels, strict=True):
            volatility = label if label in VOLATILITY_BUCKETS else _FALLBACK
            status = lifecycle_status(volatility, fact["valid_as_of"], now, ttl_days)

            result.facts_seen += 1
            result.newly_graded += 1
            result.by_volatility[volatility] = result.by_volatility.get(volatility, 0) + 1
            if status == "expired":
                if volatility == "ephemeral":
                    result.expired_ephemeral += 1
                else:
                    result.expired_volatile_ttl += 1

            changed = volatility != fact["volatility"] or status != fact["status"]
            if changed:
                result.changes.append(
                    GradeChange(fact["id"], fact["text"], volatility, status)
                )
            if not dry_run:
                backend.update_fact_grade(fact["id"], volatility, status, method="llm")

    return result
