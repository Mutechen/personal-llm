"""Phase 0 stub for recall memory: append-only JSONL per session.

Letta replaces this in Phase 1; the API surface here is deliberately small so
the swap is one file's worth of code.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

INTERACTIONS_DIR = "data/interactions"


def new_session_id() -> str:
    """A session id is the ISO timestamp + 8 random hex chars."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def session_path(vault_path: Path, session_id: str) -> Path:
    return vault_path / INTERACTIONS_DIR / f"{session_id}.jsonl"


def append_turn(vault_path: Path, session_id: str, role: str, content: str) -> None:
    """Append a single conversation turn to the session's JSONL file."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "role": role,
        "content": content,
    }
    path = session_path(vault_path, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def recent_turns(vault_path: Path, limit: int = 20) -> list[dict[str, str]]:
    """Return the last `limit` turns across all sessions, oldest first.

    Used to provide cross-session continuity in chat. Crude but correct for Phase 0.
    """
    interactions = vault_path / INTERACTIONS_DIR
    if not interactions.is_dir():
        return []
    files = sorted(interactions.glob("*.jsonl"), reverse=True)
    collected: list[dict[str, str]] = []
    for fpath in files:
        with fpath.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            collected.append({"role": rec["role"], "content": rec["content"]})
            if len(collected) >= limit:
                break
        if len(collected) >= limit:
            break
    return list(reversed(collected))


def turn_counts_for_today(vault_path: Path) -> dict[str, int]:
    """Count turns & sessions logged today. Used by the sleep-time growth log."""
    interactions = vault_path / INTERACTIONS_DIR
    today_prefix = datetime.now(UTC).strftime("%Y%m%d")
    sessions = 0
    turns = 0
    if not interactions.is_dir():
        return {"sessions": 0, "turns": 0}
    for fpath in interactions.glob(f"{today_prefix}T*.jsonl"):
        sessions += 1
        with fpath.open("r", encoding="utf-8") as f:
            turns += sum(1 for _ in f)
    return {"sessions": sessions, "turns": turns}
