"""Tests for document text extraction (txt/md/epub; pdf is exercised live)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from personal_llm.documents.parsers import (
    DocumentParseError,
    UnsupportedDocument,
    extract_text,
)


def test_extract_txt(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("Hello\n\nWorld", encoding="utf-8")
    text = extract_text(p)
    assert "Hello" in text and "World" in text


def test_extract_markdown(tmp_path: Path):
    p = tmp_path / "a.md"
    p.write_text("# Title\n\nsome body", encoding="utf-8")
    assert "some body" in extract_text(p)


def test_unsupported_extension_raises(tmp_path: Path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"\x00\x01")
    with pytest.raises(UnsupportedDocument):
        extract_text(p)


def _make_epub(path: Path) -> None:
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        "<manifest>"
        '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/>'
        "</manifest>"
        '<spine><itemref idref="c1"/><itemref idref="c2"/></spine>'
        "</package>"
    )
    ch1 = "<html><body><h1>Chapter One</h1><p>The quick brown fox.</p></body></html>"
    ch2 = (
        "<html><body><p>Jumps over the lazy dog.</p>"
        "<script>ignore_me()</script></body></html>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/ch1.xhtml", ch1)
        z.writestr("OEBPS/ch2.xhtml", ch2)


def test_corrupt_pdf_raises_parse_error(tmp_path: Path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"%PDF-1.4 this is not a real pdf")
    with pytest.raises(DocumentParseError):
        extract_text(p)


def test_corrupt_epub_raises_parse_error(tmp_path: Path):
    p = tmp_path / "broken.epub"
    p.write_bytes(b"definitely not a zip archive")
    with pytest.raises(DocumentParseError):
        extract_text(p)


def test_extract_epub_reads_spine_and_strips_scripts(tmp_path: Path):
    p = tmp_path / "book.epub"
    _make_epub(p)
    text = extract_text(p)
    assert "Chapter One" in text
    assert "quick brown fox" in text
    assert "lazy dog" in text
    assert "ignore_me" not in text  # <script> content dropped
