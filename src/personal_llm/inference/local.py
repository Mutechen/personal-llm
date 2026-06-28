"""Local inference via Ollama.

Phase 0: thin wrapper around the official ollama Python client. Streams
responses for incremental display. No tool use, no routing — that's L6.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import ollama

# Retries for a single input that the embedding server rejects (see `embed`).
_EMBED_RETRIES = 3


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
        # Ollama lists a bare-name model under its `:latest` tag, so a config
        # value of `nomic-embed-text` must match a listed `nomic-embed-text:latest`.
        candidates = {self.model_name}
        if ":" not in self.model_name:
            candidates.add(f"{self.model_name}:latest")
        if names.isdisjoint(candidates):
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

    def embed(self, inputs: list[str]) -> list[list[float]]:
        """Return one embedding vector per input string.

        Tries the whole list in one call. Some embedding models (notably bge-m3
        on Ollama) intermittently emit a NaN for one item, which fails the entire
        batch with a 500. On that error we bisect to isolate the culprit and
        retry it alone — single items reliably succeed — so a flaky item can't
        sink a whole batch (or crash the nightly embed step).

        The model is whatever this client was constructed with, so callers point
        it at the embedding model, not the chat model.
        """
        if not inputs:
            return []
        try:
            resp = self._client.embed(model=self.model_name, input=inputs)
            return [list(v) for v in (resp.get("embeddings") or [])]
        except ollama.ResponseError:
            if len(inputs) > 1:
                mid = len(inputs) // 2
                return self.embed(inputs[:mid]) + self.embed(inputs[mid:])
            for _ in range(_EMBED_RETRIES):
                try:
                    resp = self._client.embed(model=self.model_name, input=inputs)
                    return [list(v) for v in (resp.get("embeddings") or [])]
                except ollama.ResponseError:
                    continue
            raise

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the full model response as one string (non-streaming).

        Used by batch jobs like fact distillation where there's no user waiting
        on incremental output.
        """
        resp = self._client.chat(model=self.model_name, messages=messages, stream=False)
        return resp.get("message", {}).get("content") or ""
