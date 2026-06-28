"""Tests for the document chunker."""

from __future__ import annotations

from personal_llm.documents.chunking import chunk_text, normalize


def test_normalize_collapses_whitespace_and_blank_lines():
    assert normalize("a  \t b\n\n\n\nc\r\nd") == "a b\n\nc\nd"


def test_chunk_empty_is_empty():
    assert chunk_text("   \n\n  ") == []


def test_chunk_single_short_paragraph():
    assert chunk_text("Hello world.") == ["Hello world."]


def test_chunk_packs_small_paragraphs_into_one():
    assert chunk_text("a\n\nb\n\nc", target_chars=100) == ["a\n\nb\n\nc"]


def test_chunk_splits_when_over_target_and_covers_all():
    paras = "\n\n".join(f"paragraph number {i} with some filler words here" for i in range(10))
    chunks = chunk_text(paras, target_chars=120, overlap_chars=30)
    assert len(chunks) > 1
    joined = " ".join(chunks)
    for i in range(10):
        assert f"paragraph number {i} " in joined


def test_chunk_hard_splits_long_paragraph_within_target():
    big = "word " * 400  # ~2000 chars, no blank lines -> one paragraph
    chunks = chunk_text(big, target_chars=200, overlap_chars=40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_chunk_consecutive_chunks_overlap():
    big = " ".join(f"w{i}" for i in range(200))  # one long paragraph
    chunks = chunk_text(big, target_chars=120, overlap_chars=40)
    assert len(chunks) >= 2
    assert set(chunks[0].split()) & set(chunks[1].split())  # shared words = overlap
