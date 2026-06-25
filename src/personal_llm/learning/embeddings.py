"""Embedding compute + semantic search over facts.

The first consumer of the L4 vector layer (memory/vector.py). It proves the
embedding foundation on the data already in the vault — the curated facts —
before any book/document corpus is ingested:

- `embed_facts` computes and stores embeddings for active facts that lack one
  (idempotent — re-runs only touch new or re-graded facts),
- `semantic_search` embeds a query and returns the closest facts.

The embedder is injectable so the whole path is testable without a live model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from personal_llm.config import VaultConfig
from personal_llm.memory import MemoryBackend

# Maps a batch of strings to one vector each. Injectable for tests.
Embedder = Callable[[list[str]], list[list[float]]]

# Embed in batches so one Ollama call doesn't have to hold the whole backlog.
EMBED_BATCH = 64


@dataclass
class EmbedResult:
    facts_embedded: int = 0


def _default_embedder(config: VaultConfig) -> Embedder:
    from personal_llm.inference.local import LocalModelClient

    client = LocalModelClient(
        config.embedding_model.name, config.embedding_model.endpoint
    )
    return client.embed


def embed_facts(
    backend: MemoryBackend,
    config: VaultConfig,
    embedder: Embedder | None = None,
) -> EmbedResult:
    """Embed and store any active facts missing an embedding for the model."""
    embedder = embedder or _default_embedder(config)
    model = config.embedding_model.name

    pending = backend.facts_needing_embedding(model)
    embedded = 0
    for start in range(0, len(pending), EMBED_BATCH):
        batch = pending[start : start + EMBED_BATCH]
        vectors = embedder([f["text"] for f in batch])
        for fact, vector in zip(batch, vectors, strict=True):
            backend.store_fact_embedding(fact["id"], model, vector)
            embedded += 1
    return EmbedResult(facts_embedded=embedded)


def semantic_search(
    backend: MemoryBackend,
    config: VaultConfig,
    query: str,
    k: int = 5,
    embedder: Embedder | None = None,
) -> list[dict]:
    """Return the `k` active facts most similar to `query`.

    Ensures embeddings are current first, so a fact added since the last compute
    is still findable.
    """
    embedder = embedder or _default_embedder(config)
    embed_facts(backend, config, embedder=embedder)
    query_vector = embedder([query])[0]
    return backend.search_facts(query_vector, k, config.embedding_model.name)
