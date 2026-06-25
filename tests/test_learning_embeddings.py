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
