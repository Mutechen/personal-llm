"""L4 — Memory & knowledge base.

Recall memory lives behind the `MemoryBackend` protocol. `open_backend` is the
single entry point consumers use to get the active backend for a vault.

Current backend: `SqliteBackend` (stdlib sqlite3, one DB per vault). Semantic /
archival search via sqlite-vss is a later chunk.
"""

from __future__ import annotations

from pathlib import Path

from personal_llm.memory.backend import MemoryBackend
from personal_llm.memory.sqlite import SqliteBackend

__all__ = ["MemoryBackend", "SqliteBackend", "open_backend"]


def open_backend(vault_path: Path) -> MemoryBackend:
    """Return the memory backend for a vault. The single swap point for L4."""
    return SqliteBackend(vault_path)
