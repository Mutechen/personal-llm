"""Tests for the G1 deterministic fact-grading pass."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from personal_llm.learning.grading import classify_volatility, grade_facts
from personal_llm.memory import SqliteBackend


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The user's system has a load average of 22.36", "ephemeral"),
        ("thermal_zone1 is at 92°C", "ephemeral"),
        ("The backend is currently running on port 5173", "ephemeral"),
        ("The user is working on disk-toolkit cleanup", "volatile"),
        ("IE-167 Lane 1 ship gate is in progress", "volatile"),
        ("There are uncommitted changes in PLAN.md", "volatile"),
        ("The project is at Phase 1", "volatile"),
        ("The user separates personal and work data", "slow"),
        ("The user builds on an exFAT Samsung T5 drive", "slow"),
    ],
)
def test_classify_volatility(text, expected):
    assert classify_volatility(text) == expected


@pytest.fixture
def backend(tmp_path: Path) -> SqliteBackend:
    return SqliteBackend(tmp_path)


def test_grade_expires_ephemeral_and_buckets_rest(backend: SqliteBackend):
    backend.append_fact("load average of 22.36 right now", "transcript:s1")
    backend.append_fact("user is working on ZeenaStoreZ", "transcript:s1")
    backend.append_fact("user prefers reversible data operations", "transcript:s1")

    result = grade_facts(backend)

    assert result.facts_seen == 3
    assert result.newly_graded == 3
    assert result.expired_ephemeral == 1
    assert result.by_volatility == {"ephemeral": 1, "volatile": 1, "slow": 1}

    rows = {f["text"]: f for f in backend.facts_for_grading()}
    # the ephemeral fact is no longer active
    assert "load average of 22.36 right now" not in rows
    assert rows["user is working on ZeenaStoreZ"]["volatility"] == "volatile"
    assert rows["user prefers reversible data operations"]["status"] == "active"


def test_grade_is_idempotent(backend: SqliteBackend):
    backend.append_fact("user is working on the encyclopedia", "transcript:s1")
    backend.append_fact("user runs Linux", "transcript:s1")

    first = grade_facts(backend)
    second = grade_facts(backend)

    assert first.newly_graded == 2
    assert second.newly_graded == 0
    assert second.changes == []


def test_volatile_fact_expires_past_ttl(backend: SqliteBackend):
    backend.append_fact("user is working on a stale task", "transcript:s1")
    # grade far in the future so the volatile fact is past its TTL
    future = datetime.now(UTC) + timedelta(days=30)
    result = grade_facts(backend, ttl_days=14, now=future)

    assert result.expired_volatile_ttl == 1
    assert backend.facts_for_grading() == []  # nothing active left


def test_volatile_fact_survives_within_ttl(backend: SqliteBackend):
    backend.append_fact("user is working on a fresh task", "transcript:s1")
    result = grade_facts(backend, ttl_days=14)

    assert result.expired_volatile_ttl == 0
    active = backend.facts_for_grading()
    assert len(active) == 1
    assert active[0]["volatility"] == "volatile"


def test_dry_run_writes_nothing(backend: SqliteBackend):
    backend.append_fact("load average spiking", "transcript:s1")
    result = grade_facts(backend, dry_run=True)

    assert result.dry_run is True
    assert result.expired_ephemeral == 1
    # still active and ungraded on disk
    rows = backend.facts_for_grading()
    assert len(rows) == 1
    assert rows[0]["volatility"] is None
    assert rows[0]["status"] == "active"
