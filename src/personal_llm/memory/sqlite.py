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

CREATE TABLE IF NOT EXISTS fact_embeddings (
    fact_id INTEGER PRIMARY KEY,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    title TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    n_chunks INTEGER NOT NULL DEFAULT 0,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doc_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    location TEXT,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_document ON doc_chunks(document_id);
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

# Columns added to doc_chunks after it first shipped.
_DOC_CHUNK_MIGRATIONS = {
    "location": "ALTER TABLE doc_chunks ADD COLUMN location TEXT",
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
        self._migrate_table("doc_chunks", _DOC_CHUNK_MIGRATIONS)
        self.conn.commit()

    def _migrate_table(self, table: str, migrations: dict[str, str]) -> None:
        """Add any missing columns to `table` (non-breaking ADD COLUMN)."""
        existing = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        for column, ddl in migrations.items():
            if column not in existing:
                self.conn.execute(ddl)

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

    def facts_needing_embedding(self, model: str) -> list[dict]:
        """Active facts with no embedding for `model` (id + text, oldest first).

        Re-embedding after a model change is automatic: a row embedded under a
        different model name is treated as missing, so the new model's vectors
        replace it on the next compute.
        """
        rows = self.conn.execute(
            "SELECT f.id, f.text FROM facts f "
            "LEFT JOIN fact_embeddings e ON e.fact_id = f.id AND e.model = ? "
            "WHERE f.status = 'active' AND e.fact_id IS NULL ORDER BY f.id",
            (model,),
        ).fetchall()
        return [{"id": fid, "text": text} for fid, text in rows]

    def store_fact_embedding(self, fact_id: int, model: str, vector: list[float]) -> None:
        """Persist (replacing any prior) the embedding for one fact."""
        from personal_llm.memory.vector import pack

        self.conn.execute(
            "INSERT OR REPLACE INTO fact_embeddings (fact_id, model, dim, vector) "
            "VALUES (?, ?, ?, ?)",
            (fact_id, model, len(vector), pack(vector)),
        )
        self.conn.commit()

    def search_facts(self, query_vector: list[float], k: int, model: str) -> list[dict]:
        """Return the `k` active facts most similar to `query_vector`, best first.

        Brute-force cosine over stored float32 blobs (see memory/vector.py); only
        embeddings for `model` are considered. Each result carries `text`,
        `volatility`, `confidence`, `corroboration`, and the cosine `score`.
        """
        from personal_llm.memory.vector import cosine_topk

        rows = self.conn.execute(
            "SELECT e.fact_id, e.vector FROM fact_embeddings e "
            "JOIN facts f ON f.id = e.fact_id "
            "WHERE f.status = 'active' AND e.model = ?",
            (model,),
        ).fetchall()
        ranked = cosine_topk(query_vector, [(fid, blob) for fid, blob in rows], k)
        if not ranked:
            return []

        scores = dict(ranked)
        placeholders = ",".join("?" * len(scores))
        meta = self.conn.execute(
            f"SELECT id, text, volatility, confidence, corroboration FROM facts "
            f"WHERE id IN ({placeholders})",
            tuple(scores),
        ).fetchall()
        by_id = {
            fid: {
                "text": text,
                "volatility": volatility,
                "confidence": confidence,
                "corroboration": corroboration,
                "score": scores[fid],
            }
            for fid, text, volatility, confidence, corroboration in meta
        }
        return [by_id[fid] for fid, _ in ranked]

    def facts_with_embeddings(self, model: str) -> list[dict]:
        """Active facts that have an embedding for `model`, vectors unpacked.

        The input to embedding-based dedup clustering: `[{id, text, vector}]`,
        ordered by id. Facts not yet embedded are simply absent (they cluster on
        a later run, once embedded).
        """
        from personal_llm.memory.vector import unpack

        rows = self.conn.execute(
            "SELECT f.id, f.text, e.vector FROM facts f "
            "JOIN fact_embeddings e ON e.fact_id = f.id AND e.model = ? "
            "WHERE f.status = 'active' ORDER BY f.id",
            (model,),
        ).fetchall()
        return [
            {"id": fid, "text": text, "vector": unpack(blob).tolist()}
            for fid, text, blob in rows
        ]

    # --- documents (book/document RAG) -------------------------------------

    def document_by_sha(self, sha256: str) -> dict | None:
        """Return `{id, title, n_chunks}` for an already-ingested document, or None."""
        row = self.conn.execute(
            "SELECT id, title, n_chunks FROM documents WHERE sha256 = ?", (sha256,)
        ).fetchone()
        return {"id": row[0], "title": row[1], "n_chunks": row[2]} if row else None

    def delete_document_by_path(self, source_path: str) -> bool:
        """Delete any document(s) at `source_path` and their chunks. True if any."""
        ids = [
            r[0]
            for r in self.conn.execute(
                "SELECT id FROM documents WHERE source_path = ?", (source_path,)
            )
        ]
        if not ids:
            return False
        placeholders = ",".join("?" * len(ids))
        self.conn.execute(
            f"DELETE FROM doc_chunks WHERE document_id IN ({placeholders})", tuple(ids)
        )
        self.conn.execute(
            f"DELETE FROM documents WHERE id IN ({placeholders})", tuple(ids)
        )
        self.conn.commit()
        return True

    def add_document(
        self,
        source_path: str,
        title: str,
        sha256: str,
        chunks: list[str],
        vectors: list[list[float]],
        model: str,
        locations: list[str] | None = None,
    ) -> int:
        """Insert a document and its embedded chunks; return the document id.

        `locations` (parallel to `chunks`) cites where each chunk came from
        (e.g. `"p.42"`); omitted -> NULL.
        """
        from personal_llm.memory.vector import pack

        if locations is None:
            locations = [None] * len(chunks)
        now = datetime.now(UTC).isoformat()
        cur = self.conn.execute(
            "INSERT INTO documents (source_path, title, sha256, n_chunks, ingested_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (source_path, title, sha256, len(chunks), now),
        )
        doc_id = cur.lastrowid
        self.conn.executemany(
            "INSERT INTO doc_chunks (document_id, ordinal, text, location, model, dim, vector) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (doc_id, i, chunk, loc, model, len(vec), pack(vec))
                for i, (chunk, loc, vec) in enumerate(
                    zip(chunks, locations, vectors, strict=True)
                )
            ],
        )
        self.conn.commit()
        return doc_id

    def list_documents(self) -> list[dict]:
        """All ingested documents, oldest first."""
        rows = self.conn.execute(
            "SELECT title, source_path, n_chunks, ingested_at FROM documents ORDER BY id"
        ).fetchall()
        return [
            {"title": t, "source_path": sp, "n_chunks": n, "ingested_at": ts}
            for t, sp, n, ts in rows
        ]

    def search_chunks(self, query_vector: list[float], k: int, model: str) -> list[dict]:
        """Return the `k` document chunks most similar to `query_vector`, best first.

        Each result carries `text`, `ordinal`, `title`, `source_path`, and the
        cosine `score`.
        """
        from personal_llm.memory.vector import cosine_topk

        rows = self.conn.execute(
            "SELECT id, vector FROM doc_chunks WHERE model = ?", (model,)
        ).fetchall()
        ranked = cosine_topk(query_vector, [(cid, blob) for cid, blob in rows], k)
        if not ranked:
            return []

        scores = dict(ranked)
        placeholders = ",".join("?" * len(scores))
        meta = self.conn.execute(
            f"SELECT c.id, c.text, c.ordinal, c.location, d.title, d.source_path "
            f"FROM doc_chunks c JOIN documents d ON d.id = c.document_id "
            f"WHERE c.id IN ({placeholders})",
            tuple(scores),
        ).fetchall()
        by_id = {
            cid: {
                "text": text,
                "ordinal": ordinal,
                "location": location,
                "title": title,
                "source_path": source_path,
                "score": scores[cid],
            }
            for cid, text, ordinal, location, title, source_path in meta
        }
        return [by_id[cid] for cid, _ in ranked]

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
