"""Tests for the search_library builtin skill (the agent's RAG tool)."""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_llm import config as config_mod
from personal_llm.agent.tools import build_smolagents_tools
from personal_llm.builtin_skills.search_library.tool import SearchLibraryError, run
from personal_llm.config import EmbeddingModelConfig, VaultConfig
from personal_llm.skills import discover


def test_search_library_is_discovered_and_wrapped(tmp_path: Path):
    skills = discover(None)  # builtins only
    assert "search_library" in {s.name for s in skills}

    tools = build_smolagents_tools(skills, vault_root=tmp_path)
    tool = next(t for t in tools if t.name == "search_library")
    # vault_root is curried away; the agent only sees query (+ optional k).
    assert "query" in tool.inputs
    assert "vault_root" not in tool.inputs


def test_empty_query_raises():
    with pytest.raises(SearchLibraryError):
        run(Path("/nonexistent-vault"), "   ")


def test_model_unavailable_returns_message(tmp_path: Path):
    config_mod.save(
        tmp_path,
        VaultConfig(embedding_model=EmbeddingModelConfig(endpoint="http://localhost:1")),
    )
    out = run(tmp_path, "anything")
    assert "unavailable" in out.lower()


@pytest.mark.integration
def test_run_returns_passages_end_to_end(tmp_path: Path):
    """Live path: ingest a doc, then the tool retrieves a relevant passage."""
    from personal_llm.documents.pipeline import ingest_document
    from personal_llm.memory import open_backend

    config_mod.save(tmp_path, VaultConfig())
    doc = tmp_path / "note.txt"
    doc.write_text(
        "Risotto is made by toasting arborio rice then adding warm stock slowly.\n\n"
        "The planet Mars has a thin carbon dioxide atmosphere and red iron-oxide dust.",
        encoding="utf-8",
    )
    ingest_document(open_backend(tmp_path), config_mod.load(tmp_path), doc)

    out = run(tmp_path, "how do you cook creamy rice?")
    assert "note" in out  # cited the document title
    assert "risotto" in out.lower()
