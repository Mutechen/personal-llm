# personal-llm

A personal LLM that grows with you. Open-source seed for your own personal AI.

**Status:** Phase 1 in progress — skill library + agent loop landed on `phase1/skills-registry`. Phase 0 ("newborn") commands all work on `main`.

## What this is

`personal-llm` is two products from one codebase:

1. **The seed** — a clean, Apache-2.0 codebase you clone, configure, and grow into *your* personal LLM. Zero personal data inside.
2. **The instance** — one user's actual personal LLM, living in a *vault directory* the package reads from. Identity, knowledge, skills, LoRA adapters — all in the vault, not in this repo.

The same `personal-llm` binary runs both; the difference is which vault you point it at.

The vision: a local-first AI that starts small (small base model, no domain knowledge beyond what's in the base) and grows in capability over time through accumulating memory, a self-maintained wiki, a Voyager-style skill library, and periodic LoRA fine-tunes. Every night while you sleep, it ingests new material, reorganizes what it knows, refactors its own skills, and (optionally) runs self-directed learning sessions on topics you care about.

## Quick start

```bash
git clone https://github.com/<your-fork>/personal-llm.git
cd personal-llm
uv sync                              # install package + deps
personal-llm init                    # creates a vault at ~/.personal-llm/vault/
personal-llm chat                    # interactive REPL — smolagents agent + skill library
personal-llm ask "what's 2 + 2?"     # one-shot agent run (can call skills)
personal-llm skills list             # show discovered SKILL.md skills
personal-llm sleep                   # run the sleep-time loop once (heartbeat in Phase 0)
```

For the install/init/configure walkthrough, see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

---

## The big picture

Three orthogonal distinctions hold the whole design together. Almost every architectural choice in this repo is a point in this cube:

- **Seed vs. instance** — is this code, or is this *your* data? The git repo is the seed (no personal bytes, ever). The vault is the instance (identity, memory, skills, adapters).
- **Wake vs. sleep** — does it happen while you're typing, or while you're not? Wake-time is fast and cheap (chat, answer questions). Sleep-time is where the agent actually grows (consolidate memory, write wiki notes, refactor skills, train LoRA).
- **Local vs. external** — does it stay on your machine, or cross a network boundary? Default is local. External calls (cloud tutors, web search, peers) flow through a single permission/budget/audit gate.

Hold those three axes in your head and you can predict where any new feature should live.

---

## Architecture: the seven layers

```
L7  Identity & Interface       CLI · web (P2+) · voice (P3+) · identity.md
L6  Agent loop & orchestrator  smolagents + MCP client (P1+)
L5  Skill library              Agent Skills (SKILL.md) standard
L4  Memory & knowledge base    sqlite recall store · Karpathy-style markdown Wiki
L3  Personalization layer      LoRA stack · DPO · KL-clamped (P2+)
L2  Inference runtime          Ollama (local) · cloud tutor router (P1+)
L1  Base model ("genes")       Qwen 3 8B local · Hermes 36B (cloud)

Sleep-time meta-loop: ingest · consolidate · curate · learn · pre-compute
```

Top-down — easiest order to *understand*; the system boots bottom-up:

### L7 — Identity & Interface
`identity.md` in your vault is the system prompt; **the agent never writes it, only you do**. Phase 0/1 interface is the CLI (`init`, `chat`, `ask`, `sleep`, `ingest`, `status`, `skills list`). Web in Phase 2+, voice in Phase 3+. Default personas are mentor/companion — explicitly **never romantic** (Replika lesson).

### L6 — Agent loop & orchestrator
Phase 1 uses **smolagents `CodeAgent`** talking to Ollama through the OpenAI-compatible `/v1` endpoint. Smolagents handles the ReAct trajectory internally (think → tool → observe → think). `identity.md` is passed as `instructions`; the chat session keeps one agent alive and calls `agent.run(msg, reset=False)` so the trajectory carries within a session. External tools (search, calendar, code exec, anything) come through **MCP** — the agent is an MCP client, no bespoke wrappers.

### L5 — Skill library
What the agent can *do*. Each skill is a directory with a **`SKILL.md`** manifest (Anthropic's open Agent Skills standard — we don't roll our own). Three sources with strict precedence: **vault > builtin > imported**. The registry deliberately **does not** execute `tool.py` from vault or imported skills — only from builtins — until a sandbox lands for user-authored Python.

### L4 — Memory & knowledge base
Two formats:
- **Memory** (events, episodes, facts) — a **SQLite recall store** behind a swappable `MemoryBackend` protocol (`src/personal_llm/memory/`). Recent turns are recalled into the agent at session start; semantic/archival search via `sqlite-vss` is a later phase.
- **Knowledge** (durable, hand-editable) — a **Karpathy-style markdown wiki** in `vault/wiki/`. Plain markdown so Obsidian/Logseq/etc. just work. The agent writes daily/topic/project notes during sleep-time; you edit them by hand any time.

Vector store stays file-based (markdown grep + sqlite-vss) until >10k chunks. Qdrant only after.

### L3 — Personalization layer (Phase 2+)
A stack of **LoRA** adapters via HuggingFace PEFT, trained from your data during sleep-time, applied at inference. DPO for preference shaping, KL-clamped so the adapter can't drift the model into a different personality. **Shareability rule, locked**: any byte of training data from the user → `shareable: false` at training time, period.

### L2 — Inference runtime
Ollama on the host (Docker can't pass MPS through on Mac). Cloud tutor (Phase 1+) routes through a small "tutor router" with a **per-call** cost gate — not just per-day. The AutoGPT lesson is that runaway loops eat $20/minute, so daily caps are too coarse.

### L1 — Base model (the "genes")
- **Local**: `qwen3:8b` via Ollama. Fast, private, free, weak.
- **Cloud tutor (Phase 1)**: Hermes 4.3 36B on RunPod + Anthropic Claude. Strong, costs money, used sparingly.

"Genes" is the metaphor on purpose: base weights are immutable identity-at-birth. What makes *your* instance yours is layered on top.

---

## The two loops

### Wake-time (you talking to it)

```
your message
  → L7 chat REPL
  → L6 smolagents agent (instructions = identity.md)
      ↳ loops: think → maybe call a skill (L5) → observe → think
      ↳ skills may read memory (L4) or hit external MCP servers
  → L2 inference (Ollama local; tutor only if needed and permitted)
  → response back through L7
  → memory write: one JSONL line per turn in vault/data/interactions/
```

### Sleep-time (the growth engine)

Nightly (or on-demand via `personal-llm sleep`), the agent processes its own day:

```
read today's interactions + raw inbox
  → summarize into the wiki (daily/topic/project notes)
  → propose new skills (Voyager-style: pattern repeats → factor a skill)
  → run a small DPO/LoRA pass on preference signals (P2+)
  → call tutors for things it couldn't answer well (within budget, P1+)
  → write vault/growth/YYYY-MM-DD.md (the growth log)
```

Today the sleep runner is a **heartbeat stub** — it writes a markdown file saying "Nothing yet — Phase 0" with the day's turn counts. The contract is: *the growth log shows up every day*, even before real work fills it.

---

## External surfaces: lobes & tutors

How a closed local system avoids becoming a fishbowl.

### Lobes — the sharing format
A **lobe** is a `.lobe` archive containing a `lobe.yaml` manifest plus skills, knowledge, and/or LoRA adapters. The brain metaphor is on purpose. You can export part of your vault as a lobe, import someone else's into yours, verify with SHA-256. **Never** in a lobe: your identity, raw interaction logs, anything private, any LoRA trained on user-derived bytes. No central registry by design — distribution is GitHub releases, blogs, email.

### External learning — one permission model for all sources
- **Privacy classes** on every piece of context (public / shareable-with-tutor / private / never-leaves-device)
- **PII redaction** before anything goes to a tutor
- **Per-tutor scope** (this tutor sees only X topics)
- **Budget caps** — $0.50/day autonomous default, $100/month total, **per-call** cost gate too
- **Audit log** in `vault/data/audit/` for every external call
- **Autonomy modes** — manual / ask-first / autonomous-within-budget

Web search is **self-hosted SearXNG** as a Docker sidecar — no API keys, no rate limits, no third-party watching your queries.

---

## Deployment topology

personal-llm runs as a **hybrid** of native and containerized components — native for what you touch every minute (CLI, Ollama, sleep cron) and Docker for what needs isolation or service-shape (skill sandbox, SearXNG, Qdrant, MCP servers). A `docker-compose.yml` at the repo root is the optional one-command path for forkers who prefer compose. The vault is **always a bind-mount**, never a Docker volume — your data must remain a regular directory you can `ls`, back up, sync.

See [ARCHITECTURE.md §9](docs/ARCHITECTURE.md) for the full split.

---

## Glossary

Key terms used above, with pointers for going deeper.

**Agent loop / ReAct** — The "think → act → observe → think" trajectory an LLM agent runs to solve a task. We use smolagents' `CodeAgent` variant, which emits Python code blocks instead of JSON tool calls.

**Agent Skills (`SKILL.md`)** — Open standard from Anthropic for packaging a skill as a directory: a markdown manifest naming the skill, when to use it, what tools it exposes, optional `tool.py` for Python.

**Curated memory (MemGPT / Letta concept)** — The agent-memory idea of explicit tiers (core / recall / archival) with the model curating what it remembers. We adopt the *concept*; L4 itself is an own-built SQLite recall store — Letta the library turned out to be server-only (see [docs/PRIOR_ART.md](docs/PRIOR_ART.md)).

**DPO (Direct Preference Optimization)** — Training objective that adjusts a model toward preferred over rejected responses without RLHF's reward-model machinery. We use it during sleep-time on preference signals.

**KL-clamp / KL penalty** — A constraint during fine-tuning that prevents the adapter from drifting too far from the base model's distribution. Stops a personalization adapter from quietly becoming a different personality.

**LoRA (Low-Rank Adaptation)** — Tiny ranks of trainable weights bolted onto a frozen base model. Cheap to train (a few hundred MB), cheap to swap, additive. PEFT's adapter format is the de-facto standard.

**Karpathy LLM Wiki** — The pattern of giving an LLM a writable markdown directory as its long-term knowledge base. Plain files, hand-editable, no exotic database — works because LLMs are already good at navigating markdown.

**Lobe** — Our packaging format for sharing parts of a vault (skills, knowledge, optionally adapters) as a single `.lobe` archive. Verified by SHA-256, no central registry.

**MCP (Model Context Protocol)** — Open standard for exposing tools/data to LLM agents. The agent speaks one protocol; any MCP-compliant server plugs in for free.

**Ollama** — Local LLM runner (GGUF + llama.cpp underneath) that gives you an OpenAI-compatible HTTP server for whatever model you've pulled. Phase 0/1 inference goes through it.

**PEFT (`adapter_config.json`)** — HuggingFace's Parameter-Efficient Fine-Tuning library and its adapter format. We use it so adapters trained here load in any other PEFT-aware tool.

**SearXNG** — Self-hosted privacy-respecting meta-search engine. Our web-search backend in Phase 1+; runs as a Docker sidecar.

**Sleep-time compute** — Doing expensive work *between* user interactions (consolidating memory, regenerating summaries, fine-tuning) so the wake-time path stays fast and cheap. The principle our growth engine is built on.

**smolagents** — HuggingFace's small agent library with a `CodeAgent` that prefers code over JSON tool calls and a `LocalPythonExecutor` sandbox. Our L6.

**Vault** — The per-user directory (default `~/.personal-llm/vault/`) where identity, memory, wiki, skills, and adapters live. The seed/instance boundary is enforced by keeping this directory completely outside the git repo.

**Voyager** — The 2023 Minecraft agent that introduced curriculum + growing skill library + self-verification. Our L5 (skill library) and parts of the sleep-time loop trace directly to it.

---

## Further reading & watching

### Memory architecture (L4)
- **MemGPT / Letta** — the memory-tier concept (core / recall / archival). docs: [docs.letta.com](https://docs.letta.com). The library itself is server-only and not a dependency — see [docs/PRIOR_ART.md](docs/PRIOR_ART.md).
- **"Sleep-time Compute" paper** — [arXiv 2504.13171](https://arxiv.org/abs/2504.13171) — the principle the sleep-time loop leans on most.
- **Karpathy LLM Wiki gist** — [gist.github.com/karpathy/442a6bf555914893e9891c11519de94f](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — the markdown-first knowledge-base pattern.
- **mem0** — an embeddable memory-layer SDK; one of the alternatives considered. L4 ultimately uses an own-built SQLite store to stay dependency-light.
- *Watch:* [Sleep-Time Compute — Letta AI (Packer / Snell / Lin)](https://www.youtube.com/watch?v=1UTo511O3-U) — the canonical talk on the exact pattern this project's sleep-time loop is built around. Also [MemGPT: Teaching LLMs memory management for unbounded context](https://www.youtube.com/watch?v=oFJJkFQjcW0) for the memory-tier story end-to-end. For the systems-view of memory around an LLM, [Andrej Karpathy's channel](https://www.youtube.com/@AndrejKarpathy/videos) — the "Intro to LLMs" and Software 3.0 talks are the right starting points.

### Self-evolving agents / skill library (L5)
- **Voyager** (Wang et al., 2023) — [arxiv.org/abs/2305.16291](https://arxiv.org/abs/2305.16291). Canonical curriculum + skill-library + self-verification loop.
- **AutoSkill** (2026) — [arxiv.org/abs/2603.01145](https://arxiv.org/abs/2603.01145). Experience-driven lifelong skill self-evolution.
- **SAGE** (2025) — [arxiv.org/abs/2512.17102](https://arxiv.org/abs/2512.17102). RL for self-improving agent with a skill library.
- **Awesome-Self-Evolving-Agents** surveys — [github.com/EvoAgentX/Awesome-Self-Evolving-Agents](https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents) · [github.com/XMUDeepLIT/Awesome-Self-Evolving-Agents](https://github.com/XMUDeepLIT/Awesome-Self-Evolving-Agents).
- **Lifelong LLM agents** survey (IEEE TPAMI 2026) — [github.com/qianlima-lab/awesome-lifelong-llm-agent](https://github.com/qianlima-lab/awesome-lifelong-llm-agent).
- *Watch:* [Jim Fan — Voyager](https://www.youtube.com/watch?v=iHzX2WLv7Pc) — the original talk on the Minecraft skill library and curriculum.

### Agent loops & tool use (L6)
- **smolagents** — [github.com/huggingface/smolagents](https://github.com/huggingface/smolagents). Our agent runtime.
- **Model Context Protocol** — [modelcontextprotocol.io](https://modelcontextprotocol.io/). The plumbing for everything-as-a-tool.
- *Watch:* [Introduction to the Model Context Protocol — Anthropic](https://www.youtube.com/watch?v=2B7_Y-6KBSQ) and [The Model Context Protocol: Connecting AI to Everything — Adam Jones, Anthropic](https://www.youtube.com/watch?v=T4-BdZQUCSE). For smolagents, [SmolAgents: A Smol Library to Build Agents](https://www.youtube.com/watch?v=icRKf_Mvmt8) (HuggingFace).

### Skill format (L5)
- **Anthropic Agent Skills (`SKILL.md`)** — [agentskills.io](https://agentskills.io/). Cross-tool compatible with 30+ agent frameworks.

### Personalization (L3)
- **HuggingFace PEFT** — [huggingface.co/docs/peft](https://huggingface.co/docs/peft/). LoRA/QLoRA + adapter format.
- **Unsloth** — custom Triton kernels, ~2× faster QLoRA than Axolotl on a single GPU; 70B fits 24 GB. Our P2 training pick.
- **Axolotl** — alternative for multi-GPU.
- *Watch:* [Insights from Finetuning LLMs with Low-Rank Adaptation — Sebastian Raschka](https://www.youtube.com/watch?v=rgmJep4Sba4) and [Hacks to Make LLM Training Faster — Daniel Han, Unsloth](https://www.youtube.com/watch?v=PdtKkc5jB4g).

### Base models & runtime (L1–L2)
- **Ollama** — [ollama.com](https://ollama.com/). Local runner; what `personal-llm` talks to by default.
- **llama.cpp + GGUF Q4_K_M** — the format underneath. Sweet spot for local single-GPU serving.
- **Qwen** — chosen local base (Apache-2.0, strong multilingual).
- **Hermes 4 / Nous Research** — cloud-tutor candidate.

### Failure modes we design against
See [docs/PRIOR_ART.md](docs/PRIOR_ART.md) for full notes on AutoGPT-style loop blowups, Replika/Pi romance pivots, and the "premature vector DB" trap.

---

## Open standards adopted

- **[Anthropic Agent Skills (`SKILL.md`)](https://agentskills.io/)** — skill format.
- **[Model Context Protocol (MCP)](https://modelcontextprotocol.io/)** — external-tool plumbing.
- **[HuggingFace PEFT (`adapter_config.json`)](https://huggingface.co/docs/peft/)** — adapter format.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Contributing

The seed should stay small and clean. Two contribution paths:

1. **Into the seed (PR here)** — generic examples (identity templates, starter skills, vault-skeleton improvements) go to `examples/`.
2. **As a lobe (out-of-tree)** — anything domain-specific or user-curated ships as a `.lobe` archive (see [docs/ARCHITECTURE.md §6](docs/ARCHITECTURE.md)). Lobes are distributed however you choose; the personal-llm community has no central registry by design.

Your own personal vault stays private. The seed never holds personal data.
