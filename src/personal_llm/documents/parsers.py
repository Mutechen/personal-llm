"""Extract plain text from a document for ingestion.

Dispatches by file extension. Text/markdown are read directly; PDF goes through
`pypdf`; EPUB is unzipped and its spine read with the stdlib (no lxml) — an EPUB
is a ZIP of XHTML described by an OPF package file.

Extraction is best-effort: the goal is searchable prose, not perfect layout. The
chunker downstream normalizes whitespace, so parsers don't need to.
"""

from __future__ import annotations

import posixpath
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".pdf", ".epub"}


class UnsupportedDocument(ValueError):
    """Raised for a file extension the pipeline can't parse."""


def extract_text(path: Path) -> str:
    """Return the document's text, dispatching on extension."""
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".epub":
        return _extract_epub(path)
    raise UnsupportedDocument(
        f"Unsupported document type {suffix!r}; supported: "
        f"{', '.join(sorted(SUPPORTED_SUFFIXES))}"
    )


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


_SKIP_TAGS = frozenset({"script", "style", "head"})
_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}
)


class _HTMLText(HTMLParser):
    """Collect visible text, dropping script/style and breaking on block tags."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _html_to_text(markup: str) -> str:
    parser = _HTMLText()
    parser.feed(markup)
    return parser.text()


def _local(tag: str) -> str:
    """Strip the XML namespace from a tag name."""
    return tag.rsplit("}", 1)[-1]


def _find_opf(zf: zipfile.ZipFile) -> str:
    root = ET.fromstring(zf.read("META-INF/container.xml"))
    for el in root.iter():
        if _local(el.tag) == "rootfile" and el.get("full-path"):
            return el.get("full-path")
    raise UnsupportedDocument("epub: no rootfile in META-INF/container.xml")


def _extract_epub(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        opf_path = _find_opf(zf)
        opf = ET.fromstring(zf.read(opf_path))
        opf_dir = posixpath.dirname(opf_path)

        manifest: dict[str, str] = {}
        spine: list[str] = []
        for el in opf.iter():
            tag = _local(el.tag)
            if tag == "item" and el.get("id") and el.get("href"):
                manifest[el.get("id")] = el.get("href")
            elif tag == "itemref" and el.get("idref"):
                spine.append(el.get("idref"))

        # Spine gives reading order; fall back to manifest order if absent.
        hrefs = [manifest[i] for i in spine if i in manifest] or list(manifest.values())

        texts: list[str] = []
        for href in hrefs:
            if not href.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            full = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
            try:
                markup = zf.read(full).decode("utf-8", errors="replace")
            except KeyError:
                continue
            texts.append(_html_to_text(markup))
        return "\n\n".join(texts)
