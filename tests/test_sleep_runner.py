"""Tests for the sleep-time runner orchestration.

LLM grading is disabled so the cycle is deterministic and needs no Ollama; the
G2/G3 steps are covered by their own tests.
"""

from __future__ import annotations

from pathlib import Path

from personal_llm import config as config_mod
from personal_llm.config import SleepConfig, VaultConfig
from personal_llm.memory import open_backend
from personal_llm.sleep.runner import run_once


def _vault(tmp_path: Path, **sleep_kwargs) -> Path:
    config_mod.save(tmp_path, VaultConfig(sleep=SleepConfig(**sleep_kwargs)))
    return tmp_path


def test_sleep_runs_g1_and_writes_growth_log(tmp_path: Path):
    vault = _vault(tmp_path, llm_grading=False)
    backend = open_backend(vault)
    backend.append_fact("the user is working on the encyclopedia", "transcript:s1")
    backend.append_fact("the user prefers reversible operations", "transcript:s1")

    report = run_once(vault)

    assert report.g1 is not None
    assert report.g1.newly_graded == 2
    assert report.g2 is None  # llm disabled
    assert report.dedup is None
    assert report.learned_facts is None  # learning opt-in, off
    assert report.active_facts == 2
    assert report.growth_path is not None and report.growth_path.exists()


def test_growth_log_content(tmp_path: Path):
    vault = _vault(tmp_path, llm_grading=False)
    open_backend(vault).append_fact("the user runs Linux", "transcript:s1")

    report = run_once(vault)
    log = report.growth_path.read_text(encoding="utf-8")

    assert "# Growth log" in log
    assert "## Graded" in log
    assert "Active facts" in log
    assert "Transcript learning disabled" in log
    assert "Corroborated (cross-session)" in log


def test_growth_log_reports_corroboration(tmp_path: Path):
    vault = _vault(tmp_path, llm_grading=False)
    backend = open_backend(vault)
    backend.append_fact("the user runs Linux", "transcript:s1")
    backend.append_fact("the user runs Linux", "transcript:s2")  # corroborates

    report = run_once(vault)
    assert report.corroborated_facts == 1
    assert "Corroborated (cross-session): **1**" in report.growth_path.read_text(
        encoding="utf-8"
    )


def test_sleep_is_idempotent_on_facts(tmp_path: Path):
    vault = _vault(tmp_path, llm_grading=False)
    open_backend(vault).append_fact("the user is mid-migration to ext4", "transcript:s1")

    run_once(vault)
    second = run_once(vault)

    # already graded by the first run, nothing new the second time
    assert second.g1.newly_graded == 0


def test_default_config_keeps_learning_off(tmp_path: Path):
    """A vault with no sleep config must not auto-read transcripts."""
    config_mod.save(tmp_path, VaultConfig())
    report = run_once(_vault(tmp_path, llm_grading=False))
    assert report.learned_facts is None
