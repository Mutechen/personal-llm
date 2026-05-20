"""JSONL-backed recall memory: append-only, one file per session.

Transitional. This is the Phase 0 storage moved behind the `MemoryBackend`
protocol so the `SqliteBackend` swap is a clean drop-in. Slated for deletion
once `SqliteBackend` lands.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

INTERACTIONS_DIR = "data/interactions"


class JsonlBackend:
    """`MemoryBackend` storing turns as per-session append-only JSONL files."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path

    def new_session_id(self) -> str:
        """ISO timestamp + 8 random hex chars."""
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]

    def session_path(self, session_id: str) -> Path:
        return self.vault_path / INTERACTIONS_DIR / f"{session_id}.jsonl"

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "role": role,
            "content": content,
        }
        path = self.session_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent_turns(self, limit: int = 20) -> list[dict[str, str]]:
        """Last `limit` turns across all sessions, oldest first. Crude but correct."""
        interactions = self.vault_path / INTERACTIONS_DIR
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

    def turn_counts_for_today(self) -> dict[str, int]:
        """Count turns & sessions logged today. Used by the sleep-time growth log."""
        interactions = self.vault_path / INTERACTIONS_DIR
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
