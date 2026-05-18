"""Phase 0 sleep-time runner.

The growth-from-day-1 promise: even a do-nothing nightly loop writes a growth
log so the user can *see* that the agent is alive and tracking. Phase 1 fills
this with real work (ingestion, wiki updates, learning sessions, etc.).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from personal_llm.memory.simple import turn_counts_for_today


def run_once(vault_path: Path) -> Path:
    """Run a single sleep-time cycle. Returns the growth log path written."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    growth_path = vault_path / "growth" / f"{today}.md"
    growth_path.parent.mkdir(parents=True, exist_ok=True)

    counts = turn_counts_for_today(vault_path)
    body = _render(today, counts)
    growth_path.write_text(body, encoding="utf-8")
    return growth_path


def _render(today: str, counts: dict[str, int]) -> str:
    return f"""# Growth log — {today}

*Phase 0 — placeholder. The sleep-time loop only counts interactions right now;
Phase 1 adds real work (ingestion, wiki updates, skill curation, learning sessions).*

## Today

- Chat sessions: **{counts['sessions']}**
- Conversation turns: **{counts['turns']}**

## What I did

Nothing yet — Phase 0. The growth log is the contract: when there's actual
nightly work, it shows up here. Until then, this file is just a heartbeat.

## What I plan to do tomorrow

(Phase 1+ will write to this section.)
"""
