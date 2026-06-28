"""Tests for LocalModelClient health checks (no live Ollama needed)."""

from __future__ import annotations

import types

import ollama
import pytest

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


def _embed_client(stub) -> LocalModelClient:
    client = LocalModelClient("bge-m3")
    client._client = stub
    return client


def test_embed_bisects_around_flaky_item():
    """A batch that 500s because one item NaN-fails is bisected; the culprit is
    retried alone (where it succeeds), and order is preserved."""

    class _Flaky:
        def embed(self, model, input):
            if len(input) > 1 and "poison" in input:
                raise ollama.ResponseError("unsupported value: NaN", 500)
            return {"embeddings": [[float(len(t))] for t in input]}

    vecs = _embed_client(_Flaky()).embed(["a", "poison", "bb"])
    assert vecs == [[1.0], [6.0], [2.0]]  # len('poison') == 6, order intact


def test_embed_raises_if_single_item_never_succeeds():
    class _AlwaysFails:
        def embed(self, model, input):
            raise ollama.ResponseError("unsupported value: NaN", 500)

    with pytest.raises(ollama.ResponseError):
        _embed_client(_AlwaysFails()).embed(["x"])


def test_embed_empty_is_noop():
    class _Boom:
        def embed(self, model, input):
            raise AssertionError("should not be called for empty input")

    assert _embed_client(_Boom()).embed([]) == []
