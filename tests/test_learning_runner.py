"""End-to-end tests for the transcript -> facts -> recall pipeline.

The extractor is injected (a fake), so these run the real ingest, watermark,
and write paths without a live model.
"""

from __future__ import annotations

import json
from pathlib import Path

from personal_llm.config import VaultConfig
from personal_llm.learning.runner import STATE_RELPATH, learn_from_transcripts
from personal_llm.memory import open_backend


def _write_session(root: Path, sid: str, text: str) -> None:
    path = root / "proj" / f"{sid}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "type": "user",
        "sessionId": sid,
        "timestamp": "2026-06-18T10:00:00Z",
        "message": {"role": "user", "content": text},
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def _fixed_extractor(facts):
    return lambda _session_text: list(facts)


def test_pipeline_writes_facts_to_recall(tmp_path: Path):
    vault, source = tmp_path / "vault", tmp_path / "src"
    _write_session(source, "s1", "I build on an exFAT drive")

    result = learn_from_transcripts(
        vault,
        VaultConfig(),
        source=source,
        extractor=_fixed_extractor(["user builds on exFAT"]),
    )

    assert result.sessions_processed == 1
    assert result.facts_added == 1
    facts = open_backend(vault).recent_facts()
    assert facts[0]["text"] == "user builds on exFAT"
    assert facts[0]["source"] == "transcript:s1"


def test_watermark_skips_processed_sessions(tmp_path: Path):
    vault, source = tmp_path / "vault", tmp_path / "src"
    _write_session(source, "s1", "first")

    learn_from_transcripts(
        vault, VaultConfig(), source=source, extractor=_fixed_extractor(["f1"])
    )
    # second run, same session, different facts — should be skipped entirely
    second = learn_from_transcripts(
        vault, VaultConfig(), source=source, extractor=_fixed_extractor(["f2"])
    )

    assert second.sessions_seen == 1
    assert second.sessions_processed == 0
    assert [f["text"] for f in open_backend(vault).recent_facts()] == ["f1"]


def test_new_session_processed_after_watermark(tmp_path: Path):
    vault, source = tmp_path / "vault", tmp_path / "src"
    _write_session(source, "s1", "first")
    learn_from_transcripts(
        vault, VaultConfig(), source=source, extractor=_fixed_extractor(["f1"])
    )

    _write_session(source, "s2", "second")
    result = learn_from_transcripts(
        vault, VaultConfig(), source=source, extractor=_fixed_extractor(["f2"])
    )
    assert result.sessions_processed == 1
    assert {f["text"] for f in open_backend(vault).recent_facts()} == {"f1", "f2"}


def test_dry_run_writes_nothing_and_keeps_watermark_clean(tmp_path: Path):
    vault, source = tmp_path / "vault", tmp_path / "src"
    _write_session(source, "s1", "hello")

    result = learn_from_transcripts(
        vault,
        VaultConfig(),
        source=source,
        dry_run=True,
        extractor=_fixed_extractor(["a fact"]),
    )

    assert result.dry_run is True
    assert result.facts_extracted == 1
    assert result.facts_added == 0
    assert open_backend(vault).recent_facts() == []
    assert not (vault / STATE_RELPATH).exists()


def test_limit_caps_sessions_processed(tmp_path: Path):
    vault, source = tmp_path / "vault", tmp_path / "src"
    for i in range(3):
        _write_session(source, f"s{i}", f"msg {i}")

    result = learn_from_transcripts(
        vault,
        VaultConfig(),
        source=source,
        limit=2,
        extractor=_fixed_extractor(["f"]),
    )
    assert result.sessions_seen == 3
    assert result.sessions_processed == 2
