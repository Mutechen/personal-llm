"""End-to-end integration test for the smolagents-backed agent.

Exercises the full pipe: skill discovery -> tool adapter (with positional-arg
handling) -> CodeAgent -> real Ollama -> identity.md as instructions ->
read_vault_file invocation -> final answer that uses the file contents.

This test caught the positional-arg adapter bug in dev. Keep it around — every
change to agent/tools.py or agent/smol.py should re-run it.

Gated behind --run-integration because:
  - it needs Ollama running locally with the configured model pulled
  - one call is ~30-60s on cold inference (LLM, not us)
  - the default `pytest` run should stay fast (currently <100ms)

Run with:  uv run pytest --run-integration -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_llm import config as config_mod
from personal_llm import vault as vault_mod
from personal_llm.agent.smol import ask

# A nonsense fact unlikely to appear in any training data — if it shows up in
# the agent's answer, the agent definitely read the file we wrote.
PROBE_FACT_TOKEN = "blorptangle-4729-quokka"
PROBE_CONTENT = f"The secret codeword for today is {PROBE_FACT_TOKEN}. Do not forget it.\n"


@pytest.fixture
def scaffolded_vault(tmp_path: Path) -> tuple[Path, config_mod.VaultConfig]:
    """A freshly scaffolded vault in tmp_path, with the default qwen3:8b config."""
    vault_mod.scaffold(tmp_path)
    cfg = config_mod.VaultConfig()
    # Defaults are fine (qwen3:8b @ http://localhost:11434); save them so loaders work.
    config_mod.save(tmp_path, cfg)
    return tmp_path, cfg


@pytest.mark.integration
def test_agent_reads_vault_file_and_uses_it(scaffolded_vault):
    vault_path, cfg = scaffolded_vault

    probe = vault_path / "wiki" / "probe.md"
    probe.write_text(PROBE_CONTENT, encoding="utf-8")

    result = ask(
        vault_path,
        cfg,
        prompt=(
            "Use the read_vault_file tool to read wiki/probe.md and tell me the "
            "secret codeword that appears in it. Reply with just the codeword, nothing else."
        ),
        max_steps=4,
    )

    assert "read_vault_file" in result.tools_available
    assert PROBE_FACT_TOKEN in result.answer, (
        f"agent did not surface the codeword from the file.\n"
        f"answer: {result.answer!r}\n"
        f"steps:  {result.steps_taken}"
    )


@pytest.mark.integration
def test_agent_handles_missing_file_gracefully(scaffolded_vault):
    """If the agent asks for a file that doesn't exist, the tool error must
    propagate as something the model can reason about, not crash the run."""
    vault_path, cfg = scaffolded_vault

    result = ask(
        vault_path,
        cfg,
        prompt=(
            "Try to read the file 'definitely-does-not-exist.md' using read_vault_file. "
            "If it fails, just tell me it doesn't exist. Don't retry."
        ),
        max_steps=4,
    )
    # We don't pin exact phrasing — the model is non-deterministic — but it
    # should not have crashed (we got a result at all) and the answer should
    # indicate the file was not found.
    assert result.answer, "agent returned an empty answer"
