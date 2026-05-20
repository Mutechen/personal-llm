"""L4 — Memory & knowledge base.

Recall memory lives behind the `MemoryBackend` protocol. `open_backend` is the
single entry point consumers use to get the active backend for a vault.

Current backends: `JsonlBackend` (transitional, the Phase 0 store) and
`SqliteBackend`. `open_backend` still returns `JsonlBackend` until L-3 flips the
default and deletes it.
"""

from __future__ import annotations

from pathlib import Path

from personal_llm.memory.backend import MemoryBackend
from personal_llm.memory.jsonl import JsonlBackend
from personal_llm.memory.sqlite import SqliteBackend

__all__ = ["JsonlBackend", "MemoryBackend", "SqliteBackend", "open_backend"]


def open_backend(vault_path: Path) -> MemoryBackend:
    """Return the memory backend for a vault. The single swap point for L4."""
    return JsonlBackend(vault_path)
