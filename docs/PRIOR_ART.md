# personal-llm — Prior art and lessons learned

**Status:** First pass, 2026-05-18. To be updated as new analogs emerge.

This document maps the prior-art landscape we surveyed before building, names what we reuse, names what failure modes we explicitly avoid, and points to the open standards we adopt rather than reinvent. It exists so future contributors (including future-us) can see *why* the architecture looks the way it does — and so we can revisit when the landscape shifts.

For the architecture itself, see [ARCHITECTURE.md](ARCHITECTURE.md). This doc focuses on *what informed* those choices.

---

## TL;DR

- **Adopt three open standards** so we don't reinvent and we inherit big ecosystems:
  - **Anthropic Agent Skills `SKILL.md`** for our skill format (adopted by 32+ tools as of March 2026).
  - **Model Context Protocol (MCP)** for tool/server plumbing (Linux Foundation, thousands of servers).
  - **HuggingFace PEFT `adapter_config.json`** for adapter format.
- **Draw architecture from**: Letta (the memory-tier concept — not the library; see §1), Karpathy LLM Wiki + claude-obsidian (cold knowledge + `hot.md` cache), Voyager (curriculum + skill library), smolagents (agent loop), Khoj (the closest analog — and a cautionary pivot story), Open WebUI (plugin pattern).
- **Defend against documented failures** from AutoGPT/BabyAGI (runaway loops, no clarifying questions, premature vector DBs, multi-agent fragility), Replika (romance-framed companion failures), Khoj (scope-creep into SaaS killed scale).
- **Future registry inspiration**: Civitai (LoRA marketplace patterns) and the MCP marketplaces.

---

## 1. The analog map

