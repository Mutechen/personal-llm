# Fact grading & consolidation — turning a fact dump into curated memory

> Design proposal, not yet built. Status: draft (2026-06-18).
> The consolidation half of L4. Slots into [ARCHITECTURE.md](ARCHITECTURE.md) §4 L4
> (fact epistemics) and §5 step 3 (sleep-loop memory consolidation). Pairs with
> [LEARNING_FROM_TRANSCRIPTS.md](LEARNING_FROM_TRANSCRIPTS.md), which *produces* the facts
> this pass *grades*.

## 1. Why this exists

The P1 transcript pipeline wrote 440 facts to recall in one run — accurate, but raw. A
sample of what's in there shows the three problems a grading pass must solve:

- **Ephemeral noise.** *"The user's system is experiencing a load average of 22.36 and
  thermal_zone1 at 92°C."* A momentary sensor reading should never be a durable fact.
- **Stale-prone status.** *"Project X is at Phase 1," "uncommitted changes in PLAN.md,"
  "preparing to complete IE-167."* True today, false next week.
- **Near-duplicates.** The same preference stated five ways across five sessions
  (`UNIQUE(text)` only caught *exact* repeats).

All 440 are tagged `unverified` and nothing trusts them yet. Grading is what makes recall
*usable*: drop the noise, expire the stale, merge the dups, and surface the durable.

## 2. The three axes, operationalized

From ARCHITECTURE §4 L4 — kept orthogonal on purpose.

### Volatility (half-life) — the highest-value axis for this data
| bucket | changes over | TTL behavior | example |
|---|---|---|---|
| `static` | never | no expiry | "separates personal and work data" |
| `slow` | months | long TTL | "primary project is the Islamic Encyclopedia" |
| `volatile` | days–weeks | short TTL, then needs re-confirmation | "IE-167 Lane 1 ship gate in progress" |
| `ephemeral` | momentary | never stored / expire on grade | load average, temperature, "currently running X" |

TTL is measured from `valid_as_of` (when the fact was asserted, default = `created_at`).
A `volatile` fact past its TTL becomes `expired` — not deleted — and can **resurrect** to
`active` if re-asserted in a later transcript.

### Certainty (confidence) — what we can compute without ground truth
We can't verify truth locally, but we can measure **cross-session corroboration**:
- `corroborated` — the same fact (post-dedup) is asserted in ≥2 independent sessions.
- `unverified` — single-source conversational (the P1 default).
- `suspect` — contradicted by a newer fact, or internally inconsistent.

(Model misreads like *"prefers Opus 4.8 after switching from Claude-based models"* — Opus
*is* Claude — stay `unverified`; this is exactly the class corroboration won't rescue.)

### Provenance — already carried in `source`
Classified into `conversational` / `observed` / `inferred` now. Revelation
(Qur'an / tafsir) and scientific are first-class later: a revelation-provenance fact is
**`static` volatility + high certainty by rule** and **requires a citation** — set
deterministically, never by model guess. This is the Mutechen / Islamic-Encyclopedia hook.

## 3. Lifecycle (orthogonal bookkeeping)

`status`: `active` → `expired` (TTL passed) / `superseded` (replaced by a newer
contradicting fact) / `merged` (folded into a canonical fact during dedup).

**Never hard-delete.** Demotion is reversible — matching the user's own "reversible data
operations / undo manifests" preference (itself a fact we distilled). The user can review
and override any grade; the grade is a proposal, not a verdict.

## 4. The pass (a sleep-loop step)

1. **Select.** Ungraded `active` facts, plus `active` facts past their TTL (re-grade).
2. **Heuristic pre-filter** (deterministic, no LLM). Obvious ephemerals by pattern — load
   average, temperature, byte/line counts, "currently/now running", bare timestamps-as-state
   → mark `ephemeral`/`expired`. Cheap, and it clears the worst noise before any model call.
3. **Cluster** for dedup: group by lexical similarity / shared subject (cheap token overlap
   first; embeddings later, ties to the deferred `sqlite-vss` chunk).
4. **LLM grade** (local model, batched). One structured call per fact-or-cluster returns
   `{volatility, certainty_hint, canonical_text, subject, supersedes_id?}`.
5. **Apply.** Update axis columns; merge dups (one canonical row + source refs, bump
   corroboration); expire ephemerals; supersede contradicted; mark `graded_at`.
6. **Log** to the growth diff (§5 step 11): "graded 440 → 290 active (180 durable / 110
   volatile), 95 ephemeral expired, 55 merged." Makes the curation *visible*.

The pass is **idempotent**: `graded_at` is the watermark; a re-run only touches ungraded or
TTL-expired facts and converges.

## 5. Schema (additive, non-breaking `ALTER TABLE ADD COLUMN`)

On the existing `facts` table:

| column | meaning | first cut |
|---|---|---|
| `confidence` | certainty (exists) | already shipped |
| `volatility` | static/slow/volatile/ephemeral, NULL=ungraded | G1 |
| `status` | active/expired/superseded/merged, default `active` | G1 |
| `valid_as_of` | when asserted (TTL anchor), default `created_at` | G1 |
| `graded_at` | grading watermark | G2 |
| `canonical_id` | →the row this was merged into (NULL if canonical) | G3 |
| `corroboration` | distinct corroborating sources, default 1 | G4 |
| `subject` | clustering key | G3 |

Recall retrieval then filters `status='active'` and prefers `static`/`slow` +
higher-certainty + recent — so the agent's cross-session context is the curated set, not the
raw dump.

## 6. Phasing

- **G1 — deterministic, immediate win on the existing 440.** Add `volatility` / `status` /
  `valid_as_of`; heuristic ephemeral filter; TTL expiry for `volatile`. No LLM. Kills the
  sensor-reading class today.
- **G2 — LLM grading.** Batched local grading of volatility + certainty hint; `graded_at`.
- **G3 — semantic dedup + supersession.** Cluster, merge canonical, contradiction detection.
  Needs embeddings or LLM-judge over candidate pairs.
- **G4 — corroboration certainty + retrieval weighting.** Bump cross-session facts; recall
  prefers active/durable/certain.
- **Later — provenance rules.** Revelation/scientific provenance, citation enforcement, a
  `personal-llm facts review` CLI for user override.

## 7. Open questions

- TTL values per bucket — need tuning against observed decay (how long is "Phase 1" true?).
- Subject extraction for clustering — model-derived vs. heuristic noun-phrase.
- Merge aggressiveness — false-merge risk; conservative threshold + keep both on doubt.
- Resurrection rule — when does a re-asserted expired fact update `valid_as_of` vs. spawn new?
- Embedding model for semantic dedup — choice and the 6 GB VRAM budget (ties to sqlite-vss).
- Where grading runs — its own `personal-llm grade` command, or only inside `sleep`?
