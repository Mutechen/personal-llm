# CLAUDE.md

Instructions for Claude when working in this repo. Read this first; then the docs.

## What this project is

`personal-llm` is two products from one codebase:

1. **The seed** — a clean, Apache-2.0 codebase users clone, configure, and grow into *their* personal LLM. Zero personal data inside this repo.
2. **The instance** — one user's actual personal LLM, living in a *vault directory* the package reads from at runtime (default: `~/.personal-llm/vault/`). Identity, knowledge, skills, LoRA adapters — all in the vault, not in this repo.

The vision: a local-first AI that starts small and grows in capability through accumulating memory, a self-maintained markdown wiki, a Voyager-style skill library, periodic LoRA fine-tunes, and a nightly sleep-time loop that does the actual growing.

## Where to look first

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — the canonical design (15 sections, ~10k words). If a question is "what should we build / why is it like this," start here.
- **[docs/PRIOR_ART.md](docs/PRIOR_ART.md)** — analog map (Khoj, Letta, Voyager, AutoGPT failures…), which open standards we adopt, which failure modes we defend against.
- **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)** — onboarding for forkers, including Docker setup and the exFAT/non-Unix-filesystem troubleshooting.
- **[README.md](README.md)** — short intro + quick start.

## Current status — Phase 0 ("newborn") scaffolded

Phase 0 ships: `personal-llm init` (wizard with hardware probe), `personal-llm chat` (streaming chat against local Ollama, identity loaded, cross-session recall via JSONL stub), `personal-llm sleep` (heartbeat growth log), `personal-llm ingest` (copies file to vault `raw/`, no parsing yet), `personal-llm status` (vault validation + inference health).

**Phase 0 deliberately stubs** several layers — they ship for real in Phase 1:
- **Memory** uses a thin JSONL log (`src/personal_llm/memory/simple.py`), not Letta. The interface is small so the swap is one module.
- **Agent loop** is a minimal identity + recent-turns + user-message composer (`src/personal_llm/agent/loop.py`). No tools, no MCP, no skill library yet. smolagents lands in Phase 1.
- **Skills** — directory layout exists in the vault skeleton, but no `SKILL.md` registry, no sandbox wiring, no example built-in skills.
- **External learning** — no tutors, no web search, no audit log. Everything stays local.
- **Lobes** — namespace directories exist (`<vault>/{skills,wiki,data/adapters}/imported/`), but no `export`/`import`/`inspect` commands.

Phase 1 plan is in [ARCHITECTURE.md §11](docs/ARCHITECTURE.md).

## The seven architectural layers (cheat sheet)

```
L7  Identity & Interface       identity.md · CLI · web (P1+) · voice (P2+)
L6  Agent loop & orchestrator  smolagents + MCP client (P1+)
L5  Skill library              SKILL.md (Anthropic Agent Skills standard)
L4  Memory & knowledge base    Letta (P1+) · Karpathy Wiki in Obsidian
L3  Personalization layer      LoRA stack · DPO · KL-clamped (P2+)
L2  Inference runtime          Ollama (local) · cloud tutor router (P1+)
L1  Base model ("genes")       Qwen 3 8B local · Hermes 36B cloud
```

## Locked decisions — do not relitigate without reason

(Full set in [ARCHITECTURE.md §6, §7, §14](docs/ARCHITECTURE.md); summarized here for fast lookup.)

