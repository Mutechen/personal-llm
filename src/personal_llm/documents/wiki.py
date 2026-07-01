"""Generate Karpathy-style wiki pages from the ingested document library.

For each ingested document the local model writes a short wiki page — a summary
plus key topics — under `wiki/library/`, with frontmatter that cites the source
and records its content hash. Idempotent: a page is regenerated only when its
document's hash changes, so the nightly loop summarizes only what's new.

Retrieval's companion: search finds passages; the wiki gives the agent (and the
user, in Obsidian) a navigable, linked overview of what the library contains.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from personal_llm.config import VaultConfig
from personal_llm.memory import MemoryBackend

# Maps (title, excerpts) -> a short markdown summary. Injectable for tests.
Summarizer = Callable[[str, str], str]

WIKI_SUBDIR = "wiki/library"
SAMPLE_CHUNKS = 10      # how many chunks to feed the summarizer
SAMPLE_CHAR_CAP = 6000  # cap the prompt so it fits the local context window

_SYSTEM = "You write concise, factual wiki summaries of documents. Output only markdown."

_PROMPT = """\
Below are excerpts from a document titled "{title}". Write a brief wiki entry:

1. A 3-5 sentence summary of what the document is about.
2. A "## Key topics" section with 3-6 bullet points.

Be factual and concise; do not invent details beyond the excerpts. Output only
the markdown body — no top-level title, no frontmatter.

EXCERPTS:
{excerpts}
"""


@dataclass
class WikiResult:
    generated: int = 0
    skipped: int = 0
    pages_dir: Path | None = None


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)


def _slug(title: str, doc_id: int) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or f"doc-{doc_id}"


def _read_source_sha(page_path: Path) -> str | None:
    """Return the `source_sha` from a page's frontmatter, or None if absent."""
    if not page_path.is_file():
        return None
    text = page_path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    return meta.get("source_sha")


def _default_summarizer(config: VaultConfig) -> Summarizer:
    from personal_llm.inference.local import LocalModelClient

    client = LocalModelClient(config.local_model.name, config.local_model.endpoint)

    def summarize(title: str, excerpts: str) -> str:
        return client.complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _PROMPT.format(title=title, excerpts=excerpts)},
            ]
        )

    return summarize


def _render_page(doc: dict, body: str) -> str:
    front = yaml.safe_dump(
        {
            "title": doc["title"],
            "source": doc["source_path"],
            "source_sha": doc["sha256"],
            "chunks": doc["n_chunks"],
            "generated_at": datetime.now(UTC).isoformat(),
            "generated_by": "personal-llm sleep",
        },
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    return (
        f"---\n{front}\n---\n\n"
        f"# {doc['title']}\n\n"
        f"{body}\n\n"
        f"## Source\n\n"
        f"Ingested from `{doc['source_path']}` ({doc['n_chunks']} chunks). "
        f"Search it with `personal-llm books search`.\n"
    )


def _write_index(pages_dir: Path, entries: list[tuple[str, str]]) -> None:
    lines = ["# Library", "", "Auto-generated summaries of ingested documents.", ""]
    for slug, title in sorted(entries, key=lambda e: e[1].lower()):
        lines.append(f"- [[{slug}|{title}]]")
    (pages_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_library_wiki(
    vault_path: Path,
    config: VaultConfig,
    backend: MemoryBackend,
    summarizer: Summarizer | None = None,
) -> WikiResult:
    """Write/refresh a wiki page per ingested document; rebuild the index.

    A page whose frontmatter `source_sha` already matches its document is left
    untouched, so re-runs only summarize new or changed documents.
    """
    summarizer = summarizer or _default_summarizer(config)
    pages_dir = vault_path / WIKI_SUBDIR
    result = WikiResult(pages_dir=pages_dir)

    docs = backend.list_documents()
    if not docs:
        return result
    pages_dir.mkdir(parents=True, exist_ok=True)

    index_entries: list[tuple[str, str]] = []
    for doc in docs:
        slug = _slug(doc["title"], doc["id"])
        index_entries.append((slug, doc["title"]))
        page = pages_dir / f"{slug}.md"
        if _read_source_sha(page) == doc["sha256"]:
            result.skipped += 1
            continue
        sample = backend.document_chunk_texts(doc["id"], SAMPLE_CHUNKS)
        excerpts = "\n\n".join(sample)[:SAMPLE_CHAR_CAP]
        body = _strip_think(summarizer(doc["title"], excerpts)).strip()
        page.write_text(_render_page(doc, body), encoding="utf-8")
        result.generated += 1

    _write_index(pages_dir, index_entries)
    return result
