# Your personal-llm vault

This directory is *your* personal LLM's brain.

The `personal-llm` package reads from this vault at runtime; it never writes to itself. Everything in here belongs to you.

## Layout

| Path | What it holds |
|---|---|
| `config.yaml` | Runtime config: model, budgets, redaction list, tutors |
| `identity.md` | Your agent's persona (you edit this; the agent reads it) |
| `raw/` | Source material you drop in (PDFs, EPUBs, notes, transcripts) |
| `wiki/` | The agent-maintained markdown wiki (Obsidian-compatible) |
| `wiki/daily/` | Daily summaries, one per day |
| `wiki/topics/` | Topic-organized notes |
| `wiki/projects/` | Project-scoped notes |
| `wiki/projects/learning/` | Active learning goals (the agent picks from here in sleep-time) |
| `wiki/imported/<author>/<lobe>/` | Knowledge imported from `.lobe` files (Phase 1+) |
| `skills/<name>/` | Your skill library (each skill is an `SKILL.md` folder) |
| `skills/imported/<author>/<lobe>/` | Skills from imported lobes |
| `data/letta/` | Letta state (Phase 1+); Phase 0 unused |
| `data/qdrant/` | Vector store (Phase 2+) |
| `data/adapters/` | LoRA adapters |
| `data/adapters/imported/` | Adapter lobes from others (opt-in to load) |
| `data/interactions/` | Per-session chat JSONL logs (Phase 0 recall memory) |
| `data/audit/` | Per-day audit logs of external calls (Phase 1+) |
| `data/tutor_logs/` | Cached tutor payloads, for distillation |
| `data/snapshots/` | Rollback snapshots |
| `growth/YYYY-MM-DD.md` | Daily growth log — what the agent did each night |

## Privacy

This whole directory is private to you. If you keep it in a git repo, that repo should be private. **The seed (`personal-llm` package) never contains personal data.**

Want to share something? Export it as a `.lobe` — a skill, a wiki slice, or a publicly-trained adapter. See `docs/ARCHITECTURE.md` §6 in the seed for the lobe format. Identity, raw sources, preference adapters, and runtime state can never be exported as lobes.

## Updating personal-llm

Pull updates on the package (in the `personal-llm` repo) with `git pull`. Your vault is untouched. The package version is recorded in `config.yaml.vault_version`; we run migrations when the layout changes.
