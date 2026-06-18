# Learning from agent transcripts — the cold-start growth source

> Design proposal, not yet built. Status: draft (2026-06-18).
> Slots into [ARCHITECTURE.md](ARCHITECTURE.md) §5 (sleep loop), §7.5 (permission model),
> and layers L3/L4/L5. Read those first.

## 1. The problem this solves

The project's growth engine assumes a stream of interactions to learn from. But the
binding constraint is: **nobody converses with an immature personal LLM.** Like a baby,
it has nothing to say yet, so it gets no conversation, so it can't grow from conversation —
a cold-start deadlock. Two escape routes exist:

- **(A) Self-exploration** — let it experiment, trial-and-error, Voyager-style.
- **(B) Observation** — let it watch the user's *existing* conversations with capable
  agents (Claude Code, Claude, etc.) and learn from those.

We choose **B as the bootstrap, A as a later, grounded follow-on.** Reasoning:

- Voyager-style self-exploration works because Minecraft is a *grounded environment with an
  automatic reward signal*. A personal assistant has no such environment. Open-ended
  exploration toward no goal and no reward is exactly the AutoGPT failure mode we guard
  against (see PRIOR_ART.md): runaway loops, no convergence, budget burned on nothing.
- Self-talk also carries **zero personalization signal**. The product is *your* LLM; it
  cannot learn you by talking to itself.
- The user already generates a corpus that is simultaneously **abundant** (growing daily),
  **personal** (their real projects and decisions), and **competent** (an expert agent is
  doing the work). That is the ideal apprenticeship data. The baby learns by overhearing
  competent adults, then by scaffolded participation, and only later by independent play —
  in that order.

This is **imitation / apprenticeship learning**, and the 2025–2026 literature converges on
the same shape (see §7).

## 2. The one trap that shapes what we harvest

If the personal LLM merely imitates Claude, it becomes a *worse Claude* — an 8B local model
cannot clone a frontier model's capability and should not try. **Capability stays delegated**
(cloud tutor / the expert agent; our L1/L2). What we harvest is the **personal layer (L3)**:
preferences, recurring tasks, domain vocabulary, the decisions the user actually makes.

So the distillation target is *not* "how to reason like the expert." It is:

1. **Memory / facts** about the user and their projects → L4 recall + the wiki.
2. **Candidate skills** — recurring task patterns crystallized into `SKILL.md` → L5.
3. **Preference signal** — the user's corrections and choices → L3 (DPO/LoRA, later).

## 3. Data source

Claude Code stores session transcripts as JSONL under
`~/.claude/projects/<project-slug>/*.jsonl` — one event per line (user turns, assistant
turns, tool calls, tool results). This is a concrete, local, append-only, growing corpus.
Other agents (Claude desktop/web exports, etc.) can be added as adapters behind the same
ingestion seam.

**This is the user's most sensitive data.** It is strictly *instance/vault* — never the
seed, never committed, never read without the user's deliberate opt-in. The ingestion path
is the only component allowed to touch it, gated by §5.

## 4. The pipeline

A nightly sleep-time job (new step inside ARCHITECTURE.md §5), three stages:

```
  transcript source ──▶ [1 ingest] ──▶ [2 distill] ──▶ [3 write]
   (~/.claude/...)        normalize       local LLM       L4 / wiki / L5 / DPO set
                          + privacy        over a day's
                          gate             trajectories
```

### Stage 1 — Ingest & normalize
- Adapter per source reads new events since the last run (watermark in `data/`).
- Normalize to a neutral trajectory record: `{session, ts, role, text, tool, tool_args,
  tool_result_summary}`. Tool results are *summarized*, not stored raw — the literature is
  unanimous that raw traces are noisy and redundant (§7).
- **Privacy gate runs here, at the boundary**, reusing §7.5: classify per session/segment
  (`private` / `personal` / `public`); PII redaction before anything is sent to a *cloud*
  tutor for distillation. Default distiller is the **local** model, so most distillation
  never leaves the machine at all.

### Stage 2 — Distill (local model over a day's trajectories)
Three extractors, each a prompt + a schema'd output:

