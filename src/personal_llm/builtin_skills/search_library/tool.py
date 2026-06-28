"""Implementation of the search_library skill.

Spec in the sibling SKILL.md. Semantic search over the user's ingested document
library (books, PDFs, notes) — the agent's RAG tool. The adapter currys
`vault_root`; from the agent's view the tool takes `query` and an optional `k`
and returns relevant passages with citations as a string.

Degrades gracefully: an empty library or an unreachable embedding model returns
a plain message rather than raising, so a library lookup never derails a turn.
"""

from __future__ import annotations

from pathlib import Path

MAX_RESULTS = 8


class SearchLibraryError(ValueError):
    """Raised when a search_library call has invalid input (e.g. empty query)."""


def run(vault_root: Path, query: str, k: int = 5) -> str:
    """Search the ingested document library for passages relevant to `query`."""
    query = (query or "").strip()
    if not query:
        raise SearchLibraryError("query must not be empty")
    k = max(1, min(int(k), MAX_RESULTS))

    from personal_llm import config as config_mod
    from personal_llm.documents.pipeline import search_documents
    from personal_llm.inference.local import LocalModelClient
    from personal_llm.memory import open_backend

    vault_root = Path(vault_root)
    config = config_mod.load(vault_root)

    ok, _ = LocalModelClient(
        config.embedding_model.name, config.embedding_model.endpoint
    ).health()
    if not ok:
        return "Library search is unavailable right now (embedding model unreachable)."

    results = search_documents(open_backend(vault_root), config, query, k=k)
    if not results:
        return (
            "No relevant passages found in the library — nothing has been "
            "ingested yet, or nothing matched the query."
        )

    blocks = []
    for r in results:
        passage = " ".join(r["text"].split())
        blocks.append(
            f"[{r['title']} #{r['ordinal']}] (relevance {r['score']:.2f})\n{passage}"
        )
    return "\n\n".join(blocks)
