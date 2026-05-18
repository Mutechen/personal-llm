"""Identity loader.

The vault's identity.md is read at the start of each chat session and used
as the agent's system prompt. The user owns this file; the agent never writes
to it. (See docs/ARCHITECTURE.md §4 L7.)
"""

from __future__ import annotations

from pathlib import Path

from personal_llm.vault import IDENTITY_FILENAME


def load(vault_path: Path) -> str:
    """Return the identity.md contents as a string for the system prompt."""
    path = vault_path / IDENTITY_FILENAME
    if not path.is_file():
        return _fallback_identity()
    return path.read_text(encoding="utf-8").strip()


def _fallback_identity() -> str:
    """Used when a vault has no identity.md (shouldn't happen after init)."""
    return (
        "You are a personal AI assistant. Be helpful, concise, and honest. "
        "Ask clarifying questions when you're uncertain rather than guessing. "
        "The user has not yet configured an identity; suggest they edit "
        "their vault's identity.md to make this their own."
    )
