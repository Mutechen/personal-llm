# Getting started

A walk-through from a fresh clone to your first chat. Phase 0 — minimal but real.

## Two paths

personal-llm runs as a **hybrid** of native and containerized components (see [ARCHITECTURE.md §9](ARCHITECTURE.md)). You have two install paths:

- **Native install (default, recommended).** Best chat UX, full GPU acceleration on Linux *and* Apple Silicon, lowest RAM overhead. Sections 1–7 below.
- **Docker compose alternative.** Easier "one command" setup, uniform across forkers, but worse daily chat UX and no MPS GPU on Mac. See [Alternative: Docker compose](#alternative-docker-compose) at the end.

Either way the *skill sandbox* runs in Docker (Phase 1+), so Docker is a soft dependency even on the native path. Install it once and you're set.

## What you'll need

| | |
|---|---|
| Python | 3.11+ |
| `uv` | recommended (faster), or `pip` works |
| [Ollama](https://ollama.com) | for the local model |
| [Docker](https://docs.docker.com/get-docker/) | for the skill sandbox (Phase 1+) and optional sidecar services |
| Hardware | a GPU with ≥5 GB VRAM is comfortable; CPU-only works but is slow |
| Disk | ~10 GB free for the model weights |

If you're on Ubuntu/Debian:

```bash
# uv (one-line install)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Ollama
curl -fsSL https://ollama.com/install.sh | sh
```

## 1. Clone and install

```bash
git clone https://github.com/<your-fork>/personal-llm.git
cd personal-llm
uv sync
```

That installs the `personal-llm` CLI into a project-local venv. To use it without activating the venv, prefix commands with `uv run`:

```bash
uv run personal-llm --help
```

…or `source .venv/bin/activate` once and skip the prefix.

## 2. Initialize your vault

```bash
uv run personal-llm init
```

The init wizard will:

1. **Probe your hardware** (RAM, disk, GPU/VRAM) and suggest a base model that fits.
2. Ask where to put the vault (default: `~/.personal-llm/vault/`).
3. Ask which **starter identity** to use — *minimal*, *journaling-companion*, or *coding-buddy*. Pick any; you'll edit later.
4. Ask for your **PII redaction list** — display name, email, optional phone and address. These are redacted before any external call (Phase 1+).
5. Ask your **monthly cloud budget cap**.
6. **Scaffold the vault** with the directory structure and write `config.yaml`.

When it's done, your vault looks like this:

```
~/.personal-llm/vault/
├── config.yaml            # editable runtime config
├── identity.md            # YOUR identity — edit this to make it yours
├── raw/                   # drop source material here
├── wiki/                  # the agent-maintained wiki
├── skills/                # your skill library (will grow over time)
├── data/                  # runtime state — don't edit by hand
└── growth/                # daily growth logs
```

## 3. Pull the model

The init wizard suggested a model based on your hardware. Pull it with Ollama:

```bash
ollama pull qwen3:8b     # default for ~6 GB VRAM (~5 GB on disk)
# or whatever the wizard suggested
```

This downloads ~5 GB. First-time only.

## 4. Start chatting

```bash
uv run personal-llm chat
```

You should see a banner, then a `you:` prompt. Try:

```
you: hi — who are you?
```

The agent reads `identity.md` and responds. Type `/help` to see runtime commands, `/quit` to exit.

Each session is persisted as a JSONL file in `<vault>/data/interactions/`. The next session has access to the last 20 turns across all sessions, so the agent remembers you across runs.

### Try the tool-using agent (Phase 1, single-shot)

The chat REPL above is the Phase 0 path — bare model, no tools. Phase 1 ships a separate command, `personal-llm ask`, that runs a smolagents-backed agent which can invoke any discovered skill (see [§4 L5 of ARCHITECTURE.md](ARCHITECTURE.md)).

```bash
personal-llm ask "what's the capital of France?"
personal-llm skills list                 # see what skills are wired up
personal-llm ask "read identity.md and tell me one thing about me"
```

The chat REPL will switch to this agent path in the next chunk; for now the two surfaces are deliberately separate so the agent loop can stabilize before it replaces the bare-model REPL.

## 5. Customize your identity

This is the highest-leverage thing you can do.

```bash
$EDITOR ~/.personal-llm/vault/identity.md
```

Fill in the `Background` section — name, current projects, things to never bring up. Anything in this file is loaded into every chat turn's system prompt.

## 6. (Optional) Wire up the sleep-time loop

The sleep-time loop consolidates your vault each night: (opt-in) learn new facts from your agent transcripts, grade them, dedup, and write a growth log of what changed.

Run it manually:

```bash
uv run personal-llm sleep
cat ~/.personal-llm/vault/growth/$(date +%F).md
```

To have it **learn** (not just grade existing facts), enable it in your vault `config.yaml`:

```yaml
sleep:
  learn_from_transcripts: true   # opt-in: reads your ~/.claude transcripts locally
```

To run it automatically, install the shipped **systemd user timer** (portable, travels with the repo; `Persistent=true` so a run missed while the laptop was asleep fires on next wake):

```bash
# exFAT/uv installs: export UV_PROJECT_ENVIRONMENT first so it's baked into the unit
./deploy/install-sleep-timer.sh
systemctl --user list-timers personal-llm-sleep.timer
```

See [`deploy/README.md`](../deploy/README.md) for details, the run-once/log commands, uninstall, and a cron alternative.

## 7. Check status anytime

```bash
uv run personal-llm status
```

Shows vault location, model, budget, validation, and a live inference health check.

## What's here vs. what's NOT here yet

Read the architecture doc ([docs/ARCHITECTURE.md](ARCHITECTURE.md)) for the full picture. The big rocks:

**Landed (Phase 1, on branch `phase1/skills-registry`):**

- **Skill library v1** — `SKILL.md` discovery + parser + namespace precedence (`vault > builtin > imported`). `personal-llm skills list`.
- **First invocable skill** — `read_vault_file` (read a UTF-8 text file under your vault) with safety checks against vault-escape, oversize, and binary content.
- **Agent loop v1** — smolagents `CodeAgent` against your local Ollama via the OpenAI-compatible `/v1` endpoint. Exposed as `personal-llm ask "..."`.

**Still missing (next chunks):**

- **More skills than just `read_vault_file`.** Listing dir contents, writing wiki pages, searching the web (via MCP) — all upcoming.
- **MCP client.** The agent can't yet talk to MCP servers (Phase 1+).
- **Document library (RAG).** `personal-llm ingest <file>` parses `.txt/.md/.pdf/.epub`, chunks it, embeds each chunk locally, and stores it in the vault; search it with `personal-llm books search "<query>"` (and `books list`). Idempotent by content hash. Agent-authored **wiki pages** from `raw/` are still a later chunk; today ingest powers retrieval, not summarization.
- **Semantic memory (facts).** Curated facts are embedded with a local model (`nomic-embed-text`) and searchable by meaning: `personal-llm recall "<query>"`. The nightly loop keeps embeddings current. Still upcoming: meaning-based search over older *turns* (archival memory).
- **Tutors / cloud escalation.** Everything stays local. (Phase 1+.)
- **Fine-tuning.** No LoRAs trained yet. (Phase 2+.)
- **Lobes export/import.** Namespace directories exist, no commands yet. (Phase 1+.)

If you want to verify the foundation on your machine before going further, the chat REPL + `ask` together are enough to see the seed running end-to-end with both surfaces.

## When things go wrong

| Symptom | Try |
|---|---|
| `Cannot reach Ollama` | `ollama serve` in another terminal, or check the endpoint in `config.yaml` |
| `Model ... not found in Ollama` | `ollama pull <model>` |
| Agent forgets the previous session | Check `~/.personal-llm/vault/data/interactions/` exists and has `.jsonl` files |
| Wrong vault picked up | Pass `--vault <path>` to any command; or set `$PERSONAL_LLM_VAULT` |
| Slow first response | Ollama loads the model on first request; subsequent calls are fast |
| `uv sync` → `failed to symlink ... Operation not permitted` | The repo is on an exFAT / NTFS / FAT32 drive that doesn't support symlinks. See [Running from a non-Unix filesystem](#running-from-a-non-unix-filesystem-exfat-ntfs) below. |

### Running from a non-Unix filesystem (exFAT, NTFS)

If you cloned the repo onto an external drive formatted exFAT, NTFS, or FAT32 (common with portable SSDs that need to work on Windows too), Python tooling will hit limitations: no symbolic links, no Unix file permissions, no hard links. The fix is to keep the *source* where it is and put the *venv* (and other ephemeral state) on your host's normal Unix filesystem.

**Put the venv outside the external drive:**

```bash
# One-time: tell uv to use a venv outside the exFAT/NTFS drive
export UV_PROJECT_ENVIRONMENT=~/.venvs/personal-llm

# Persist for future shells
echo 'export UV_PROJECT_ENVIRONMENT=~/.venvs/personal-llm' >> ~/.bashrc

# Now sync — the venv lives at ~/.venvs/personal-llm, the source stays where you cloned it
uv sync
uv run personal-llm --help
```

**Other things to keep on a Unix filesystem, not the external drive:**

- **Your vault** (default: `~/.personal-llm/vault/`). The vault stores recall memory in SQLite and benefits from real Unix file locking and permissions. Keeping the default location avoids exFAT pain.
- **Ollama models** (default: `~/.ollama/models/`). Already on your home filesystem; no action needed.

**What's fine on exFAT/NTFS:**

- The source code itself (Python imports, Git, your editor).
- `raw/` source material in the vault, if you choose to put the vault on the external drive.
- Wiki markdown files.

**What breaks on exFAT/NTFS:**

- Python venvs (symlink to interpreter, executable file mode bits).
- SQLite write performance and locking (the recall-memory DB will be slower and may error under concurrent access).
- Anything that needs `chmod +x` or `ln -s`.
- Docker bind mounts may have permission issues (everything appears as the uid/gid set in the mount options).

## What to do next

- Use it for a week. See what feels right and what doesn't. The whole project's hypothesis is that the *growth curve* is the value — Phase 0 is just the seed.
- When you're ready, the Phase 1 milestone (in [ARCHITECTURE.md §11](ARCHITECTURE.md)) is: real ingestion + wiki + skill library v1 + first cloud tutor + lobe export/import.

## Alternative: Docker compose

For forkers who want one command instead of seven, the repo ships a `docker-compose.yml` at the root that brings up the sidecar services (and optionally the agent itself) in containers. **You still need Ollama running native** (especially on Apple Silicon — Docker can't access MPS).

### What compose runs

In Phase 0 the compose file is intentionally sparse — the sidecars come online as features land. See [ARCHITECTURE.md §9](ARCHITECTURE.md) for the full split. Roughly:

- **Phase 1**: SearXNG (search backend), the skill sandbox image.
- **Phase 2+**: Qdrant (vector store), optional all-in-one agent container with a web UI.

### Native + compose (the recommended hybrid)

Use compose for the sidecar services; run the agent native:

```bash
docker compose up -d searxng              # once it's uncommented in Phase 1
uv run personal-llm chat                  # chat stays native
```

Your vault stays at `~/.personal-llm/vault/` as a bind mount; compose services that need it read/write through that mount, never a Docker-managed volume.

### Full containerization (compose-first)

Once the optional `agent` service in `docker-compose.yml` is wired up (Phase 2+), you can run everything containerized:

```bash
docker compose up -d                      # all services
docker compose exec agent personal-llm chat
```

You give up some chat UX (`docker exec` is clunkier than a native terminal) in exchange for one-command setup uniformity.

### GPU passthrough

- **Linux + NVIDIA**: install [`nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) and the compose file sets `runtime: nvidia` on services that need it. Most users don't need this — Ollama runs native and uses the GPU directly.
- **Apple Silicon**: Docker cannot pass MPS through. **Run Ollama native on Mac.** Compose can still bring up SearXNG, Qdrant, and other sidecars.
- **CPU-only**: nothing to configure; everything works at CPU speed.

### Vault location with compose

If your vault lives somewhere other than the default, set `$PERSONAL_LLM_VAULT` before invoking compose so the bind mounts resolve correctly:

```bash
export PERSONAL_LLM_VAULT=/path/to/my/vault
docker compose up -d
```
