"""Tests for parsing Claude Code JSONL transcripts."""

from __future__ import annotations

import json
from pathlib import Path

from personal_llm.learning.transcripts import (
    TranscriptSession,
    TranscriptTurn,
    iter_sessions,
)


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")


def _user(text, sid="s1", ts="2026-06-18T10:00:00Z", **extra):
    return {
        "type": "user",
        "sessionId": sid,
        "timestamp": ts,
        "message": {"role": "user", "content": text},
        **extra,
    }


def _assistant(blocks, sid="s1", ts="2026-06-18T10:00:01Z", **extra):
    return {
        "type": "assistant",
        "sessionId": sid,
        "timestamp": ts,
        "message": {"role": "assistant", "content": blocks},
        **extra,
    }


def test_extracts_user_and_assistant_text(tmp_path: Path):
    _write_jsonl(
        tmp_path / "proj" / "s1.jsonl",
        [
            _user("hello there"),
            _assistant(
                [
                    {"type": "thinking", "thinking": "hmm"},
                    {"type": "text", "text": "hi, how can I help?"},
                ]
            ),
        ],
    )
    sessions = list(iter_sessions(tmp_path))
    assert len(sessions) == 1
    s = sessions[0]
    assert isinstance(s, TranscriptSession)
    assert s.project == "proj"
    assert s.turns == [
        TranscriptTurn("user", "hello there"),
        TranscriptTurn("assistant", "hi, how can I help?"),
    ]


def test_drops_tool_and_machinery_events(tmp_path: Path):
    _write_jsonl(
        tmp_path / "proj" / "s1.jsonl",
        [
            _user("do the thing"),
            _assistant([{"type": "tool_use", "name": "bash", "input": {}}]),
            # tool result comes back as a user-type event with no text block
            _user([{"type": "tool_result", "content": "output"}], ts="2026-06-18T10:00:02Z"),
            {"type": "file-history-snapshot", "snapshot": {}},
            {"type": "system", "subtype": "info"},
            _assistant([{"type": "text", "text": "done"}], ts="2026-06-18T10:00:03Z"),
        ],
    )
    s = next(iter(iter_sessions(tmp_path)))
    assert [t.text for t in s.turns] == ["do the thing", "done"]


def test_skips_sidechain_and_meta(tmp_path: Path):
    _write_jsonl(
        tmp_path / "proj" / "s1.jsonl",
        [
            _user("real message"),
            _user("subagent noise", ts="2026-06-18T10:00:02Z", isSidechain=True),
            _user("meta noise", ts="2026-06-18T10:00:03Z", isMeta=True),
        ],
    )
    s = next(iter(iter_sessions(tmp_path)))
    assert [t.text for t in s.turns] == ["real message"]


def test_groups_by_session_and_orders_by_timestamp(tmp_path: Path):
    _write_jsonl(
        tmp_path / "proj" / "a.jsonl",
        [
            _user("second", sid="s1", ts="2026-06-18T10:00:05Z"),
            _user("first", sid="s1", ts="2026-06-18T10:00:01Z"),
            _user("other session", sid="s2", ts="2026-06-18T10:00:02Z"),
        ],
    )
    sessions = {s.session_id: s for s in iter_sessions(tmp_path)}
    assert [t.text for t in sessions["s1"].turns] == ["first", "second"]
    assert [t.text for t in sessions["s2"].turns] == ["other session"]


def test_tolerates_bad_lines_and_missing_dir(tmp_path: Path):
    assert list(iter_sessions(tmp_path / "does-not-exist")) == []
    path = tmp_path / "proj" / "s1.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('not json\n{"type":"user","sessionId":"s1","message":{"content":"ok"}}\n')
    s = next(iter(iter_sessions(tmp_path)))
    assert [t.text for t in s.turns] == ["ok"]


def test_render_caps_length(tmp_path: Path):
    session = TranscriptSession(
        session_id="s1",
        project="p",
        turns=[TranscriptTurn("user", "x" * 100)],
        last_ts="",
    )
    assert len(session.render(max_chars=10)) == 10
