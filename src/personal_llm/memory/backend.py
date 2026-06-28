"""The `MemoryBackend` protocol — the swap seam for L4 memory.

Exactly one production implementation lives behind this at a time (currently
`SqliteBackend`). The protocol is the contract that keeps the memory layer
pluggable without the project carrying two backends.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MemoryBackend(Protocol):
    """Recall-memory store for conversation turns.

    Implementations are constructed with the vault path and own their storage
    underneath it; all methods operate on that one vault.
    """

    def new_session_id(self) -> str:
        """Return a fresh, unique session identifier."""
        ...

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        """Persist one conversation turn."""
        ...

    def recent_turns(self, limit: int = 20) -> list[dict[str, str]]:
        """Return the most recent turns across all sessions, oldest first.

        Each turn is a dict with `role` and `content` keys.
        """
        ...

    def turn_counts_for_today(self) -> dict[str, int]:
        """Return `{'sessions': int, 'turns': int}` for turns logged today (UTC)."""
        ...

    def append_fact(self, text: str, source: str, confidence: str = "unverified") -> bool:
        """Persist a distilled fact about the user. Returns True if newly stored.

        `confidence` is an epistemic tag; auto-distilled facts default to
        `"unverified"` since they come from conversation and aren't checked.
        It is the thin seam for the fuller fact-epistemics model (certainty /
        volatility / provenance) deferred to ARCHITECTURE.md §4 L4.

        Idempotent on `text`: re-inserting an identical fact is a no-op and
        returns False, so distillation re-runs don't duplicate. A no-op
        re-assertion from a *different* source still corroborates the existing
        fact (raising its corroboration count and, past a threshold, its
        certainty).
        """
        ...

    def recent_facts(self, limit: int = 50) -> list[dict[str, str]]:
        """Return the most recently stored facts, oldest first.

        Each fact is a dict with `text`, `source`, `confidence`, and
        `created_at` keys.
        """
        ...

    def recall_facts(self, limit: int = 50) -> list[dict[str, str]]:
        """Return active facts for agent context, most-durable first.

        Each fact is a dict with `text`, `volatility`, `confidence`, and
        `corroboration` keys. Ordered static -> slow -> volatile so the agent
        sees stable facts first, with cross-session corroboration as the
        within-bucket tiebreak.
        """
        ...

    def facts_needing_embedding(self, model: str) -> list[dict]:
        """Return active facts lacking an embedding for `model` (id + text).

        A fact embedded under a different model name counts as missing, so a
        model change triggers a re-embed.
        """
        ...

    def store_fact_embedding(self, fact_id: int, model: str, vector: list[float]) -> None:
        """Persist (replacing any prior) one fact's embedding vector."""
        ...

    def search_facts(self, query_vector: list[float], k: int, model: str) -> list[dict]:
        """Return the `k` active facts most similar to `query_vector`, best first.

        Each result is a dict with `text`, `volatility`, `confidence`,
        `corroboration`, and a cosine `score`.
        """
        ...

    def facts_with_embeddings(self, model: str) -> list[dict]:
        """Return active facts that have an embedding for `model`.

        Each is `{id, text, vector}` with the vector unpacked to a list of
        floats — the input to embedding-based dedup clustering.
        """
        ...

    def document_by_sha(self, sha256: str) -> dict | None:
        """Return `{id, title, n_chunks}` for an ingested document, or None."""
        ...

    def delete_document_by_path(self, source_path: str) -> bool:
        """Delete document(s) at `source_path` and their chunks; True if any removed."""
        ...

    def add_document(
        self,
        source_path: str,
        title: str,
        sha256: str,
        chunks: list[str],
        vectors: list[list[float]],
        model: str,
    ) -> int:
        """Insert a document and its embedded chunks; return the document id."""
        ...

    def list_documents(self) -> list[dict]:
        """Return all ingested documents (`title`, `source_path`, `n_chunks`, `ingested_at`)."""
        ...

    def search_chunks(self, query_vector: list[float], k: int, model: str) -> list[dict]:
        """Return the `k` document chunks most similar to `query_vector`, best first.

        Each is a dict with `text`, `ordinal`, `title`, `source_path`, and `score`.
        """
        ...

    def count_corroborated(self) -> int:
        """Return how many active facts carry `corroborated` certainty.

        A before/after delta over a sleep cycle is how the growth log reports
        newly promoted facts.
        """
        ...

    def facts_for_grading(self) -> list[dict]:
        """Return all `active` facts (with `id`) for the consolidation pass.

        Each row carries id/text/source/confidence/volatility/status/
        valid_as_of/graded_at/grade_method/created_at — enough to grade, to
        re-check TTL, and to tell a heuristic grade from an LLM one.
        """
        ...

    def update_fact_grade(
        self, fact_id: int, volatility: str, status: str, method: str = "heuristic"
    ) -> None:
        """Persist one grading decision (volatility bucket + lifecycle + method)."""
        ...

    def merge_fact(self, fact_id: int, canonical_id: int) -> None:
        """Fold a duplicate fact into its canonical (status `merged`).

        The duplicate's corroboration carries onto the canonical, since the merge
        is itself cross-session evidence for the same fact.
        """
        ...

    def supersede_fact(self, fact_id: int, superseded_by: int) -> None:
        """Mark a fact obsoleted by a newer one (status `superseded`)."""
        ...