- **Facts** → memory candidates: durable statements about the user, their projects,
  decisions, constraints. ("ZeenaStoreZ launch gates Mutechen revenue." "Prefers fixing
  pre-existing lint in-scope.")
- **Skills** → from *recurring* multi-step patterns that succeeded: a draft `SKILL.md`
  (name, description, steps). Mirrors Trace2Skill / SkillRL (§7). Learn from **failures
  too** — a failed-then-corrected pattern becomes a "lesson" note (EvoSkill's insight).
- **Preferences** → from the user's *edits and corrections* of the agent: implicit
  signals, the strongest personalization source per the latent-preference-from-edits work
  (§7). Appended to the DPO dataset (already in §5 step 7), not applied immediately.

### Stage 3 — Write
- Facts → L4 recall store (and promoted to wiki pages with `[[wikilinks]]`).
- Skills → **proposals**, not auto-installed. Written to a review queue; a draft `SKILL.md`
  lands in the `imported` namespace only after the user approves. Imported never overrides
  user-authored (hard rule #4).
- Preferences → the DPO dataset for the weekly KL-clamped LoRA (§5 step 8). No user-derived
  byte is ever marked `shareable` (locked rule #5).
- Everything is logged to the **growth diff** (§5 step 11) so the user *sees* it:
  "Observed 3 sessions; learned 5 facts, proposed 2 skills, banked 4 preference pairs."

## 5. Guardrails (all reuse existing mechanisms)

- **Opt-in, explicit.** A `learn from-transcripts` source is off by default; enabling it is a
  deliberate config act. The agent never reaches into `~/.claude/` on its own.
- **Privacy classes + PII redaction** from §7.5, applied at Stage 1.
- **Local-first distillation.** Default distiller is the local model; cloud distillation of a
  `personal` segment requires redaction + an in-budget per-call gate (§7.5 #4).
- **Audit log** (§7.5 #6): every transcript ingested and every cloud call recorded.
- **Skills are proposals.** Nothing self-installs; the user approves the review queue.
- **The agent never writes `identity.md`** (hard rule #2) — facts go to the wiki/recall, not
  identity.

## 6. The grounded form of "trial and error" (the A path, later)

Once a transcript corpus exists, the user's self-exploration instinct gets a *safe* home:
**predict-the-expert.** Replay a real past task; have the local model predict the next
action; diff against what the expert actually did. The gap is a reward signal grounded in
the user's real work — no Minecraft, no open-ended goal generation, no AutoGPT vacuum. This
is offline imitation with on-policy-style correction (§7), and it is the right precursor to
any sandboxed self-play. **Not** in the first cut.

## 7. Prior art (2025–2026) — what to read and steal

The "distill experience into reusable abstractions, don't hoard raw traces" thesis is now
the field consensus. Closest to what we want:

- **Trace2Skill** — distills trajectory-local lessons into transferable skills, recovering a
  hierarchy of `SKILL.md`-style docs automatically from trajectory evidence. Direct template
  for Stage 2's skill extractor. (arXiv 2603.25158)
- **EvoSkill** — open-source; synthesizes reusable skills from *failed* trajectories for
  coding agents. Readable code; informs the "learn from failures too" path.
  (github.com/sentient-agi/EvoSkill)
- **SkillRL** — hierarchical skill library via experience-based distillation: successes →
  strategic patterns, failures → concise lessons. (arXiv 2602.08234 · github aiming-lab/SkillRL)
- **ExpeL / AgentRR / Contextual Experience Replay** — parameter-free self-improvement from
  accumulated experience, *no gradient updates*. Validates our "recall + distill first, LoRA
  later" phasing. (arXiv 2506.06698 and refs)
- **Trajectory-Informed Memory Generation for Self-Improving Agents** — generating memory
  items from trajectories. (arXiv 2603.10600)
- **Aligning LLM Agents by Learning Latent Preference from User Edits** — preferences are
  revealed implicitly through the user's edits/corrections, not stated. Direct basis for
  Stage 2's preference extractor.
- **PersonaMem-v2 / CUPID / PersonalLLM (ICLR 2025)** — personalization from interaction
  history; benchmarks and the "implicit preference" framing. (arXiv 2512.06688 · 2508.01674 ·
  2409.20296)
- **Imitation Learning for Multi-turn LM Agents via On-policy Expert Corrections** —
  small-model-learns-from-larger-model demonstrations; the predict-the-expert basis.
  (arXiv 2512.14895)
- **Externalization in LLM Agents: A Unified Review** — survey tying memory + skills +
  protocols together; good orientation. (arXiv 2604.08224)

Takeaways folded into this design: (1) never store raw trajectories — distill; (2) mine both
successes and failures; (3) parameter-free (recall + insights) first, LoRA/DPO later;
(4) harvest preferences from edits, not statements.

## 8. Phasing

- **P1 (now-ish):** Stage 1 ingest of Claude Code JSONL + Stage 2 *facts* extractor (local
  model) + Stage 3 write to the recall store. Smallest end-to-end slice; reuses the existing
  sleep runner, agent, and memory backend. No cloud, no new heavy deps.
- **P1.5:** skills extractor → review-queue proposals.
- **P2:** preference extractor → DPO dataset; predict-the-expert evaluation harness.
- **P2+:** additional transcript adapters; sandboxed self-play.

## 9. Open questions

- Watermark/dedup across overlapping Claude Code sessions (compaction rewrites history).
- How aggressively to summarize tool results without losing the signal a skill needs.
- De-duping facts against what the wiki/recall already knows (idempotent re-runs).
- Whether the predict-the-expert reward is good enough to train on, or only to rank.
