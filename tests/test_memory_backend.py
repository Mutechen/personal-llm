"""Tests for the MemoryBackend protocol and its implementations.

The behavioral tests are parametrized over every backend — the parametrization
is the seam that keeps the protocol honest as more backends are added.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from personal_llm.memory import MemoryBackend, SqliteBackend, open_backend
from personal_llm.memory.sqlite import DB_RELATIVE_PATH

_BACKENDS = [SqliteBackend]


@pytest.fixture(params=_BACKENDS, ids=lambda c: c.__name__)
def backend(request, tmp_path: Path) -> MemoryBackend:
    return request.param(tmp_path)


@pytest.mark.parametrize("backend_cls", _BACKENDS, ids=lambda c: c.__name__)
def test_backend_satisfies_protocol(backend_cls, tmp_path: Path):
    assert isinstance(backend_cls(tmp_path), MemoryBackend)


def test_open_backend_returns_a_memory_backend(tmp_path: Path):
    assert isinstance(open_backend(tmp_path), MemoryBackend)


def test_append_and_recent_turns_roundtrip(backend: MemoryBackend):
    session_id = backend.new_session_id()
    backend.append_turn(session_id, "user", "hello")
    backend.append_turn(session_id, "assistant", "hi there")

    turns = backend.recent_turns()
    assert [(t["role"], t["content"]) for t in turns] == [
        ("user", "hello"),
        ("assistant", "hi there"),
    ]


def test_recent_turns_empty_vault(backend: MemoryBackend):
    assert backend.recent_turns() == []


def test_recent_turns_respects_limit(backend: MemoryBackend):
    session_id = backend.new_session_id()
    for i in range(10):
        backend.append_turn(session_id, "user", f"msg {i}")

    turns = backend.recent_turns(limit=3)
    assert [t["content"] for t in turns] == ["msg 7", "msg 8", "msg 9"]


def test_new_session_id_is_unique(backend: MemoryBackend):
    ids = {backend.new_session_id() for _ in range(50)}
    assert len(ids) == 50


def test_turn_counts_for_today(backend: MemoryBackend):
    session_id = backend.new_session_id()
    backend.append_turn(session_id, "user", "a")
    backend.append_turn(session_id, "assistant", "b")

    assert backend.turn_counts_for_today() == {"sessions": 1, "turns": 2}


def test_append_and_recent_facts_roundtrip(backend: MemoryBackend):
    assert backend.append_fact("user runs Linux", "transcript:s1") is True
    facts = backend.recent_facts()
    assert len(facts) == 1
    assert facts[0]["text"] == "user runs Linux"
    assert facts[0]["source"] == "transcript:s1"
    assert facts[0]["confidence"] == "unverified"


def test_append_fact_is_idempotent_on_text(backend: MemoryBackend):
    assert backend.append_fact("same fact", "transcript:s1") is True
    assert backend.append_fact("same fact", "transcript:s2") is False
    assert len(backend.recent_facts()) == 1


def test_append_fact_corroborates_across_sources(backend: MemoryBackend):
    """A re-assertion from a new session raises corroboration and promotes certainty."""
    assert backend.append_fact("user runs Linux", "transcript:s1") is True
    assert backend.append_fact("user runs Linux", "transcript:s2") is False

    fact = backend.recall_facts()[0]
    assert fact["corroboration"] == 2
    assert fact["confidence"] == "corroborated"


def test_append_fact_same_source_does_not_corroborate(backend: MemoryBackend):
    """A duplicate from the same session is within-session repetition, not support."""
    backend.append_fact("user runs Linux", "transcript:s1")
    backend.append_fact("user runs Linux", "transcript:s1")

    fact = backend.recall_facts()[0]
    assert fact["corroboration"] == 1
    assert fact["confidence"] == "unverified"


def test_merge_carries_corroboration_onto_canonical(backend: MemoryBackend):
    """G3 merging a near-dup is cross-session support: it promotes the keeper."""
    backend.append_fact("user runs Linux", "transcript:s1")
    backend.append_fact("the user is on Linux", "transcript:s2")
    rows = {f["text"]: f["id"] for f in backend.facts_for_grading()}
    backend.merge_fact(rows["the user is on Linux"], rows["user runs Linux"])

    active = backend.recall_facts()
    assert [f["text"] for f in active] == ["user runs Linux"]  # loser dropped out
    assert active[0]["corroboration"] == 2
    assert active[0]["confidence"] == "corroborated"


def test_count_corroborated(backend: MemoryBackend):
    backend.append_fact("solo fact", "transcript:s1")
    assert backend.count_corroborated() == 0
    backend.append_fact("shared fact", "transcript:s1")
    backend.append_fact("shared fact", "transcript:s2")  # promotes
    assert backend.count_corroborated() == 1


def test_recent_facts_respects_limit_and_order(backend: MemoryBackend):
    for i in range(5):
        backend.append_fact(f"fact {i}", "transcript:s1")
    facts = backend.recent_facts(limit=2)
    assert [f["text"] for f in facts] == ["fact 3", "fact 4"]


def test_append_fact_custom_confidence(backend: MemoryBackend):
    backend.append_fact("grounded fact", "quran:2:255", confidence="grounded")
    assert backend.recent_facts()[-1]["confidence"] == "grounded"


def test_facts_for_grading_and_update(backend: MemoryBackend):
    backend.append_fact("a durable fact", "transcript:s1")
    rows = backend.facts_for_grading()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "active"
    assert row["volatility"] is None
    assert row["valid_as_of"] is not None  # anchored at insert

    backend.update_fact_grade(row["id"], "ephemeral", "expired")
    # expired facts drop out of the active grading set
    assert backend.facts_for_grading() == []


def test_migrates_pre_grading_facts_table(tmp_path: Path):
    """An old vault whose facts table predates the grading columns is upgraded."""
    db = tmp_path / DB_RELATIVE_PATH
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            confidence TEXT NOT NULL DEFAULT 'unverified',
            created_at TEXT NOT NULL
        );
        INSERT INTO facts (text, source, confidence, created_at)
        VALUES ('old fact', 'transcript:s0', 'unverified', '2026-06-01T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    backend = SqliteBackend(tmp_path)
    rows = backend.facts_for_grading()
    assert len(rows) == 1
    assert rows[0]["status"] == "active"
    assert rows[0]["volatility"] is None
    # valid_as_of backfilled from created_at so TTL math has an anchor
    assert rows[0]["valid_as_of"] == "2026-06-01T00:00:00+00:00"


@pytest.mark.parametrize("backend_cls", _BACKENDS, ids=lambda c: c.__name__)
def test_backend_persists_across_instances(backend_cls, tmp_path: Path):
    """A fresh backend over the same vault sees turns written by an earlier one."""
    first = backend_cls(tmp_path)
    session_id = first.new_session_id()
    first.append_turn(session_id, "user", "remember me")

    second = backend_cls(tmp_path)
    assert second.recent_turns()[-1]["content"] == "remember me"
