"""Tests for G4 retrieval: surfacing curated facts into agent context."""

from __future__ import annotations

from pathlib import Path

from personal_llm.agent.smol import (
    build_memory_context,
    format_facts_context,
)
from personal_llm.memory import SqliteBackend


def _graded(backend, text, volatility, status="active"):
    backend.append_fact(text, "transcript:s1")
    row = next(f for f in backend.facts_for_grading() if f["text"] == text)
    backend.update_fact_grade(row["id"], volatility, status)


def test_recall_facts_orders_durable_first(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _graded(backend, "volatile one", "volatile")
    _graded(backend, "static one", "static")
    _graded(backend, "slow one", "slow")

    facts = backend.recall_facts()
    assert [f["text"] for f in facts] == ["static one", "slow one", "volatile one"]


def test_recall_facts_weights_corroboration_within_bucket(tmp_path: Path):
    """Within one volatility bucket, better-corroborated facts surface first,
    overriding the recency (id DESC) tiebreak."""
    backend = SqliteBackend(tmp_path)
    backend.append_fact("well supported", "transcript:s1")
    backend.append_fact("well supported", "transcript:s2")  # corroboration -> 2
    _graded(backend, "well supported", "static")
    _graded(backend, "single source", "static")  # newer (higher id), corroboration 1

    assert [f["text"] for f in backend.recall_facts()] == [
        "well supported",
        "single source",
    ]


def test_recall_facts_excludes_inactive(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _graded(backend, "kept", "static")
    _graded(backend, "gone", "ephemeral", status="expired")

    assert [f["text"] for f in backend.recall_facts()] == ["kept"]


def test_recall_facts_respects_limit(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    for i in range(5):
        _graded(backend, f"fact {i}", "static")
    assert len(backend.recall_facts(limit=2)) == 2


def test_format_facts_context_empty_is_blank():
    assert format_facts_context([]) == ""


def test_format_facts_context_renders_block():
    block = format_facts_context([{"text": "user runs Linux"}, {"text": "uses uv"}])
    assert "What you know about this user" in block
    assert "- user runs Linux" in block
    assert "- uses uv" in block


def test_build_memory_context_facts_only(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _graded(backend, "static fact", "static")
    backend.append_turn(backend.new_session_id(), "user", "hello")

    ctx = build_memory_context(backend)  # recall_turns defaults to 0
    assert "static fact" in ctx
    assert "hello" not in ctx  # turns not included unless requested


def test_build_memory_context_with_turns(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _graded(backend, "static fact", "static")
    backend.append_turn(backend.new_session_id(), "user", "remember this")

    ctx = build_memory_context(backend, recall_turns=10)
    assert "static fact" in ctx
    assert "remember this" in ctx


def test_build_memory_context_empty_vault(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    assert build_memory_context(backend, recall_turns=10) == ""
