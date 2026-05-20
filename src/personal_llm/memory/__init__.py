"""L4 — Memory & knowledge base.

Recall memory lives behind the `MemoryBackend` protocol. Current backend:
`JsonlBackend` (transitional) → `SqliteBackend`. `open_backend` is the single
entry point consumers use to get the active backend for a vault.
"""

from __future__ import annotations

from pathlib import Path

from personal_llm.memory.backend import MemoryBackend
from personal_llm.memory.jsonl import JsonlBackend

__all__ = ["JsonlBackend", "MemoryBackend", "open_backend"]


def open_backend(vault_path: Path) -> MemoryBackend:
    """Return the memory backend for a vault. The single swap point for L4."""
    return JsonlBackend(vault_path)
