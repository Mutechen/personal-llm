"""G1 fact grading — deterministic, no LLM.

The first consolidation pass over distilled facts (FACT_GRADING.md). It does
the cheap, high-confidence work before any model is involved:

- classify each fact's **volatility** by surface pattern,
- expire **ephemeral** facts (momentary state that should never persist),
- expire **volatile** facts whose `valid_as_of` is past the TTL,
- leave everything else `slow` and `active`.

It deliberately does NOT try to tell `slow` from `static`, or grade certainty
beyond what corroboration (a later pass) can compute. Patterns are conservative:
a false `slow` (durable) is harmless; a false `ephemeral` silently drops a real
fact, so the ephemeral set is kept tight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from personal_llm.memory import MemoryBackend

DEFAULT_TTL_DAYS = 14

# Volatility buckets, most-durable first. G1 assigns ephemeral/volatile/slow;
# G2's LLM pass additionally distinguishes `static` from `slow`.
VOLATILITY_BUCKETS = ("static", "slow", "volatile", "ephemeral")

# Momentary machine/runtime state — never durable. Tight on purpose.
_EPHEMERAL = [
    re.compile(r"\bload average\b", re.I),
    re.compile(r"\bthermal_zone\w*\b", re.I),
    re.compile(r"\b\d{1,3}(?:\.\d+)?\s*°?\s*C\b"),  # temperatures e.g. 92°C
    re.compile(r"\bis (?:currently )?(?:experiencing|running|processing)\b", re.I),
    re.compile(r"\b(?:right now|at the moment|as of (?:now|today))\b", re.I),
]

# Current-activity / status language — true now, stale soon.
_VOLATILE = [
    re.compile(r"\b(?:is|are) (?:currently )?working on\b", re.I),
    re.compile(r"\bin progress\b", re.I),
    re.compile(r"\buncommitted\b", re.I),
    re.compile(r"\bpreparing to\b", re.I),
    re.compile(r"\b(?:at|in) Phase \d", re.I),
    re.compile(r"\b(?:awaiting|pending|not yet|about to)\b", re.I),
    re.compile(r"\bship gate\b", re.I),
    re.compile(r"\bplans? to\b|\bgoing to\b|\bupcoming\b", re.I),
]


def classify_volatility(text: str) -> str:
    """Return `ephemeral`, `volatile`, or `slow` from surface patterns."""
    if any(p.search(text) for p in _EPHEMERAL):
        return "ephemeral"
    if any(p.search(text) for p in _VOLATILE):
        return "volatile"
    return "slow"


@dataclass
class GradeChange:
    fact_id: int
    text: str
    volatility: str
    new_status: str


@dataclass
class GradeResult:
    facts_seen: int = 0
    newly_graded: int = 0
    expired_ephemeral: int = 0
    expired_volatile_ttl: int = 0
    by_volatility: dict[str, int] = field(default_factory=dict)
    dry_run: bool = False
    changes: list[GradeChange] = field(default_factory=list)


def _is_past_ttl(valid_as_of: str | None, now: datetime, ttl_days: int) -> bool:
    if not valid_as_of:
        return False
    try:
        anchored = datetime.fromisoformat(valid_as_of)
    except ValueError:
        return False
    return now - anchored > timedelta(days=ttl_days)


def lifecycle_status(
    volatility: str, valid_as_of: str | None, now: datetime, ttl_days: int
) -> str:
    """Map a volatility bucket (+ age) to a lifecycle status. Shared by G1/G2."""
    if volatility == "ephemeral":
        return "expired"
    if volatility == "volatile" and _is_past_ttl(valid_as_of, now, ttl_days):
        return "expired"
    return "active"


def grade_facts(
    backend: MemoryBackend,
    ttl_days: int = DEFAULT_TTL_DAYS,
    dry_run: bool = False,
    now: datetime | None = None,
) -> GradeResult:
    """Run the G1 deterministic grading pass over a vault's active facts.

    Idempotent: a fact already graded is only revisited to apply TTL expiry, so
    re-running converges.
    """
    now = now or datetime.now(UTC)
    result = GradeResult(dry_run=dry_run)

    for fact in backend.facts_for_grading():
        result.facts_seen += 1
        volatility = fact["volatility"] or classify_volatility(fact["text"])
        status = lifecycle_status(volatility, fact["valid_as_of"], now, ttl_days)

        result.by_volatility[volatility] = result.by_volatility.get(volatility, 0) + 1

        already_graded = fact["volatility"] is not None
        unchanged = already_graded and status == fact["status"]
        if unchanged:
            continue

        if not already_graded:
            result.newly_graded += 1
        if status == "expired":
            if volatility == "ephemeral":
                result.expired_ephemeral += 1
            else:
                result.expired_volatile_ttl += 1

        result.changes.append(GradeChange(fact["id"], fact["text"], volatility, status))
        if not dry_run:
            backend.update_fact_grade(fact["id"], volatility, status)

    return result
