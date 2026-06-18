"""Local inference via Ollama.

Phase 0: thin wrapper around the official ollama Python client. Streams
responses for incremental display. No tool use, no routing — that's L6.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import ollama


@dataclass
class LocalModelClient:
    """Minimal client for an Ollama-hosted local model."""

    model_name: str
    endpoint: str = "http://localhost:11434"

    def __post_init__(self) -> None:
        self._client = ollama.Client(host=self.endpoint)

    def health(self) -> tuple[bool, str]:
        """Return (ok, message). Ok=True means we can reach Ollama AND the model is pulled."""
        try:
            tags = self._client.list()
        except Exception as e:
            return False, f"Cannot reach Ollama at {self.endpoint}: {e}"
        names = {m.get("name") or m.get("model") for m in (tags.get("models") or [])}
        if self.model_name not in names:
            return False, (
                f"Model {self.model_name!r} not found in Ollama. "
                f"Pull it with: ollama pull {self.model_name}"
            )
        return True, "ok"

    def chat_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Yield response chunks as they arrive from the model."""
        stream = self._client.chat(model=self.model_name, messages=messages, stream=True)
        for chunk in stream:
            piece = chunk.get("message", {}).get("content")
            if piece:
                yield piece

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the full model response as one string (non-streaming).

        Used by batch jobs like fact distillation where there's no user waiting
        on incremental output.
        """
        resp = self._client.chat(model=self.model_name, messages=messages, stream=False)
        return resp.get("message", {}).get("content") or ""