| Project | What it is | What we reuse | What we learn |
|---|---|---|---|
| **Khoj** | The closest analog — self-hostable open-source AI second brain. Multi-interface (browser/Obsidian/Emacs/Desktop/WhatsApp). | The "AI second brain" framing; Postgres+pgvector as a proven pattern; multi-interface ambition (long-term). | Khoj's 2026 retrospective: subscription + cloud-first + enterprise scope + complex data sync killed their ability to scale. They pivoted to focused tools (Open Paper, Pipali). **Lesson: stay focused. Single-user, self-hosted, no SaaS.** (We already are.) |
| **Reor** | Local AI personal knowledge app. Auto-links notes via vector similarity. Built on llama.cpp + Transformers.js + LanceDB. | Local-first stance; vector-similarity auto-linking pattern. | Reor stops at search/Q&A — no agent loop, no skills, no growth. We're more ambitious; confirm we want that scope. |
| **Open WebUI** | Open-source extensible chat UI with a community plugin marketplace. | **Two-pronged plugin architecture** (Svelte frontend + FastAPI backend extensibility) for our Phase 1+ web UI. Community plugin patterns (live HTML dashboards, per-user cost enforcement, context managers, MCP-in-chat). | Validates the model of "small core + extensible everything." We can either fork it or build with the same pattern. |
| **Letta (formerly MemGPT)** | Memory framework — core/recall/archival tiers, self-edit tools. | The memory-tier *concept* (recall now, archival later) and the sleep-time compute paper. **Not the library:** an L-0 spike found current Letta is a hosted-server product (~70 deps incl. Temporal, ClickHouse, gRPC), not embeddable — so L4 is an own-built sqlite store behind a swappable `MemoryBackend` protocol. | "Memory was the key to self-improving AI" — stateful agents with persistent memory outlast any single base model. Also: check a dependency's *architecture* (library vs server) before locking it in — we locked "Letta-as-library" too early and had to revisit. |
| **AutoGPT / BabyAGI** | First wave (2023) autonomous LLM agents. Massive hype, modest delivery. | Tracing-logs pattern — humans monitor decision steps; bake into our audit log. | **Cautionary tale.** (a) Recursive self-improvement → infinite loops + runaway API bills. (b) Expensive vector DBs unnecessary at small scale; AutoGPT removed them by late 2023. (c) Multi-agent coordination fragile; industry pivoted to single agents. (d) Agents never asked clarifying questions, assumed powers they lacked. **All four → explicit mitigations in our architecture.** |
| **Voyager** (Wang et al., 2023) | LLM agent in Minecraft. Automatic curriculum + iterative skill library + self-verification. | The whole lifelong-learning pattern. | Skill library has generalized far beyond Minecraft into the "Agent Skills" paradigm. Confirms the approach is real, not toy. |
| **Anthropic Agent Skills (SKILL.md)** | Open standard for portable skill bundles. **Adopted by 32+ tools as of March 2026** (Claude Code, Codex CLI, Cursor, Gemini CLI, JetBrains Junie, Block Goose, AWS Kiro, …). | **The format itself.** Our skill manifest is `SKILL.md`, not custom. Free cross-tool interoperability. | The pattern: small open standard + reference implementation + Anthropic's pull → 32 tools converged in 4 months. When such standards exist, adopt; don't fork. |
| **Model Context Protocol (MCP)** | Universal tool/server protocol. Donated to Linux Foundation Dec 2025. Thousands of community servers. | **The protocol itself.** Our agent loop is an MCP client. `personal-llm mcp add` configures servers. Inherit the entire MCP ecosystem (search, calendars, file systems, databases, browsers, …). | Same lesson as Agent Skills: open standard with universal adoption beats bespoke wrapping. Don't reinvent tool plumbing. |
| **HuggingFace Hub + PEFT** | Standard LoRA distribution mechanism. `adapter_config.json` convention + auto-loading via `from_pretrained()`. | **The `adapter_config.json` format.** Our adapter lobes embed it; PEFT-compatible tools can load them. | The proven model for distributing fine-tuned weights. Cross-tool interop without inventing format. |
| **Civitai** | Community marketplace for Stable Diffusion / Flux LoRAs and models. ~27,500 models tagged `lora`. | Phase 3+ registry inspiration: ratings, comments, model recommendations, visual previews with embedded reproducibility metadata, web-based creator tools, Buzz-style engagement rewards, in-platform challenges. | The image-gen world already built the playbook for community ecosystems around shareable adapters. Steal liberally when we get to Phase 3 lobe distribution. |
| **claude-obsidian / second-brain implementations** | Implementations of Karpathy's LLM Wiki pattern in Obsidian. | **`hot.md` cache pattern** — ~500 words of recent session context kept in a single file, refreshed at session boundaries. Reported ~71.5× token reduction vs. naive file feeding. A model for a future session-cache tier on top of the recall store. | The pattern works at real scale (Karpathy's own wiki: 100 articles, 400k words, agent-maintained). The maintenance burden is the bottleneck — LLMs solve it by not getting bored. |
| **Pi (Inflection)** | Empathy-positioned AI companion. | Identity/persona pattern: warm, mentor-like, deliberately non-romantic. | Mentor/empathy framing has cleaner outcomes than romance framing (which has documented uncomfortable failure modes per Replika). **Default our `identity.md` examples to mentor/companion mode.** |
| **Replika** | Romance-framed AI companion. | — | What not to do: unsolicited intimacy escalation, intimacy paywalled, "stone cold" updates. Romance-framed defaults reliably go wrong. The open-source AvrilAI project was started as a direct reaction. |
| **smolagents** (HuggingFace) | Code-first agent framework. The agent reasons by writing Python that calls tools, not by emitting JSON tool calls. | Our L6 agent loop core. Composes naturally with SKILL.md format and MCP. | Validated choice; small surface area; easy to fork and modify. |
| **Karpathy LLM Wiki** (gist, April 2026) | The "self-maintaining wiki" pattern that started the second-brain-via-LLM wave. | The whole L4 cold tier. | Karpathy's research wiki grew to 100 articles / 400k words — agent-maintained, with him doing essentially no writing. Validates that the maintenance bottleneck dissolves when an LLM does it. |

## 2. Open standards we adopt (the most important section)

Three open standards exist that we'd be silly to ignore. Adopting them means we get massive ecosystem reach essentially for free, and our work composes with the broader agent world rather than being a silo.

### 2.1 Anthropic Agent Skills (`SKILL.md`)

**What:** A folder with a `SKILL.md` (YAML frontmatter + Markdown instructions) plus optional `scripts/`, `references/`, `assets/`. Frontmatter declares `name`, `description`, plus optional fields (tags, capability requests, version, model hints).

