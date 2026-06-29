"""Sleep-time runner — the nightly growth loop.

Runs the consolidation pipeline over the vault and writes a human-readable
growth log so the user can *see* what changed while they were away:

1. (opt-in) learn new facts from agent transcripts,
2. grade them — G1 deterministic, then G2 LLM volatility (if the model is up),
3. dedup + supersede (G3, if the model is up),
4. record turn/fact counts.

Grading and dedup only touch facts already in the vault; learning is gated on
`config.sleep.learn_from_transcripts` so the loop never reaches into the user's
transcripts on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from personal_llm import config as config_mod
from personal_llm.documents.pipeline import IngestSummary, ingest_directory
from personal_llm.learning.dedup import DedupResult, dedup_facts
from personal_llm.learning.embeddings import embed_facts
from personal_llm.learning.grading import GradeResult, grade_facts
from personal_llm.learning.llm_grading import grade_facts_llm
from personal_llm.learning.runner import learn_from_transcripts
from personal_llm.memory import open_backend


@dataclass
class SleepReport:
    date: str
    growth_path: Path | None = None
    learning_enabled: bool = False
    learned_facts: int | None = None  # None when learning is disabled or skipped
    g1: GradeResult | None = None
    g2: GradeResult | None = None
    dedup: DedupResult | None = None
    model_skipped: bool = False
    active_facts: int = 0
    corroborated_facts: int = 0
    corroborated_new: int = 0  # promoted to `corroborated` this cycle
    facts_embedded: int = 0  # embeddings computed this cycle
    ingest: IngestSummary | None = None  # documents auto-ingested from raw/
    turn_counts: dict[str, int] | None = None


def _model_available(name: str, endpoint: str) -> bool:
    from personal_llm.inference.local import LocalModelClient

    ok, _ = LocalModelClient(name, endpoint).health()
    return ok


def run_once(vault_path: Path) -> SleepReport:
    """Run a single sleep-time cycle. Writes the growth log; returns the report."""
    config = config_mod.load(vault_path)
    backend = open_backend(vault_path)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    report = SleepReport(
        date=today, learning_enabled=config.sleep.learn_from_transcripts
    )

    # The local model is needed for learning and for the G2/G3 steps. Check once;
    # if it's down (a real possibility for a 3am cron), those steps skip and only
    # the deterministic G1 grade runs.
    wants_model = config.sleep.learn_from_transcripts or config.sleep.llm_grading
    model_up = (
        _model_available(config.local_model.name, config.local_model.endpoint)
        if wants_model
        else False
    )

    # Snapshot certainty before consolidation so the log can report this cycle's
    # promotions; corroboration accrues inside learn (re-assertion) and dedup (merge).
    corroborated_before = backend.count_corroborated()

    if config.sleep.learn_from_transcripts and model_up:
        source = (
            Path(config.sleep.transcript_source)
            if config.sleep.transcript_source
            else None
        )
        report.learned_facts = learn_from_transcripts(
            vault_path, config, source=source
        ).facts_added

    report.g1 = grade_facts(backend)

    if config.sleep.llm_grading and model_up:
        report.g2 = grade_facts_llm(backend, config)

    # Embeddings power both semantic recall and dedup clustering, so compute them
    # before dedup. Gated on the embedding model's own availability (a different
    # model than chat); dedup degrades to no-op clustering if it's unavailable.
    embed_up = config.sleep.llm_grading and _model_available(
        config.embedding_model.name, config.embedding_model.endpoint
    )
    if embed_up:
        report.facts_embedded = embed_facts(backend, config).facts_embedded
        # Auto-ingest anything the user dropped in raw/ (idempotent by content).
        report.ingest = ingest_directory(backend, config, vault_path / "raw")

    if config.sleep.llm_grading and model_up:
        report.dedup = dedup_facts(backend, config)

    if wants_model and not model_up:
        report.model_skipped = True

    report.turn_counts = backend.turn_counts_for_today()
    report.active_facts = len(backend.facts_for_grading())
    report.corroborated_facts = backend.count_corroborated()
    report.corroborated_new = max(0, report.corroborated_facts - corroborated_before)

    growth_path = vault_path / "growth" / f"{today}.md"
    growth_path.parent.mkdir(parents=True, exist_ok=True)
    growth_path.write_text(_render(report), encoding="utf-8")
    report.growth_path = growth_path
    return report


def _render(report: SleepReport) -> str:
    counts = report.turn_counts or {"sessions": 0, "turns": 0}
    lines = [f"# Growth log — {report.date}", ""]

    lines.append("## Learned")
    if not report.learning_enabled:
        lines.append("- Transcript learning disabled (`sleep.learn_from_transcripts`).")
    elif report.learned_facts is None:
        lines.append("- Transcript learning enabled but skipped — local model unreachable.")
    else:
        lines.append(f"- New facts from transcripts: **{report.learned_facts}**")

    lines += ["", "## Graded"]
    if report.g1:
        g1 = report.g1
        lines.append(
            f"- G1 (deterministic): {g1.newly_graded} newly graded, "
            f"{g1.expired_ephemeral} ephemeral expired, "
            f"{g1.expired_volatile_ttl} volatile expired (TTL)."
        )
    if report.g2:
        g2 = report.g2
        buckets = ", ".join(f"{k}={v}" for k, v in sorted(g2.by_volatility.items()))
        lines.append(f"- G2 (LLM): re-graded {g2.facts_seen} — {buckets or 'none'}.")
    if report.dedup:
        d = report.dedup
        lines.append(
            f"- G3 (dedup): {d.merged} merged, {d.superseded} superseded "
            f"across {d.clusters} cluster(s)."
        )
    if report.model_skipped:
        lines.append("- LLM grading/dedup skipped — local model unreachable.")

    if report.ingest is not None:
        ing = report.ingest
        lines += ["", "## Library (raw/)"]
        lines.append(
            f"- Ingested {ing.ingested} new doc(s) ({ing.chunks} chunks); "
            f"{ing.skipped} unchanged, {ing.empty} no-text, {ing.failed} failed."
        )

    lines += [
        "",
        "## State",
        f"- Active facts: **{report.active_facts}**",
        f"- Corroborated (cross-session): **{report.corroborated_facts}** "
        f"(+{report.corroborated_new} this cycle)",
        f"- Facts embedded this cycle: **{report.facts_embedded}**",
        f"- Chat sessions today: **{counts['sessions']}** · "
        f"turns: **{counts['turns']}**",
        "",
    ]
    return "\n".join(lines)
