"""Tests for LocalModelClient health checks (no live Ollama needed)."""

from __future__ import annotations

import types

from personal_llm.inference.local import LocalModelClient


def _client_listing(model_name: str, listed: list[str]) -> LocalModelClient:
    client = LocalModelClient(model_name)
    client._client = types.SimpleNamespace(
        list=lambda: {"models": [{"name": n} for n in listed]}
    )
    return client


def test_health_accepts_bare_name_against_latest_tag():
    # Ollama lists a bare-name model as `name:latest`; the bare config must match.
    ok, msg = _client_listing("nomic-embed-text", ["nomic-embed-text:latest"]).health()
    assert ok, msg


def test_health_accepts_explicit_tag():
    ok, _ = _client_listing("qwen3:8b", ["qwen3:8b"]).health()
    assert ok


def test_health_reports_missing_model():
    ok, msg = _client_listing("missing-model", ["qwen3:8b"]).health()
    assert not ok
    assert "not found" in msg


def test_health_does_not_treat_tagged_name_as_latest():
    # An explicit tag must match exactly — not fall back to :latest.
    ok, _ = _client_listing("qwen3:8b", ["qwen3:latest"]).health()
    assert not ok