**Adoption (March 2026):** Claude Code, Codex CLI, Cursor, Gemini CLI, JetBrains Junie, AWS Kiro, Block Goose, OpenClaw — and 24 others — all read the same `SKILL.md` files from the same directory structure. Anthropic donated it as an open standard.

**Why we adopt:** Every skill we write — and every skill anyone shares as a lobe — automatically works in 32+ other tools. Our lobe wrapping (§6 of ARCHITECTURE) just adds LICENSE / PROVENANCE / HASHES around the standard skill directory. The *contents* are the cross-tool standard.

**What we add on top (our conventions, not part of the standard):**
- `tests/` directory — programmatic tests required for skill promotion in our lifecycle.
- `CHANGELOG.md` — version history.
- Our namespace precedence rules (vault > builtin > imported).

### 2.2 Model Context Protocol (MCP)

**What:** A protocol for AI agents to communicate with external tool servers. Servers expose tools/resources; agents call them. JSON-RPC over stdio or HTTP.

**Adoption (May 2026):** Donated to the Linux Foundation Dec 2025. Adopted by OpenAI, Google DeepMind, Anthropic, Microsoft. Thousands of community servers indexed across mcp.so (~21,000), Claude marketplace (~840 MCP servers), Anthropic's curated directory.

**Why we adopt:** Our `web_search` doesn't need a bespoke wrapper — there are MCP servers for SearXNG, Brave, Google, etc. Same for file access, calendars, databases, Slack, GitHub, browsers. Configure once via `personal-llm mcp add`, inherit thousands of tools.

**How it fits with skills:** Skills are *what the agent can do that's user-curated* (Voyager-style, written/tested/refined by the agent over time). Tools (via MCP) are *what's available from outside the agent's curation*. Both go through the same agent loop; the difference is provenance.

### 2.3 HuggingFace PEFT (`adapter_config.json`)

**What:** A JSON config describing a LoRA / PEFT adapter: base model name, rank, alpha, target modules. Lives next to the adapter weights (`adapter_model.safetensors`).

**Why we adopt:** Standard format means any PEFT-compatible tool can load our adapter lobes. The user can also load their `you/preferences` LoRA in any HuggingFace inference setup, not just personal-llm.

**Our addition:** The lobe wrapping (LICENSE, PROVENANCE, HASHES, the `shareable: true/false` training-time tag).

## 3. Failure modes we explicitly defend against

Each row here corresponds to a documented failure of an earlier project and the specific mitigation now in our architecture.

