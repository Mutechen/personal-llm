"""Tests for the MemoryBackend protocol and its implementations.

The behavioral tests are parametrized over every backend — the parametrization
is the seam that keeps the protocol honest as more backends are added.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_llm.memory import MemoryBackend, SqliteBackend, open_backend

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


@pytest.mark.parametrize("backend_cls", _BACKENDS, ids=lambda c: c.__name__)
def test_backend_persists_across_instances(backend_cls, tmp_path: Path):
    """A fresh backend over the same vault sees turns written by an earlier one."""
    first = backend_cls(tmp_path)
    session_id = first.new_session_id()
    first.append_turn(session_id, "user", "remember me")

    second = backend_cls(tmp_path)
    assert second.recent_turns()[-1]["content"] == "remember me"
