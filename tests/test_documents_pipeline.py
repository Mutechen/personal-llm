"""Tests for the document ingest pipeline (parse -> chunk -> embed -> store).

A constant embedder keeps it model-free; chunk-ranking correctness lives in the
backend's search_chunks test, which controls vectors directly.
"""

from __future__ import annotations

from pathlib import Path

from personal_llm.config import VaultConfig
from personal_llm.documents.pipeline import ingest_document, search_documents
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


def test_search_documents_returns_hits(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    doc = _doc(tmp_path, "book.txt", "alpha beta\n\ngamma delta")
    ingest_document(backend, VaultConfig(), doc, embedder=_embedder)

    results = search_documents(backend, VaultConfig(), "anything", k=3, embedder=_embedder)
    assert results
    assert results[0]["title"] == "book"
    assert "score" in results[0]
