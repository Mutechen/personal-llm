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
from personal_llm.documents.chunking import chunk_segments
from personal_llm.documents.parsers import (
    SUPPORTED_SUFFIXES,
    DocumentParseError,
    UnsupportedDocument,
    extract_segments,
)
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


@dataclass
class IngestSummary:
    """Outcome of ingesting a directory of documents (e.g. the nightly raw/ scan)."""

    ingested: int = 0   # newly ingested or replaced (chunks stored)
    skipped: int = 0    # unchanged (already ingested)
    empty: int = 0      # no extractable text (e.g. scanned PDFs)
    failed: int = 0     # unsupported type or parse error
    chunks: int = 0     # total chunks added this run


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

    located = chunk_segments(extract_segments(path))
    if not located:
        # No extractable text (e.g. a scanned/image-only PDF). Don't store an
        # empty document; let the caller report it.
        return IngestResult(title=path.stem, chunks=0, empty=True)

    locations = [loc for loc, _ in located]
    texts = [text for _, text in located]
    replaced = backend.delete_document_by_path(str(path))
    vectors = _embed_all(embedder, texts)
    backend.add_document(
        str(path), path.stem, sha, texts, vectors,
        config.embedding_model.name, locations=locations,
    )
    return IngestResult(title=path.stem, chunks=len(texts), replaced=replaced)


def ingest_directory(
    backend: MemoryBackend,
    config: VaultConfig,
    directory: Path,
    embedder: Embedder | None = None,
) -> IngestSummary:
    """Ingest every supported document under `directory` (recursively).

    Idempotent (per-file content hash), so re-running only does new/changed work.
    A single unparseable file is counted and skipped, never aborting the rest —
    this is what the nightly loop runs over the vault's `raw/`.
    """
    summary = IngestSummary()
    if not directory.is_dir():
        return summary
    embedder = embedder or _default_embedder(config)

    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            result = ingest_document(backend, config, path, embedder=embedder)
        except (UnsupportedDocument, DocumentParseError):
            summary.failed += 1
            continue
        if result.empty:
            summary.empty += 1
        elif result.skipped:
            summary.skipped += 1
        else:
            summary.ingested += 1
            summary.chunks += result.chunks
    return summary


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
