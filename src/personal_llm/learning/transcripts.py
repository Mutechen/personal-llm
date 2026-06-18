"""Parse Claude Code JSONL transcripts into per-session conversations.

Claude Code stores one session as a `.jsonl` file under
`~/.claude/projects/<project-slug>/`. Each line is an event; we keep only the
natural-language `user` and `assistant` turns and drop the machinery (tool
calls, tool results, thinking, snapshots, mode changes, sidechains).

Tolerant by design: this reads files the user never meant for us, written by a
tool whose format we don't control, so unknown shapes are skipped, not fatal.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Cap a rendered session so one very long transcript can't blow the model's
# context. Generous enough that most sessions pass through whole.
MAX_RENDER_CHARS = 12000


@dataclass(frozen=True)
class TranscriptTurn:
    role: str
    text: str


@dataclass(frozen=True)
class TranscriptSession:
    session_id: str
    project: str
    turns: list[TranscriptTurn]
    last_ts: str

    def render(self, max_chars: int = MAX_RENDER_CHARS) -> str:
        """Flatten to a plain `role: text` block for the distiller."""
        body = "\n\n".join(f"{t.role}: {t.text}" for t in self.turns)
        return body[:max_chars]


def _extract_text(content: object) -> str:
    """Pull natural-language text from an Anthropic message `content`.

    `content` is either a string or a list of typed blocks; we keep only the
    `text` blocks, dropping thinking / tool_use / tool_result.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block["text"].strip()
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        return "\n".join(p for p in parts if p).strip()
    return ""


def _read_events(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


def iter_sessions(root: Path) -> Iterator[TranscriptSession]:
    """Yield one `TranscriptSession` per Claude Code session under `root`.

    Sessions are keyed by `sessionId` and may span multiple files (resumed
    sessions); turns are ordered by timestamp.
    """
    if not root.is_dir():
        return

    sessions: dict[str, dict] = {}
    for path in sorted(root.glob("*/*.jsonl")):
        project = path.parent.name
        for evt in _read_events(path):
            if evt.get("type") not in ("user", "assistant"):
                continue
            if evt.get("isSidechain") or evt.get("isMeta"):
                continue
            message = evt.get("message") or {}
            text = _extract_text(message.get("content"))
            if not text:
                continue
            sid = evt.get("sessionId") or path.stem
            ts = evt.get("timestamp") or ""
            role = message.get("role") or evt["type"]
            bucket = sessions.setdefault(
                sid, {"project": project, "events": [], "last_ts": ""}
            )
            bucket["events"].append((ts, role, text))
            if ts > bucket["last_ts"]:
                bucket["last_ts"] = ts

    for sid, bucket in sessions.items():
        ordered = sorted(bucket["events"], key=lambda e: e[0])
        turns = [TranscriptTurn(role=role, text=text) for _, role, text in ordered]
        yield TranscriptSession(
            session_id=sid,
            project=bucket["project"],
            turns=turns,
            last_ts=bucket["last_ts"],
        )
