"""Tests for the chat REPL's per-turn handler."""

from __future__ import annotations

import json
from pathlib import Path

from personal_llm.agent.smol import chat_turn
from personal_llm.memory import simple as memory


class _FakeAgent:
    """Minimal stand-in for smolagents.CodeAgent.

    Records every call so we can assert reset=False is used (the bit that gives
    us in-session continuity), and returns a canned answer per turn.
    """

    def __init__(self, answers: list[str]):
        self._answers = list(answers)
        self.calls: list[dict] = []

    def run(self, task: str, reset: bool = True) -> str:
        self.calls.append({"task": task, "reset": reset})
        return self._answers.pop(0)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_chat_turn_writes_both_turns_and_returns_answer(tmp_path: Path):
    agent = _FakeAgent(answers=["4"])
    session_id = memory.new_session_id()

    answer = chat_turn(agent, tmp_path, session_id, "what is 2+2")

    assert answer == "4"
    log = _read_jsonl(memory.session_path(tmp_path, session_id))
    assert [(r["role"], r["content"]) for r in log] == [
        ("user", "what is 2+2"),
        ("assistant", "4"),
    ]


def test_chat_turn_preserves_agent_trajectory_across_turns(tmp_path: Path):
    """reset=False is what carries the ReAct trajectory between turns."""
    agent = _FakeAgent(answers=["hello", "blue"])
    session_id = memory.new_session_id()

    chat_turn(agent, tmp_path, session_id, "hi")
    chat_turn(agent, tmp_path, session_id, "what color?")

    assert [c["reset"] for c in agent.calls] == [False, False]
    assert [c["task"] for c in agent.calls] == ["hi", "what color?"]

    log = _read_jsonl(memory.session_path(tmp_path, session_id))
    assert len(log) == 4
    assert log[0]["content"] == "hi"
    assert log[1]["content"] == "hello"
    assert log[2]["content"] == "what color?"
    assert log[3]["content"] == "blue"


def test_chat_turn_coerces_non_string_answers(tmp_path: Path):
    """smolagents' final_answer can be any type; chat_turn returns a string."""
    agent = _FakeAgent(answers=[42])  # type: ignore[list-item]
    session_id = memory.new_session_id()

    answer = chat_turn(agent, tmp_path, session_id, "give me an int")

    assert answer == "42"
    log = _read_jsonl(memory.session_path(tmp_path, session_id))
    assert log[1]["content"] == "42"
