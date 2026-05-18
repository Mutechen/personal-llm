"""Minimal Phase 0 agent loop: identity + recent turns + user message → stream response.

This is the placeholder that smolagents replaces in Phase 1 once we add tools,
MCP, and the skill library. The interface (`chat_turn`) is kept small so the
upgrade is local.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from personal_llm.config import VaultConfig
from personal_llm.identity import load as load_identity
from personal_llm.inference.local import LocalModelClient
from personal_llm.memory import simple as memory

DEFAULT_CONTEXT_TURNS = 20


class ChatAgent:
    """Phase 0 chat agent. Stateless except for the vault."""

    def __init__(self, vault_path: Path, config: VaultConfig) -> None:
        self.vault_path = vault_path
        self.config = config
        self.client = LocalModelClient(
            model_name=config.local_model.name,
            endpoint=config.local_model.endpoint,
        )
        self.session_id = memory.new_session_id()

    def health(self) -> tuple[bool, str]:
        return self.client.health()

    def chat_turn(self, user_message: str) -> Iterator[str]:
        """Run one turn: persist the user message, stream the assistant reply,
        and persist that too. Yields response chunks for incremental display.
        """
        memory.append_turn(self.vault_path, self.session_id, "user", user_message)

        messages = self._build_messages(user_message)
        assistant_parts: list[str] = []
        for chunk in self.client.chat_stream(messages):
            assistant_parts.append(chunk)
            yield chunk

        memory.append_turn(
            self.vault_path, self.session_id, "assistant", "".join(assistant_parts)
        )

    def _build_messages(self, user_message: str) -> list[dict[str, str]]:
        system = load_identity(self.vault_path)
        history = memory.recent_turns(self.vault_path, limit=DEFAULT_CONTEXT_TURNS)
        # Exclude the just-appended user message to avoid duplication.
        history_minus_current = [
            h for h in history if not (h["role"] == "user" and h["content"] == user_message)
        ]
        return [
            {"role": "system", "content": system},
            *history_minus_current,
            {"role": "user", "content": user_message},
        ]
