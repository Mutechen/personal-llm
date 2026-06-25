"""Tests for embedding compute + semantic search over facts.

A fake embedder maps known strings to fixed vectors, so the whole path runs
without Ollama.
"""

from __future__ import annotations

from pathlib import Path

from personal_llm.config import VaultConfig
from personal_llm.learning.embeddings import embed_facts, semantic_search
from personal_llm.memory import SqliteBackend

_VECTORS = {
    "the user loves python": [1.0, 0.0, 0.0, 0.0],
    "the user dislikes mornings": [0.0, 1.0, 0.0, 0.0],
    "the user lives in berlin": [0.0, 0.0, 1.0, 0.0],
    "the user plays guitar": [0.0, 0.0, 0.0, 1.0],
    "what language does the user like?": [0.9, 0.1, 0.0, 0.0],
    "any musical hobbies?": [0.0, 0.0, 0.1, 0.9],
}


def _embedder(texts: list[str]) -> list[list[float]]:
    return [_VECTORS[t] for t in texts]


def _seed(backend: SqliteBackend) -> None:
    for text in ("the user loves python", "the user dislikes mornings", "the user lives in berlin"):
        backend.append_fact(text, "transcript:s1")


def test_embed_facts_is_idempotent(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _seed(backend)
    cfg = VaultConfig()

    first = embed_facts(backend, cfg, embedder=_embedder)
    assert first.facts_embedded == 3
    second = embed_facts(backend, cfg, embedder=_embedder)
    assert second.facts_embedded == 0  # nothing new to embed


def test_semantic_search_finds_relevant_fact(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _seed(backend)

    results = semantic_search(
        backend, VaultConfig(), "what language does the user like?", k=2, embedder=_embedder
    )
    assert results[0]["text"] == "the user loves python"
    assert len(results) == 2


def test_semantic_search_no_ensure_skips_backlog(tmp_path: Path):
    """The agent path (ensure_embedded=False) searches only what's embedded and
    does not embed the backlog mid-conversation."""
    backend = SqliteBackend(tmp_path)
    _seed(backend)
    embed_facts(backend, VaultConfig(), embedder=_embedder)
    backend.append_fact("the user plays guitar", "transcript:s2")  # not embedded yet

    results = semantic_search(
        backend,
        VaultConfig(),
        "any musical hobbies?",
        k=3,
        embedder=_embedder,
        ensure_embedded=False,
    )
    # the new fact was never embedded, so it can't surface...
    assert "the user plays guitar" not in [r["text"] for r in results]
    # ...and the call left it un-embedded (no backlog compute happened).
    assert backend.facts_needing_embedding("nomic-embed-text") == [
        {"id": next(f["id"] for f in backend.facts_for_grading() if f["text"] == "the user plays guitar"),
         "text": "the user plays guitar"}
    ]


def test_semantic_search_embeds_new_facts_first(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _seed(backend)
    embed_facts(backend, VaultConfig(), embedder=_embedder)
    # A fact added after the last compute must still be searchable: semantic_search
    # embeds the backlog before querying.
    backend.append_fact("the user plays guitar", "transcript:s2")

    results = semantic_search(
        backend, VaultConfig(), "any musical hobbies?", k=1, embedder=_embedder
    )
    assert results[0]["text"] == "the user plays guitar"
