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

## Current status — Phase 1 in progress (PR #1 + PR #2 merged to `main`)

Phase 0 commands still work: `init`, `chat`, `sleep`, `ingest`, `status`, `version`.

**Merged to `main`** (PR #1 — the skills-registry chunk):
- **L5 skill library**: `SKILL.md` discovery + parser + 3-source namespace precedence (`vault > builtin > imported`); `personal-llm skills list`. See `src/personal_llm/skills/`.
- **First invocable skill**: `read_vault_file` builtin with safety checks (vault escape, oversize, non-UTF-8). `src/personal_llm/builtin_skills/read_vault_file/`.
- **L6 agent loop**: smolagents `CodeAgent` backed by Ollama via the OpenAI-compatible `/v1` endpoint. `vault_root` is curried into tools invisibly; `identity.md` passes through as `instructions`. `src/personal_llm/agent/{tools,smol}.py`.
- **CLI**: `personal-llm ask "..."` (single-shot) and `personal-llm chat` (interactive) both route through the smolagents agent. Chat builds the agent once per session and calls `agent.run(msg, reset=False)` so the ReAct trajectory carries in-session continuity. Phase 0 `ChatAgent` is gone.

**Merged to `main`** (PR #2 — the L4 memory swap):
- **`MemoryBackend` protocol** (`src/personal_llm/memory/`) — the L4 swap seam; `open_backend()` is the single resolution point.
- **`SqliteBackend`** — recall memory on stdlib `sqlite3`, one `turns` table per vault at `data/memory.db`, no new dependency. The Phase 0 JSONL stub is gone.
- **Cross-session memory** — at chat startup, recent turns are recalled from the backend and folded into the agent's `instructions`. The regression from the chat-REPL swap is closed.
- **Letta dropped** — an L-0 spike found Letta is a server product (~70 deps incl. Temporal/ClickHouse/gRPC), not a library. This supersedes the "Letta-as-library" locked choice; L4 is now an own-built sqlite store.
- **Test infra**: 39 unit tests + 2 opt-in integration tests behind `--run-integration` (`tests/conftest.py`).

**Still stubbed — land in subsequent chunks:**
- **Archival / semantic memory** — recall-only for now; `sqlite-vss` + a local embedding model is a later chunk.
- **JSONL migration** — old `data/interactions/*.jsonl` history isn't imported into sqlite; an optional `memory migrate` command is deferred.
- **External learning** — no tutors, no web search, no MCP servers, no audit log. Everything stays local.
- **Lobes** — namespace directories exist, but no `export`/`import`/`inspect` commands.
- **User-authored Python in skills** — the registry deliberately does NOT load `tool.py` from vault skills (only from builtins), pending a sandbox story for user code. There's a test pinning this boundary; don't relax it without a deliberate design pass.
- **Runtime overrides** (`/private`, `/local`, `/no-search`, `/tutor=`) parse in the REPL but don't yet enforce — they wire up alongside the tutor router.

Phase 1 plan is in [ARCHITECTURE.md §11](docs/ARCHITECTURE.md).

## The seven architectural layers (cheat sheet)

```
L7  Identity & Interface       identity.md · CLI · web (P1+) · voice (P2+)
L6  Agent loop & orchestrator  smolagents + MCP client (P1+)
L5  Skill library              SKILL.md (Anthropic Agent Skills standard)
L4  Memory & knowledge base    sqlite recall store · Karpathy Wiki in Obsidian
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
| **Vector store** | File-based until >10k chunks, then a real index. First cut: brute-force cosine over float32 blobs in SQLite (`memory/vector.py`) — lighter than sqlite-vss, no C extension on exFAT. Upgrade ladder: brute-force -> sqlite-vec (maintained successor to sqlite-vss) -> Qdrant. |
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
│       ├── memory/          # L4 — MemoryBackend protocol + SqliteBackend (facts, embeddings, doc chunks) + vector.py
│       ├── documents/       # L4 — book/doc ingest: parsers (txt/md/pdf/epub) + chunking + pipeline (RAG) + wiki gen
│       ├── learning/        # transcript distill + fact grading (G1/G2) + dedup (G3) + fact embeddings
│       ├── skills/          # L5 — SKILL.md registry, namespace precedence (P1)
│       ├── agent/           # L6 — smol.py (build_agent + ask + chat_turn, semantic recall) + tools.py
│       ├── interface/       # L7 — CLI chat REPL (routes through agent/smol.py)
│       ├── sleep/           # sleep-time runner
│       └── builtin_skills/  # Phase 1: read_vault_file/ + search_library/ (RAG) — SKILL.md + tool.py
├── examples/
│   ├── identities/          # three starter personas (mentor-mode)
│   └── vault-skeleton/      # what `personal-llm init` copies to scaffold a vault
└── tests/                   # 29 unit + 2 integration (gated behind --run-integration)
```

## Common commands

```bash
# This repo lives on an exFAT external drive (Samsung T5), so always set:
export UV_PROJECT_ENVIRONMENT=~/.venvs/personal-llm

uv sync                                  # install / refresh deps
uv run personal-llm --help               # CLI help
uv run personal-llm init                 # scaffold a vault
uv run personal-llm chat                 # interactive REPL — smolagents agent + skill library
uv run personal-llm ask "..."            # single-shot agent invocation (same agent as chat)
uv run personal-llm skills list          # show discovered SKILL.md skills
uv run personal-llm recall "..."         # semantic search over curated facts
uv run personal-llm ingest FILE          # parse/chunk/embed a doc (.txt/.md/.pdf/.epub) into the library
uv run personal-llm books search "..."   # semantic search over ingested document chunks
uv run personal-llm wiki build           # summarize ingested docs into wiki/library/ pages
uv run personal-llm sleep                # run sleep-time once (writes growth log)
uv run personal-llm status               # vault + inference health check

# Lint and test
uv run ruff check src/ tests/
uv run pytest                            # 29 unit tests, <100ms, no external deps
uv run pytest --run-integration          # also runs the live-Ollama integration tests (slow)
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
