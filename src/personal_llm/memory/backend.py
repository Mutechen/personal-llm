"""The `MemoryBackend` protocol — the swap seam for L4 memory.

Exactly one production implementation lives behind this at a time (currently
`JsonlBackend`; `SqliteBackend` replaces it). The protocol is the contract that
keeps the memory layer pluggable without the project carrying two backends.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MemoryBackend(Protocol):
    """Recall-memory store for conversation turns.

    Implementations are constructed with the vault path and own their storage
    underneath it; all methods operate on that one vault.
    """

    def new_session_id(self) -> str:
        """Return a fresh, unique session identifier."""
        ...

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        """Persist one conversation turn."""
        ...

    def recent_turns(self, limit: int = 20) -> list[dict[str, str]]:
        """Return the most recent turns across all sessions, oldest first.

        Each turn is a dict with `role` and `content` keys.
        """
        ...

    def turn_counts_for_today(self) -> dict[str, int]:
        """Return `{'sessions': int, 'turns': int}` for turns logged today (UTC)."""
        ...
