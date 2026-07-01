"""Tests for library wiki generation (a fake summarizer keeps it model-free)."""

from __future__ import annotations

from pathlib import Path

from personal_llm.config import VaultConfig
from personal_llm.documents.wiki import _slug, build_library_wiki
from personal_llm.memory import SqliteBackend


def _summ(title: str, excerpts: str) -> str:
    return f"This is about {title}.\n\n## Key topics\n- alpha\n- beta"


def _add(backend: SqliteBackend, title: str, sha: str) -> None:
    backend.add_document(
        f"/raw/{title}.txt", title, sha,
        ["chunk one text", "chunk two text"], [[1.0, 0.0], [0.0, 1.0]], "m1",
    )


def test_slug_and_non_latin_fallback():
    assert _slug("Hello World", 1) == "hello-world"
    assert _slug("العقيدة", 7) == "doc-7"  # no latin chars -> id fallback


def test_build_generates_page_and_index(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _add(backend, "My Book", "sha1")

    res = build_library_wiki(tmp_path, VaultConfig(), backend, summarizer=_summ)
    assert (res.generated, res.skipped) == (1, 0)

    page = tmp_path / "wiki" / "library" / "my-book.md"
    text = page.read_text(encoding="utf-8")
    assert "source_sha: sha1" in text  # frontmatter cites the source hash
    assert "# My Book" in text
    assert "This is about My Book" in text
    assert "## Source" in text
    assert "/raw/My Book.txt" in text

    index = (tmp_path / "wiki" / "library" / "index.md").read_text(encoding="utf-8")
    assert "[[my-book|My Book]]" in index


def test_build_is_idempotent_until_sha_changes(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    _add(backend, "My Book", "sha1")
    build_library_wiki(tmp_path, VaultConfig(), backend, summarizer=_summ)

    second = build_library_wiki(tmp_path, VaultConfig(), backend, summarizer=_summ)
    assert (second.generated, second.skipped) == (0, 1)

    # A changed document (new hash) is re-summarized.
    backend.delete_document_by_path("/raw/My Book.txt")
    _add(backend, "My Book", "sha2")
    third = build_library_wiki(tmp_path, VaultConfig(), backend, summarizer=_summ)
    assert third.generated == 1


def test_build_empty_library_is_noop(tmp_path: Path):
    backend = SqliteBackend(tmp_path)
    res = build_library_wiki(tmp_path, VaultConfig(), backend, summarizer=_summ)
    assert (res.generated, res.skipped) == (0, 0)
    assert not (tmp_path / "wiki" / "library").exists()