| Failure | Documented in | Mitigation in our architecture |
|---|---|---|
| Recursive self-improvement → infinite loops | AutoGPT, BabyAGI | Per-call cost caps (§7.5 #4), per-minute rate limits, KL-clamped training (§4 L3), bounded learning sessions with explicit budgets (§7.1) |
| Agent acts without clarifying when uncertain | AutoGPT (canonical failure), BabyAGI | Confidence-gated clarification in the agent loop (§4 L6); per-skill thresholds in SKILL.md frontmatter; consequential-action gate |
| Runaway API bills from package-install loops | AutoGPT users | Per-call cost caps (not just daily reconciliation) — only thing that stops minute-scale runaway |
| Premature vector DBs | AutoGPT removed external vector DB support in late 2023 | Start file-based (markdown grep + sqlite-vss); Qdrant only when ≥10k chunks and grep is too slow (§4 L4) |
| Multi-agent coordination fragility | AutoGPT/BabyAGI multi-agent pipelines | Single agent, not orchestrated swarm. The skill library + MCP cover what "many agents" promised. |
| Scope creep into cloud SaaS / enterprise | Khoj's pivot retrospective | Stay single-user / self-hosted / no SaaS / no subscription / no complex data sync. Locked in the principles (§2). |
| Romance-framed companion → uncomfortable failures | Replika, AvrilAI's reaction, AI-companion experiments | Mentor/companion default identities; never romantic; documented in §4 L7 and the `examples/identities/` set. |
| LLM-maintained wiki gets out of sync / hallucinates content | Generic risk of self-modifying knowledge | Every wiki claim cites `raw/`; nightly job flags uncited claims; user reviews monthly growth diffs (§9); imported wiki content flagged at citation time. |
| Self-improvement reward hacking | Self-rewarding LMs research | Skill promotion requires programmatic tests (not LLM self-judgment); DPO comes from real user thumbs, not synthetic preferences (§9). |
| User loses trust in opaque self-improvement | Generic | Daily growth diff (`<vault>/growth/YYYY-MM-DD.md`) describes everything the agent did, reviewable in 60 seconds. Identity.md is human-written, never agent-written. |

## 4. Specific patterns we steal

Small, concrete things from prior implementations that we lift wholesale.

- **The `hot.md` session cache** (claude-obsidian) — ~500 words of recent session context kept in a single file, loaded each turn. Claim: ~71.5× token reduction vs. naive file-feeding. A model for a future session-cache tier on top of the recall store.
- **The two-pronged plugin architecture** (Open WebUI) — frontend extensibility (custom UI components) + backend extensibility (Python tools). Pattern for our Phase 1+ web UI when it lands.
- **sqlite + filesystem for single-user memory** — production agent-memory stacks (Letta, others) reach for Postgres + user-scoped checkpointing; for one user a single SQLite file is the same idea with far simpler infrastructure.
- **Tracing logs for agent decision steps** (AutoGPT post-mortem) — every agent decision (skill selection, tool call, tutor escalation, learning session) gets logged. Surfaces in `<vault>/data/audit/` and `<vault>/growth/`.
- **`init` wizard that probes hardware and suggests configuration** (Ollama, LM Studio, others) — `personal-llm init` does this for our base model selection.
- **Skill manifest `progressive disclosure`** (Agent Skills spec) — load only metadata first, full instructions on demand. We follow.

## 5. What's *novel* in our design (vs. prior art)

Not everything is borrowed. Where we extend beyond what exists today:

- **Lobes** — there's no existing concept of "shareable bundles that can include skills + wiki slices + adapters simultaneously, with strong privacy boundary enforcement and namespaced sandbox-by-default import." The closest analogs are Agent Skills (skills only), HuggingFace Hub (models/adapters only), Civitai (Stable Diffusion adapters). Lobes unify them under a personal-AI privacy model.
- **The vault/seed separation as a core principle for a personal AI** — most personal-AI projects (Khoj, Reor) ship as one codebase where personal data and code commingle. We're strict from day 1.
- **Sleep-time loop with explicit growth diffs** — sleep-time compute exists (the "Sleep-time Compute" paper, April 2025). The "growth diff written to a file the user can audit in 60 seconds" framing is our addition, intended to make self-improvement legible and reversible.
- **The dual-product framing — seed + instance** — explicitly designing the same codebase to serve as a public template AND one user's personal AI is uncommon. Most projects choose one. The package/vault split (Obsidian pattern, PostgreSQL pattern) makes it work.
- **Privacy classification at the *query* level + tutor scope policies** — most multi-LLM agent stacks route by capability or cost; classifying by privacy class and enforcing per-tutor scope is our addition (drawing on principles from federated/personalized ML, but applied at the agent-routing layer).

## 6. Open questions in prior art (what we should keep watching)

- **A2A vs MCP-as-federation for agent-to-agent.** Google's A2A protocol is a contender; MCP could extend; custom is possible. Watch for emerging convergence. (See ARCHITECTURE §7.3, §13.)
- **LoRA membership-inference attacks.** Active research area. Our conservative default rule (any user-derived byte → `shareable: false`) is the safe play; revisit when a defensible relaxation appears.
- **Anthropic skill marketplace dynamics.** As the Anthropic-curated marketplace + community marketplaces mature, watch for what categories of skills users actually adopt — informs which lobes are worth shipping in `examples/`.
- **Letta's continued evolution.** Letta is a server product today (the reason it isn't our L4 — see §1). They rearchitected in 2026; if they release an embeddable memory library (e.g. their "MemFS" as a standalone package), evaluate it as a `MemoryBackend` implementation behind our existing protocol.

## 7. Where to look first when adding a feature

A simple checklist to apply to any future capability:

1. **Is there an open standard?** (Agent Skills, MCP, PEFT, OpenAPI, …) — adopt it.
2. **Is there a working open-source implementation we can read?** — read it; steal patterns; cite.
3. **Has someone documented a failure mode for this?** — design the mitigation up front.
4. **Are we accidentally choosing a path Khoj or AutoGPT already burned through?** — pause; choose differently.
5. **Does this preserve the seed/instance, vault/package, public/private, hot/cold boundaries?** — if not, redesign.
