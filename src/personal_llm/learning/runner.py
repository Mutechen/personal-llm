"""Orchestrate the transcript -> facts -> recall pipeline.

A watermark of processed session ids (under `data/learning/`) makes re-runs
idempotent: only sessions never seen before are distilled. Combined with the
fact table's UNIQUE(text), running this twice is a no-op.

Privacy: the default distiller is the local model, so transcripts never leave
the machine. The pipeline is opt-in — nothing here runs unless the user invokes
`personal-llm learn`; the agent never reaches into the transcript source on its
own (docs/LEARNING_FROM_TRANSCRIPTS.md §5).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from personal_llm.config import VaultConfig
from personal_llm.learning.distill import extract_facts
from personal_llm.learning.transcripts import iter_sessions
from personal_llm.memory import open_backend

STATE_RELPATH = "data/learning/transcripts_state.json"
DEFAULT_SOURCE = Path.home() / ".claude" / "projects"

# Callable taking a rendered session and returning extracted facts. Injectable
# so tests can run the whole pipeline without a live model.
Extractor = Callable[[str], list[str]]


@dataclass
class LearnResult:
    sessions_seen: int
    sessions_processed: int
    facts_extracted: int
    facts_added: int
    dry_run: bool


def _load_processed(vault_path: Path) -> set[str]:
    path = vault_path / STATE_RELPATH
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return set(data.get("processed_session_ids", []))


def _save_processed(vault_path: Path, processed: set[str]) -> None:
    path = vault_path / STATE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"processed_session_ids": sorted(processed)}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _default_extractor(config: VaultConfig) -> Extractor:
    from personal_llm.inference.local import LocalModelClient

    client = LocalModelClient(config.local_model.name, config.local_model.endpoint)
    return lambda session_text: extract_facts(client, session_text)


def learn_from_transcripts(
    vault_path: Path,
    config: VaultConfig,
    source: Path | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    extractor: Extractor | None = None,
) -> LearnResult:
    """Distill facts from new transcript sessions into the recall store.

    `limit` caps how many *new* sessions to process this run. `dry_run` extracts
    and counts but writes nothing and does not advance the watermark.
    """
    source = source or DEFAULT_SOURCE
    extractor = extractor or _default_extractor(config)
    backend = open_backend(vault_path)
    processed = _load_processed(vault_path)

    seen = done = extracted = added = 0
    newly_done: set[str] = set()

    for session in iter_sessions(source):
        seen += 1
        if session.session_id in processed:
            continue
        if limit is not None and done >= limit:
            continue

        facts = extractor(session.render())
        extracted += len(facts)
        if not dry_run:
            source_tag = f"transcript:{session.session_id}"
            for fact in facts:
                if backend.append_fact(fact, source_tag):
                    added += 1
            newly_done.add(session.session_id)
        done += 1

    if not dry_run and newly_done:
        _save_processed(vault_path, processed | newly_done)

    return LearnResult(
        sessions_seen=seen,
        sessions_processed=done,
        facts_extracted=extracted,
        facts_added=added,
        dry_run=dry_run,
    )
