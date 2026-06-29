"""Tests for the document ingest pipeline (parse -> chunk -> embed -> store).

A constant embedder keeps it model-free; chunk-ranking correctness lives in the
backend's search_chunks test, which controls vectors directly.
"""

from __future__ import annotations

from pathlib import Path

from personal_llm.config import VaultConfig
from personal_llm.documents.pipeline import (
    ingest_directory,
    ingest_document,
    search_documents,
)
from personal_llm.memory import SqliteBackend


def _embedder(texts: list[str]) -> list[list[float]]:
    return [[1.0, 0.0] for _ in texts]


def _doc(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_ingest_parses_chunks_and_stores(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    doc = _doc(tmp_path, "book.txt", "alpha beta\n\ngamma delta")

    result = ingest_document(backend, VaultConfig(), doc, embedder=_embedder)

    assert not result.skipped
    assert result.chunks >= 1
    assert backend.list_documents()[0]["title"] == "book"


def test_ingest_is_idempotent_on_content(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    doc = _doc(tmp_path, "book.txt", "same content here")

    first = ingest_document(backend, VaultConfig(), doc, embedder=_embedder)
    second = ingest_document(backend, VaultConfig(), doc, embedder=_embedder)

    assert not first.skipped
    assert second.skipped
    assert len(backend.list_documents()) == 1  # not duplicated


def test_ingest_replaces_changed_content_at_same_path(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    doc = _doc(tmp_path, "book.txt", "first version of the text")
    ingest_document(backend, VaultConfig(), doc, embedder=_embedder)

    doc.write_text("a totally different second version", encoding="utf-8")
    result = ingest_document(backend, VaultConfig(), doc, embedder=_embedder)

    assert result.replaced
    assert not result.skipped
    assert len(backend.list_documents()) == 1  # old version removed


def test_ingest_empty_text_is_not_stored(tmp_path: Path):
    """A document that yields no text (e.g. a scanned PDF) is reported, not stored."""
    backend = SqliteBackend(tmp_path)
    doc = _doc(tmp_path, "scanned.txt", "   \n\n   ")  # whitespace-only -> no chunks

    result = ingest_document(backend, VaultConfig(), doc, embedder=_embedder)

    assert result.empty
    assert result.chunks == 0
    assert backend.list_documents() == []


def test_ingest_directory_counts_and_is_idempotent(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "good1.txt").write_text("alpha beta gamma", encoding="utf-8")
    (raw / "good2.md").write_text("# Heading\n\nbody text", encoding="utf-8")
    (raw / "blank.txt").write_text("   \n\n  ", encoding="utf-8")  # no text -> empty
    (raw / "broken.epub").write_bytes(b"not a zip")  # supported type, unparseable
    (raw / "ignore.xyz").write_text("unsupported type, skipped silently", encoding="utf-8")

    first = ingest_directory(backend, VaultConfig(), raw, embedder=_embedder)
    assert (first.ingested, first.empty, first.failed) == (2, 1, 1)
    assert len(backend.list_documents()) == 2

    second = ingest_directory(backend, VaultConfig(), raw, embedder=_embedder)
    assert (second.ingested, second.skipped) == (0, 2)  # unchanged on re-run


def test_ingest_directory_missing_dir_is_noop(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    summary = ingest_directory(backend, VaultConfig(), tmp_path / "nope", embedder=_embedder)
    assert (summary.ingested, summary.skipped, summary.failed) == (0, 0, 0)


def test_search_documents_returns_hits(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    doc = _doc(tmp_path, "book.txt", "alpha beta\n\ngamma delta")
    ingest_document(backend, VaultConfig(), doc, embedder=_embedder)

    results = search_documents(backend, VaultConfig(), "anything", k=3, embedder=_embedder)
    assert results
    assert results[0]["title"] == "book"
    assert "score" in results[0]
