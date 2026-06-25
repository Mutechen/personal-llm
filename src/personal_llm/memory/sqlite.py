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

# Certainty (confidence) values. A fact starts `unverified`; it is promoted to
# `corroborated` once it has been asserted across CORROBORATION_THRESHOLD
# independent sessions (directly, or via a G3 dedup merge). FACT_GRADING.md §2.
CONFIDENCE_UNVERIFIED = "unverified"
CONFIDENCE_CORROBORATED = "corroborated"
CORROBORATION_THRESHOLD = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_created_at ON turns(created_at);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'unverified',
    volatility TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    valid_as_of TEXT,
    graded_at TEXT,
    grade_method TEXT,
    canonical_id INTEGER,
    superseded_by INTEGER,
    corroboration INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""

# Columns added after the facts table first shipped. Existing vaults get them
# via ADD COLUMN (non-breaking); fresh ones already have them from _SCHEMA.
_FACT_MIGRATIONS = {
    "volatility": "ALTER TABLE facts ADD COLUMN volatility TEXT",
    "status": "ALTER TABLE facts ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
    "valid_as_of": "ALTER TABLE facts ADD COLUMN valid_as_of TEXT",
    "graded_at": "ALTER TABLE facts ADD COLUMN graded_at TEXT",
    "grade_method": "ALTER TABLE facts ADD COLUMN grade_method TEXT",
    "canonical_id": "ALTER TABLE facts ADD COLUMN canonical_id INTEGER",
    "superseded_by": "ALTER TABLE facts ADD COLUMN superseded_by INTEGER",
    "corroboration": "ALTER TABLE facts ADD COLUMN corroboration INTEGER NOT NULL DEFAULT 1",
}


