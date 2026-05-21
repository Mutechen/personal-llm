"""SQLite-backed recall memory.

Stdlib `sqlite3` — zero new dependencies. One database per vault at
`data/memory.db`, one row per conversation turn. Recall only; semantic /
archival search (sqlite-vss) is a later chunk.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

DB_RELATIVE_PATH = "data/memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_created_at ON turns(created_at);
"""


class SqliteBackend:
    """`MemoryBackend` storing conversation turns in a per-vault SQLite database."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self.db_path = vault_path / DB_RELATIVE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def new_session_id(self) -> str:
        """ISO timestamp + 8 random hex chars (sortable, human-readable)."""
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        self.conn.execute(
            "INSERT INTO turns (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, datetime.now(UTC).isoformat()),
        )
        self.conn.commit()

    def recent_turns(self, limit: int = 20) -> list[dict[str, str]]:
        """Last `limit` turns across all sessions, oldest first.

        Ordered by insertion id, not timestamp — turns within one second keep a
        stable order.
        """
        rows = self.conn.execute(
            "SELECT role, content FROM turns ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def turn_counts_for_today(self) -> dict[str, int]:
        """Count turns & distinct sessions logged today (UTC). Used by the growth log."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        turns, sessions = self.conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT session_id) FROM turns WHERE created_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return {"sessions": sessions, "turns": turns}
