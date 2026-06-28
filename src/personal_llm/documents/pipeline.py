"""Document ingest + retrieval — parse, chunk, embed, store, search.

The book/document side of the L4 vector layer, mirroring the fact pipeline. A
document is parsed to text, chunked, each chunk embedded with the local model,
and stored in the vault (`documents` + `doc_chunks`). Retrieval is brute-force
cosine over the chunks, the same engine as fact recall.

Idempotent by content hash: re-ingesting identical bytes is a no-op; re-ingesting
a changed file at the same path replaces the prior version.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from personal_llm.config import VaultConfig
from personal_llm.documents.chunking import chunk_text
from personal_llm.documents.parsers import extract_text
from personal_llm.memory import MemoryBackend

# Maps a batch of strings to one vector each. Injectable for tests.
Embedder = Callable[[list[str]], list[list[float]]]

EMBED_BATCH = 64


@dataclass
class IngestResult:
    title: str
    chunks: int
    skipped: bool = False   # identical content already ingested
    replaced: bool = False  # superseded a prior version at the same path
    empty: bool = False     # parsed but yielded no text (e.g. a scanned PDF)


def _default_embedder(config: VaultConfig) -> Embedder:
    from personal_llm.inference.local import LocalModelClient

    client = LocalModelClient(
        config.embedding_model.name, config.embedding_model.endpoint
    )
    return client.embed


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _embed_all(embedder: Embedder, chunks: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), EMBED_BATCH):
        vectors.extend(embedder(chunks[start : start + EMBED_BATCH]))
    return vectors


def ingest_document(
    backend: MemoryBackend,
    config: VaultConfig,
    path: Path,
    embedder: Embedder | None = None,
) -> IngestResult:
    """Parse, chunk, embed, and store one document. Idempotent by content hash."""
    embedder = embedder or _default_embedder(config)
    sha = _sha256(path)

    existing = backend.document_by_sha(sha)
    if existing:
        return IngestResult(
            title=existing["title"], chunks=existing["n_chunks"], skipped=True
        )

    chunks = chunk_text(extract_text(path))
    if not chunks:
        # No extractable text (e.g. a scanned/image-only PDF). Don't store an
        # empty document; let the caller report it.
        return IngestResult(title=path.stem, chunks=0, empty=True)

    replaced = backend.delete_document_by_path(str(path))
    vectors = _embed_all(embedder, chunks)
    backend.add_document(
        str(path), path.stem, sha, chunks, vectors, config.embedding_model.name
    )
    return IngestResult(title=path.stem, chunks=len(chunks), replaced=replaced)


def search_documents(
    backend: MemoryBackend,
    config: VaultConfig,
    query: str,
    k: int = 5,
    embedder: Embedder | None = None,
) -> list[dict]:
    """Return the `k` document chunks most similar to `query`, best first."""
    embedder = embedder or _default_embedder(config)
    query_vector = embedder([query])[0]
    return backend.search_chunks(query_vector, k, config.embedding_model.name)