class SqliteBackend:
    """`MemoryBackend` storing conversation turns in a per-vault SQLite database."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self.db_path = vault_path / DB_RELATIVE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(_SCHEMA)
        self._migrate_facts()
        self.conn.commit()

    def _migrate_facts(self) -> None:
        """Add fact columns missing from an older vault, then backfill anchors."""
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(facts)")}
        for column, ddl in _FACT_MIGRATIONS.items():
            if column not in existing:
                self.conn.execute(ddl)
        # valid_as_of anchors TTL math; pre-grading rows default to created_at.
        self.conn.execute(
            "UPDATE facts SET valid_as_of = created_at WHERE valid_as_of IS NULL"
        )

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

    def append_fact(self, text: str, source: str, confidence: str = "unverified") -> bool:
        now = datetime.now(UTC).isoformat()
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO facts (text, source, confidence, valid_as_of, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (text, source, confidence, now, now),
        )
        if cur.rowcount > 0:
            self.conn.commit()
            return True
        # Exact duplicate: a re-assertion from a *different* session corroborates
        # the existing fact. The learn watermark presents each (session, fact)
        # pair at most once, so this can't double-count across runs. We compare
        # only the first-recorded source; full multi-source tracking is deferred.
        row = self.conn.execute(
            "SELECT id, source FROM facts WHERE text = ?", (text,)
        ).fetchone()
        if row and row[1] != source:
            self._bump_corroboration(row[0])
        self.conn.commit()
        return False

    def _bump_corroboration(self, fact_id: int, by: int = 1) -> None:
        """Raise a fact's corroboration count and promote its certainty once
        independent sources cross the threshold. Caller commits.

        Only promotes `unverified` -> `corroborated`; never overrides a `suspect`
        grade (a contradiction outweighs repetition).
        """
        self.conn.execute(
            "UPDATE facts SET corroboration = corroboration + ? WHERE id = ?",
            (by, fact_id),
        )
        self.conn.execute(
            "UPDATE facts SET confidence = ? "
            "WHERE id = ? AND corroboration >= ? AND confidence = ?",
            (CONFIDENCE_CORROBORATED, fact_id, CORROBORATION_THRESHOLD, CONFIDENCE_UNVERIFIED),
        )

    def recent_facts(self, limit: int = 50) -> list[dict[str, str]]:
        rows = self.conn.execute(
            "SELECT text, source, confidence, created_at FROM facts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"text": text, "source": source, "confidence": confidence, "created_at": created_at}
            for text, source, confidence, created_at in reversed(rows)
        ]

    def recall_facts(self, limit: int = 50) -> list[dict[str, str]]:
        """Return active facts for agent context, most-durable first.

        Ordered static -> slow -> volatile (ungraded last), then by corroboration
        (cross-session support) and recency within a bucket. This is the
        retrieval the agent reads as "what I know about you"; the corroboration
        tiebreak weights well-supported facts into the top-`limit` cut.
        """
        rows = self.conn.execute(
            "SELECT text, volatility, confidence, corroboration FROM facts "
            "WHERE status = 'active' "
            "ORDER BY CASE volatility WHEN 'static' THEN 0 WHEN 'slow' THEN 1 "
            "WHEN 'volatile' THEN 2 ELSE 3 END, corroboration DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "text": text,
                "volatility": volatility,
                "confidence": confidence,
                "corroboration": corroboration,
            }
            for text, volatility, confidence, corroboration in rows
        ]

    def count_corroborated(self) -> int:
        """Number of active facts promoted to `corroborated` certainty."""
        (n,) = self.conn.execute(
            "SELECT COUNT(*) FROM facts WHERE status = 'active' AND confidence = ?",
            (CONFIDENCE_CORROBORATED,),
        ).fetchone()
        return n

    def facts_for_grading(self) -> list[dict]:
        """Return all `active` facts with the fields the grading pass needs.

        Includes already-graded facts so the pass can re-evaluate TTL on
        volatile ones; the grader decides what to skip.
        """
        rows = self.conn.execute(
            "SELECT id, text, source, confidence, volatility, status, valid_as_of, "
            "graded_at, grade_method, created_at FROM facts WHERE status = 'active' ORDER BY id"
        ).fetchall()
        cols = [
            "id", "text", "source", "confidence", "volatility", "status",
            "valid_as_of", "graded_at", "grade_method", "created_at",
        ]
        return [dict(zip(cols, row, strict=True)) for row in rows]

    def update_fact_grade(
        self, fact_id: int, volatility: str, status: str, method: str = "heuristic"
    ) -> None:
        """Persist a grading decision: volatility bucket, lifecycle status, watermark.

        `method` records who graded it (`heuristic` = G1 patterns, `llm` = G2),
        so a later pass can re-grade only what it hasn't seen.
        """
        self.conn.execute(
            "UPDATE facts SET volatility = ?, status = ?, graded_at = ?, grade_method = ? "
            "WHERE id = ?",
            (volatility, status, datetime.now(UTC).isoformat(), method, fact_id),
        )
        self.conn.commit()

    def merge_fact(self, fact_id: int, canonical_id: int) -> None:
        """Fold a duplicate into its canonical fact (reversible: status only).

        The duplicate's corroboration carries onto the canonical: a near-dup that
        G3 merged is the same fact stated in another session, so the merge is
        itself cross-session support and may promote the canonical's certainty.
        """
        loser = self.conn.execute(
            "SELECT corroboration FROM facts WHERE id = ?", (fact_id,)
        ).fetchone()
        self.conn.execute(
            "UPDATE facts SET status = 'merged', canonical_id = ? WHERE id = ?",
            (canonical_id, fact_id),
        )
        if loser:
            self._bump_corroboration(canonical_id, by=loser[0])
        self.conn.commit()

    def supersede_fact(self, fact_id: int, superseded_by: int) -> None:
        """Mark a fact obsoleted by a newer one (reversible: status only)."""
        self.conn.execute(
            "UPDATE facts SET status = 'superseded', superseded_by = ? WHERE id = ?",
            (superseded_by, fact_id),
        )
        self.conn.commit()