| | |
|---|---|
| **License** | Apache-2.0 |
| **Package name** | `personal-llm` (CLI: `personal-llm`) |
| **Local base model** | `qwen3:8b` (Ollama tag). Fall-back ladder in `cli.py:_suggest_model()`. |
| **Cloud tutor (Phase 1)** | Anthropic Claude + self-hosted Hermes 4.3 36B on RunPod |
| **Pack/share name** | **lobes** (`.lobe` file extension, `lobe.yaml` manifest). Not "packs" or "modules." |
| **Skill format** | **`SKILL.md`** — Anthropic Agent Skills open standard. Not our own custom manifest. |
| **External tool protocol** | **MCP** (Model Context Protocol). Agent is an MCP client; no bespoke tool wrappers. |
| **Adapter format** | HuggingFace PEFT `adapter_config.json`. Cross-tool loadable. |
| **Vector store** | File-based (markdown grep + sqlite-vss) until >10k chunks. Qdrant only after. |
| **Search backend** | Self-hosted SearXNG (Docker sidecar in Phase 1). |
| **Default autonomous learning budget** | $0.50/day. Configurable. |
| **Lobe verification (v1)** | Hash-only (SHA-256). Signing scheme is Phase 3+. |
| **Lobe registry** | None in v1. Distribution via author's GitHub releases / blogs / email. |
| **LoRA shareability rule** | Conservative — *any* user-derived byte → `shareable: false`. |
| **Identity defaults** | Mentor/companion. **Never romantic.** (Replika/Pi lesson.) |
| **Deployment** | Hybrid native+Docker. CLI/Ollama native; skill sandbox + sidecars in Docker. Vault is always a bind mount. |
| **Mac users** | Run Ollama native (Docker can't pass MPS through). |
| **Cloud budget cap** | Default $100/mo total. Per-call cost gate (not just daily). Per-minute rate limit. |

## Coding conventions

- **Python 3.11+**, `uv` for env management.
- **Type hints** on public functions. `from __future__ import annotations` at the top of new modules.
- **Minimal comments.** Only write a comment when the *why* is non-obvious — a hidden constraint, a workaround, a deliberately surprising choice. Never comment to describe what well-named code already says.
- **No emojis** in code, comments, or docs unless the user explicitly asks.
- **Keep modules small.** When something gets bigger than ~200 lines, ask whether it should be split.
- **Don't add error handling for impossible scenarios.** Trust internal code. Validate at boundaries (CLI input, external APIs, vault files the user might have hand-edited).
- **`SKILL.md` for skills** — both ours and user-authored. Not custom manifests.
- **Print user-facing text via `rich.console.Console`**, not bare `print()` — consistent formatting and easy theming.

## The hard rules — do not violate

1. **The seed contains no personal data.** Never commit anything user-specific. The vault is *always* separate.
2. **The agent never writes `identity.md`.** Only the user does.
3. **Cost caps enforced per-call**, not just per-day. The AutoGPT lesson — runaway loops eat $20/minute.
4. **Imported lobes never override user-authored content.** Namespace precedence in §4 L5.
5. **Adapter `shareable` tag set at training time**, not at export time. Bytes from user data → `shareable: false`, period.
6. **Mac users get a special path** — Ollama always native, never Docker.

## Repo layout

```
personal-llm/
├── CLAUDE.md                # this file
├── LICENSE                  # Apache-2.0
├── README.md                # public-facing intro
├── pyproject.toml           # uv-managed
├── docker-compose.yml       # Phase 1+ sidecars (mostly commented for now)
├── docker/
│   ├── README.md
│   └── sandbox/Dockerfile   # skill sandbox base image
├── docs/
│   ├── ARCHITECTURE.md      # the canonical design
│   ├── GETTING_STARTED.md   # onboarding
│   └── PRIOR_ART.md         # what we learned from earlier projects
├── src/
│   └── personal_llm/
│       ├── cli.py           # Typer app — init, chat, sleep, ingest, status, version
│       ├── config.py        # VaultConfig (pydantic)
│       ├── vault.py         # vault discovery + scaffolding
│       ├── identity.py      # identity.md loader
│       ├── inference/       # L2
│       ├── memory/          # L4 — Phase 0: simple.py JSONL stub
│       ├── agent/           # L6 — Phase 0: minimal loop, smolagents lands P1
│       ├── interface/       # L7 — Phase 0: CLI chat REPL
│       ├── sleep/           # sleep-time runner
│       └── builtin_skills/  # empty Phase 0; SKILL.md skills land P1
├── examples/
│   ├── identities/          # three starter personas (mentor-mode)
│   └── vault-skeleton/      # what `personal-llm init` copies to scaffold a vault
└── tests/                   # empty Phase 0; first smoke test lands P1
```

## Common commands

```bash
# This repo lives on an exFAT external drive (Samsung T5), so always set:
export UV_PROJECT_ENVIRONMENT=~/.venvs/personal-llm

uv sync                                  # install / refresh deps
uv run personal-llm --help               # CLI help
uv run personal-llm init                 # scaffold a vault
uv run personal-llm chat                 # open chat REPL
uv run personal-llm sleep                # run sleep-time once (writes growth log)
uv run personal-llm status               # vault + inference health check

# Run lints / format (when ruff/pytest land)
uv run ruff check src/
uv run pytest                            # currently no tests; lands Phase 1
```

## When you're proposing the next feature

The checklist before designing anything (from [PRIOR_ART.md §7](docs/PRIOR_ART.md)):

1. Is there an open standard? (Agent Skills, MCP, PEFT, OpenAPI…) → adopt it.
2. Is there a working open-source implementation we can read? → read it; steal patterns.
3. Has someone documented a failure mode for this? (AutoGPT, Khoj pivot, Replika…) → design the mitigation up front.
4. Does this preserve the seed/instance, vault/package, public/private, hot/cold boundaries? → if not, redesign.
5. Will this scale Phase 0 (single user, ~10 GB free RAM, 6 GB VRAM)? → keep it small.

## Tone for user-facing text

The project user is collaborating with you on a deeply personal project they care about. Be:

- **Direct.** They asked for trial-and-error; cut the throat-clearing.
- **Honest about uncertainty.** If you haven't tested code, say so. If a model name is a guess, say so.
- **Concise.** End-of-turn summaries are one or two sentences max.
- **Mentor-mode.** When the user is about to take a turn that conflicts with the design (e.g., adding a hardcoded LoRA name to the seed), say so before doing it.

## What you should never do without asking

- Push to remote or run any `git push`.
- Add a feature that wasn't asked for (no "while I'm here" refactors).
- Reach into `~/.personal-llm/vault/` (that's the user's data; even reading it should be deliberate).
- Spend cloud money (no `runpod` API calls, no Anthropic/OpenAI/etc. API calls without explicit user sign-off).
- Delete `__pycache__/`, `uv.lock`, or `.venv` "to clean things up" — those are runtime state, owned by uv.
