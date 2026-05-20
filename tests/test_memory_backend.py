"""Tests for the MemoryBackend protocol and the JsonlBackend implementation."""

from __future__ import annotations

from pathlib import Path

from personal_llm.memory import JsonlBackend, MemoryBackend, open_backend


def test_jsonl_backend_satisfies_protocol(tmp_path: Path):
    """JsonlBackend must structurally conform to MemoryBackend."""
    assert isinstance(JsonlBackend(tmp_path), MemoryBackend)


def test_open_backend_returns_a_memory_backend(tmp_path: Path):
    assert isinstance(open_backend(tmp_path), MemoryBackend)


def test_append_and_recent_turns_roundtrip(tmp_path: Path):
    backend = JsonlBackend(tmp_path)
    session_id = backend.new_session_id()

    backend.append_turn(session_id, "user", "hello")
    backend.append_turn(session_id, "assistant", "hi there")

    turns = backend.recent_turns()
    assert [(t["role"], t["content"]) for t in turns] == [
        ("user", "hello"),
        ("assistant", "hi there"),
    ]


def test_recent_turns_empty_vault(tmp_path: Path):
    assert JsonlBackend(tmp_path).recent_turns() == []


def test_recent_turns_respects_limit(tmp_path: Path):
    backend = JsonlBackend(tmp_path)
    session_id = backend.new_session_id()
    for i in range(10):
        backend.append_turn(session_id, "user", f"msg {i}")

    turns = backend.recent_turns(limit=3)
    assert [t["content"] for t in turns] == ["msg 7", "msg 8", "msg 9"]


def test_new_session_id_is_unique(tmp_path: Path):
    backend = JsonlBackend(tmp_path)
    ids = {backend.new_session_id() for _ in range(50)}
    assert len(ids) == 50


def test_turn_counts_for_today(tmp_path: Path):
    backend = JsonlBackend(tmp_path)
    session_id = backend.new_session_id()
    backend.append_turn(session_id, "user", "a")
    backend.append_turn(session_id, "assistant", "b")

    counts = backend.turn_counts_for_today()
    assert counts == {"sessions": 1, "turns": 2}
