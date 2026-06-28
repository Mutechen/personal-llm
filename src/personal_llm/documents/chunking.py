"""Split a document's text into overlapping chunks for embedding.

Paragraph-aware greedy packing: paragraphs accumulate into a chunk until adding
the next would exceed `target_chars`; a fresh chunk is seeded with the tail of
the previous one (`overlap_chars`) so a fact split across a boundary is still
retrievable from at least one chunk. Oversized single paragraphs are hard-split.

Character-based, not token-based — no tokenizer dependency, and the embedding
model's context far exceeds these chunk sizes.
"""

from __future__ import annotations

import re

TARGET_CHARS = 1000
OVERLAP_CHARS = 200

_INLINE_WS = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")


def normalize(text: str) -> str:
    """Collapse inline whitespace and blank-line runs; unify newlines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _INLINE_WS.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def _tail(text: str, n: int) -> str:
    """Last ~n chars of text, cut at a word boundary so overlap stays readable."""
    if n <= 0 or len(text) <= n:
        return text if n > 0 else ""
    tail = text[-n:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def _hard_split(para: str, target: int, overlap: int) -> list[str]:
    """Split a paragraph longer than `target` into overlapping windows."""
    chunks = []
    start = 0
    step = max(1, target - overlap)
    while start < len(para):
        chunk = para[start : start + target].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def chunk_text(
    text: str, target_chars: int = TARGET_CHARS, overlap_chars: int = OVERLAP_CHARS
) -> list[str]:
    """Return the document split into overlapping, paragraph-aligned chunks."""
    text = normalize(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > target_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(para, target_chars, overlap_chars))
            continue

        if current and len(current) + 2 + len(para) > target_chars:
            chunks.append(current)
            seed = _tail(current, overlap_chars)
            current = f"{seed}\n\n{para}" if seed else para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current)
    return chunks
