# Research subset — learning-from-transcripts

Source material for [`../LEARNING_FROM_TRANSCRIPTS.md`](../LEARNING_FROM_TRANSCRIPTS.md).
Curated subset, not the full bibliography — see ARCHITECTURE.md §15 for the rest.

PDFs are gitignored by intent (binary, fetchable) — re-pull with the curl lines below if
missing. Read in the order listed.

## Read first — the map
- **`externalization-review.pdf`** — *Externalization in LLM Agents: A Unified Review of
  Memory, Skills, Protocols and Harness Engineering* (arXiv 2604.08224). Survey that situates
  everything below; skim to place memory + skills + protocols on one map.

## Read closely — direct templates
- **`trace2skill.pdf`** — *Trace2Skill: Distill Trajectory-Local Lessons into Transferable
  Agent Skills* (arXiv 2603.25158). Template for the Stage-2 **skill extractor**
  (trajectories → `SKILL.md` hierarchy, no manual curation).
- **`latent-preference-from-user-edits.pdf`** — *Aligning LLM Agents by Learning Latent
  Preference from User Edits* (arXiv 2404.15269, NeurIPS 2024). Framework **PRELUDE** /
  algorithm **CIPHER**: infer preferences from the user's *edits*, no fine-tuning. Basis for
  the Stage-2 **preference extractor** — note its no-fine-tune stance matches our
  "recall/insights first, LoRA later" phasing.
- **`expel-contextual-experience-replay.pdf`** — *Contextual Experience Replay* (arXiv
  2506.06698). Parameter-free self-improvement from accumulated experience; justifies
  distill-first-train-later.

## Code to clone (not vendored here — read upstream)
- **EvoSkill** — https://github.com/sentient-agi/EvoSkill — synthesizes reusable skills from
  *failed* coding-agent trajectories. Closest to our stack; read the trace-segmentation and
  skill-schema code.
- **SkillRL** — https://github.com/aiming-lab/SkillRL (paper arXiv 2602.08234) — hierarchical
  skill library: successes → strategic patterns, failures → concise lessons.

## Reference-only (not fetched — pull when building evaluation, not now)
- PersonaMem-v2 (arXiv 2512.06688), CUPID (arXiv 2508.01674), PersonalLLM (arXiv 2409.20296)
  — personalization benchmarks.
- On-policy Expert Corrections (arXiv 2512.14895) — matters at P2 (predict-the-expert).

## Re-fetch
```sh
cd docs/research
curl -fsSL -o externalization-review.pdf            https://arxiv.org/pdf/2604.08224
curl -fsSL -o trace2skill.pdf                       https://arxiv.org/pdf/2603.25158
curl -fsSL -o latent-preference-from-user-edits.pdf https://arxiv.org/pdf/2404.15269
curl -fsSL -o expel-contextual-experience-replay.pdf https://arxiv.org/pdf/2506.06698
```
