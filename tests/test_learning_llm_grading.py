"""Tests for the G2 batched LLM volatility grading pass.

The grader is injected, so the pass runs without a live model.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from personal_llm.learning.llm_grading import (
    BATCH_SIZE,
    grade_facts_llm,
    parse_volatility,
)
from personal_llm.memory import SqliteBackend


def test_parse_volatility_indexed_objects():
    raw = '[{"i": 1, "v": "static"}, {"i": 2, "v": "ephemeral"}]'
    assert parse_volatility(raw, 2) == ["static", "ephemeral"]


def test_parse_volatility_bare_array_positional():
    assert parse_volatility('["slow", "volatile"]', 2) == ["slow", "volatile"]


def test_parse_volatility_strips_think_and_pads_missing():
    raw = '<think>...</think>[{"i": 1, "v": "static"}]'
    assert parse_volatility(raw, 3) == ["static", "slow", "slow"]


def test_parse_volatility_rejects_unknown_labels():
    assert parse_volatility('[{"i":1,"v":"someday"}]', 1) == ["slow"]


def test_parse_volatility_garbage_falls_back():
    assert parse_volatility("not json", 2) == ["slow", "slow"]


@pytest.fixture
def backend(tmp_path: Path) -> SqliteBackend:
    return SqliteBackend(tmp_path)


def _grader(mapping):
    """Build a batch grader that labels by exact fact text, default 'slow'."""
    return lambda texts: [mapping.get(t, "slow") for t in texts]


def test_llm_grade_assigns_static_and_expires_ephemeral(backend: SqliteBackend):
    backend.append_fact("user is the maintainer of Mutechen", "transcript:s1")
    backend.append_fact("chrome tab open for 6 days", "transcript:s1")
    grader = _grader(
        {
            "user is the maintainer of Mutechen": "static",
            "chrome tab open for 6 days": "ephemeral",
        }
    )

    result = grade_facts_llm(backend, grader=grader)

    assert result.facts_seen == 2
    assert result.expired_ephemeral == 1
    rows = {f["text"]: f for f in backend.facts_for_grading()}
    assert rows["user is the maintainer of Mutechen"]["volatility"] == "static"
    assert "chrome tab open for 6 days" not in rows  # expired, no longer active


def test_llm_grade_sets_method_and_is_idempotent(backend: SqliteBackend):
    backend.append_fact("user prefers uv", "transcript:s1")

    first = grade_facts_llm(backend, grader=_grader({"user prefers uv": "static"}))
    second = grade_facts_llm(backend, grader=_grader({"user prefers uv": "volatile"}))

    assert first.facts_seen == 1
    assert second.facts_seen == 0  # already grade_method='llm', skipped
    assert backend.facts_for_grading()[0]["volatility"] == "static"


def test_llm_regrades_over_g1(backend: SqliteBackend):
    """A fact G1 marked heuristically is eligible for the LLM pass."""
    from personal_llm.learning.grading import grade_facts

    backend.append_fact("user is working on the encyclopedia", "transcript:s1")
    grade_facts(backend)  # G1 -> volatile, method=heuristic
    assert backend.facts_for_grading()[0]["volatility"] == "volatile"

    grade_facts_llm(
        backend, grader=_grader({"user is working on the encyclopedia": "slow"})
    )
    row = backend.facts_for_grading()[0]
    assert row["volatility"] == "slow"
    assert row["grade_method"] == "llm"


def test_llm_grade_batches(backend: SqliteBackend):
    n = BATCH_SIZE + 3
    for i in range(n):
        backend.append_fact(f"fact number {i}", "transcript:s1")

    seen_batches = []

    def grader(texts):
        seen_batches.append(len(texts))
        return ["slow"] * len(texts)

    result = grade_facts_llm(backend, grader=grader)
    assert result.facts_seen == n
    assert seen_batches == [BATCH_SIZE, 3]


def test_llm_grade_dry_run_writes_nothing(backend: SqliteBackend):
    backend.append_fact("momentary load spike", "transcript:s1")
    result = grade_facts_llm(
        backend, grader=_grader({"momentary load spike": "ephemeral"}), dry_run=True
    )
    assert result.expired_ephemeral == 1
    row = backend.facts_for_grading()[0]
    assert row["volatility"] is None
    assert row["grade_method"] is None


def test_llm_volatile_past_ttl_expires(backend: SqliteBackend):
    backend.append_fact("user is mid-migration", "transcript:s1")
    future = datetime.now(UTC) + timedelta(days=30)
    result = grade_facts_llm(
        backend,
        grader=_grader({"user is mid-migration": "volatile"}),
        ttl_days=14,
        now=future,
    )
    assert result.expired_volatile_ttl == 1
    assert backend.facts_for_grading() == []


def test_grade_facts_llm_requires_config_or_grader(backend: SqliteBackend):
    backend.append_fact("x", "transcript:s1")
    with pytest.raises(ValueError):
        grade_facts_llm(backend)
