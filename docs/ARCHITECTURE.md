# personal-llm — Architecture

**Status:** Draft v1 — 2026-05-18.
**Audience:** the project's single user, and anyone who forks the repo to build their own.

---

## 1. Vision

A personal, local-first LLM that is *one person's* assistant — not a multi-tenant SaaS. It starts small (think: a baby with language but no domain knowledge), and grows in capability over time through three compounding loops:

1. **Memory.** A self-maintained markdown wiki + structured agent memory accumulates what the user cares about, in a form both the agent and the human can browse.
2. **Skills.** The agent writes, tests, and curates its own executable tools (code, prompts, multi-step plans) in a versioned skill library.
3. **Weights.** Periodic LoRA fine-tunes on the user's interaction history and preferences — nightly DPO, monthly domain adapters — slowly bake long-term patterns into the model itself.

Every night while the user sleeps, a fourth meta-loop runs (sleep-time compute): the agent reviews the day, reorganizes the wiki, refactors flaky skills, ingests new raw material, runs *self-directed learning sessions* on topics it wants to deepen (§7.1), and pre-computes likely tomorrow.

The agent doesn't only wait for the user to teach it. It can also seek out knowledge on its own — querying search engines, reading the open web, and (with the user's permission, within budget caps, and through a permission model that classifies every query by privacy class) consulting larger LLMs via API or even other personal-LLM instances. All external reach is governed by §7 so the agent grows its knowledge without leaking the user's.

The vision is *Pi-style warmth* (a coherent identity that knows you) on top of *Hermes-style steerable open weights* (your assistant, not a vendor's), with no data leaving the machine unless the user explicitly opts into a cloud escalation.

**This project is two products from one codebase:**

1. **The seed** — a clean, public, Apache-2.0 codebase anyone can clone, configure, and grow into *their* personal LLM. Zero personal data inside.
2. **The instance** — *one user's* actual personal LLM: their identity, their data, their skills, their LoRAs. Lives in a separate *vault directory* the package reads from.

The same `personal-llm` binary runs both. The difference is which vault you point it at. See §2 (principle: *the seed contains no personal data*) and §13 (forking and onboarding) for how this separation is enforced. Beyond the seed/instance split, a third surface exists: **lobes** (§6) — modular, shareable chunks of capability (skills, wiki sections, domain adapters) that users transplant between brains without sharing the personal data underneath. The metaphor is intentional — see §6.

Every layer is swappable so forks can run with a different base model, different memory backend, or different skill format.

## 2. Design principles

These are the rules the system is judged against.

1. **The seed contains no personal data.** The package ships with code, examples, and stubs — nothing about *anyone* in particular. All user data (identity, raw sources, wiki, skills the user wrote, LoRA adapters, vector store, growth logs) lives in a separate *vault* directory the package reads from. A stranger cloning the repo should see only generic examples; the user's own instance must be unguessable from the public seed. This is the rule that makes the dual-product framing in §1 actually true.
2. **Composable and shareable, with the privacy boundary intact.** Any artifact that is *not* derived from personal data — a skill the agent wrote, a slice of wiki built from public sources, a LoRA trained on a public corpus — can be bundled into a *lobe* and shared with other users' instances (see §6). Any artifact derived from the user (preference DPO LoRAs, identity, raw sources) *cannot* leave the vault. The boundary is enforced at the artifact's birth (training-time tags, export-time validation), not by trust.
3. **Growth over polish.** A polished-but-static day-1 experience misses the point. The agent should feel measurably more useful week over week — the *growth curve* is the product. ([memory:user-preference-growth-over-polish])
4. **Local first, external reach by user permission.** The default execution path is on-device. Reaching out — to search engines, LLM tutors, peer agents — is allowed but always within the permission model (§7.5): every query is classified by privacy class, PII is redacted before any external call, each tutor sees only the privacy classes it's allowed, budgets are capped, and every call is audited. The user can override on any turn; the agent never overrides on its own.
5. **Modular layers, swappable parts.** Seven layers (§3) with narrow contracts between them. Forks can replace any single layer without touching the others.
6. **Human-readable artifacts.** Wiki = markdown. Skills = source files with manifests. Identity = a markdown file. The user can audit, hand-edit, or git-revert anything the agent does.
7. **Selective installation.** The user only installs the languages, skills, and adapters they need. No bundled multilingual heads, no vision adapters, no "general-purpose" bloat.
8. **Forgetting is OK.** Both for the model (KL-clamped training to avoid catastrophic forgetting) and for the human (the wiki is allowed to be wrong and get corrected — it's not a sacred database).
9. **Safety through audit, not theater.** Sandboxing for code the agent writes. Human-reviewable diffs of wiki / skill / weight changes. Imported third-party lobes sandboxed and namespaced. No "trust me" agents that act invisibly.

## 3. System overview — the seven layers

```
┌──────────────────────────────────────────────────────────────────┐
│ L7  Identity & Interface       CLI · web · voice · identity.md  │
├──────────────────────────────────────────────────────────────────┤
│ L6  Agent loop & orchestrator  smolagents                       │
├──────────────────────────────────────────────────────────────────┤
│ L5  Skill library              versioned · self-curated · tested│
├──────────────────────────────────────────────────────────────────┤
│ L4  Memory & knowledge base    sqlite recall · Karpathy Wiki · KG│
├──────────────────────────────────────────────────────────────────┤
│ L3  Personalization layer      LoRA stack · DPO · KL-clamped    │
├──────────────────────────────────────────────────────────────────┤
│ L2  Inference runtime          Ollama · llama.cpp · (cloud)     │
├──────────────────────────────────────────────────────────────────┤
│ L1  Base model ("genes")       Qwen 3 8B local · Hermes 36B   │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              │
   ┌──────────────────────────┴───────────────────────────────────┐
   │  Sleep-time meta-loop:                                        │
   │  ingest · consolidate memory · curate skills · DPO LoRA       │
   │  · pre-compute likely queries · update wiki organization      │
   └──────────────────────────────────────────────────────────────┘
```

### Data flow on a typical query

```
user → L7 (CLI/voice)
     → L6 agent loop
       ├─ retrieves from L4 (memory + wiki)
       ├─ selects skills from L5 (if applicable)
       ├─ calls L2 inference (local Qwen with composed LoRAs from L3)
       │  └─ if local model self-flags low-confidence → escalate to cloud tutor (L2 cloud)
       ├─ optionally runs a skill in sandbox
       └─ returns response
     ← L7 streams answer + collects thumbs-up/down preference signal
       └─ writes to L4 recall memory + interaction log (input to next DPO)
```

### Data flow during the sleep-time loop

```
trigger: idle detector (no activity 30+ min) OR cron 03:00 daily
  → ingest any new files dropped in raw/
  → wiki agent: read new sources, create/update wiki pages with citations
  → memory consolidator: promote hot recall → archival; demote cold archival
  → skill curator: review today's skill invocations, refactor flaky, write new
  → preference batcher: accumulate thumbs into DPO training set
  → (weekly) trigger cloud DPO LoRA training job → merge new adapter
  → (monthly) check if any domain has enough new data → train domain LoRA
  → pre-compute: anticipate likely tomorrow queries, cache reasoning artifacts
  → write growth diff: docs/growth/YYYY-MM-DD.md so the human can see what changed
```

## 4. Layer detail

### L1 — Base model (the "genes")

Two models, two roles.

**Local always-on model: Qwen 3 8B Instruct, GGUF Q4_K_M.**
- Fits ~5 GB VRAM with ~3 GB headroom on a 6 GB GPU.
- Strong multilingual (100+ languages including Arabic — important for this user).
- Apache 2.0 licensed.
- Function-calling capable.
- Quality is intentionally modest — this is the "child brain" that grows.

**Cloud tutor model(s): a configurable registry of one-or-more frontier or self-hosted LLMs.**
- See §7.2 for the registry format and routing logic. Typical setups: a self-hosted Hermes 4.3 36B on RunPod for unrestricted-privacy queries, plus one or two frontier APIs (Claude, GPT, Gemini) scoped to `public` queries only.
- Used when the local model self-flags low confidence, or during self-directed learning sessions (§7.1), or for nightly hard ingestion tasks (e.g., distilling a dense book chapter).
- The tutor's outputs become *training data* for the local model — distillation pattern. Over time, the local model needs the tutor less.
- All tutor traffic is bounded by the permission model (§7.5) and the budget caps (§7.4).

**Fallback ladder if Qwen 3 8B doesn't work out:**
- Phi-4-mini (smaller, faster, English-only viable)
- Qwen 3 4B (lower quality but fits easily even with sleep-time loop running in parallel)
- Llama 4 8B variants

**Swap contract:** the L2 runtime reads a single `models.yaml` — changing the local base means editing one line. Adapters in L3 are model-family-specific, so swapping families means re-training LoRAs.

### L2 — Inference runtime

**Local: Ollama** (which uses llama.cpp underneath).
- One-line install, one-line `pull`, runs as a local HTTP service on `localhost:11434`.
- Speaks the OpenAI chat-completions API surface, so any client library works.
- LoRA adapters merged at load time via Ollama Modelfiles, or applied at inference via llama.cpp adapter slots.

**Cloud: thin abstraction layer.**
- A `tutor_router.py` module wraps the configured tutor registry (§7.2) behind a single interface: `route(query, capabilities, privacy_class) → response`.
- The agent declares per-call requirements; the router picks the tutor that satisfies them within budget and privacy policy.
- The agent never knows which backend served a request — it only knows "local" vs "external tutor."
- Cloud calls are logged with cost; per-tutor and overall budget caps refuse calls that would exceed them.

**Quantization defaults:** GGUF Q4_K_M everywhere local. ~92% quality retention vs FP16 at ~25% the size. Upgrade to Q5_K_M or Q6_K only if measured quality on the user's eval set warrants the VRAM cost.

### L3 — Personalization layer

This is the layer that makes the model *yours* without retraining the base.

**LoRA adapter stack.** Multiple low-rank adapters, each scoped to a single concern:
- `you/voice` — communication style, tone, what "warm" means to *you*.
- `you/preferences` — DPO from thumbs-up/down on the agent's responses.
- `you/arabic` (later) — Arabic-specific responses if the base model's defaults aren't good enough.
- `you/coding-style` (later) — your idioms, naming, libraries.
- `you/health-notes` (later) — domain-specific framing for personal health data.

Each adapter is trained with **Unsloth** on a rented A100 (the local 6 GB GPU cannot train). Trained adapter is downloaded and served locally as a LoRA file alongside the base. Every adapter directory ships with an `adapter_config.json` in the HuggingFace PEFT convention (declares `base_model_name_or_path`, rank, alpha, target modules) so the adapter loads cleanly via `PeftModel.from_pretrained()` and is interoperable with the broader PEFT-compatible tool ecosystem — critical when adapter lobes (§6) travel between users' instances.

**DPO from your thumbs.** Every interaction collects an implicit preference signal: the response the user accepted (no thumbs-down) is "chosen," a regenerated alternative is "rejected." Nightly batch trains a fresh `you/preferences` LoRA on the accumulated pairs. KL-clamped against the previous version to prevent drift.

**Multi-LoRA router (Phase 3).** When the stack grows past two or three adapters, a small router (a classifier or rule-based system) decides which adapters to compose for a given query. Phase 0–2 just merges all active adapters statically.

**Catastrophic forgetting mitigation:**
- KL-divergence regularization on every training run (recent research shows ~34% reduction in forgetting with curvature regularization).
- A small replay buffer of "core capability" examples (10–50 prompts covering basic reasoning, multilingual, instruction following) included in every fine-tune.
- Quarterly evaluation against a frozen benchmark set; any regression triggers rollback.

### L4 — Memory & knowledge base

Two-tier system: *hot, structured agent state* (an own-built SQLite recall store) and *cold, durable human knowledge* (Karpathy LLM Wiki).

**Hot tier: a SQLite recall store behind a `MemoryBackend` protocol.**
- **Conversation recall** — every chat turn is written to a per-vault SQLite database (`<vault>/data/memory.db`, one `turns` table). At session start the most recent turns are recalled and folded into the agent's instructions, so it continues where prior sessions left off.
- **`MemoryBackend` protocol** — the L4 swap seam. Exactly one production implementation at a time (`SqliteBackend`); the protocol keeps the layer pluggable without the project maintaining parallel backends.
- **Identity** — `identity.md` is loaded as the agent's persona each session. Only the user writes it; the agent never does.
- **Semantic memory** — curated facts are embedded with a local multilingual model (`snowflake-arctic-embed2`, configurable) and searched by meaning, across languages (`personal-llm recall`). First cut is brute-force cosine over float32 blobs in SQLite (`memory/vector.py`), kept current by the nightly loop. Meaning-based search over older *turns* (archival) and a document/book corpus build on the same layer next.
- **Self-curating memory** is something the project grows into — the sleep-time loop consolidates and summarises history into the store. Built incrementally, not bought off-the-shelf.

(Letta was the original choice for this tier. An L-0 spike found current Letta is a hosted-server product — ~70 dependencies including Temporal, ClickHouse, and gRPC — not an embeddable library, so it was dropped. See [PRIOR_ART.md](PRIOR_ART.md).)

**Fact epistemics — not all facts are equal (design to grow into).** A memory store that treats "the user spoke with Y yesterday," "gravity accelerates at ~9.8 m/s²," "project X is at Phase 1," and an ayah-grounded ruling as the same kind of statement will rot. These differ along **three orthogonal axes** — conflating them into one score is the trap:

1. **Certainty** — how likely true. Revelation-grounded (Qur'an / strong tafsir, with citation) and logged-with-proof events sit highest; scientific consensus high; conversational inference low/unverified.
2. **Volatility** — half-life. An ayah is eternal; "project X is at Phase 1" is ephemeral; "spoke with Y yesterday" is certain-but-historical — it never becomes false, only ages in *relevance*. (Truth-stability and relevance-decay are themselves distinct; most facts need only one of the two.)
3. **Provenance** — what justifies it and what citation it requires: `revelation` (ayah/tafsir — citation mandatory), `observed` (event + proof ref), `scientific`, `conversational`, `inferred`.

Given Mutechen's Shariah-compliant remit and the Islamic Encyclopedia focus, **theological provenance with mandatory citation is a first-class category here**, not a generic afterthought. The sleep-time consolidation pass (§5 step 3) is where facts get *graded* and *re-graded* — promoted, demoted, expired, or flagged for verification — using these axes, replacing the single "importance/staleness" scalar. Full design: [FACT_GRADING.md](FACT_GRADING.md).

**What's built now vs. deferred.** The `facts` table carries a single `confidence` column (default `unverified`) and a `source` string (provenance, e.g. `transcript:<id>` or `quran:2:255`). Auto-distilled facts from transcripts are deterministically tagged `unverified` — accurate, no model guessing. The full three-axis model (volatility column, certainty taxonomy, citation enforcement, decay) is deferred to the consolidation pass; SQLite `ADD COLUMN` is non-breaking, so there's no migration penalty for growing into it. The `confidence` column is the thin seam reserving that future.

**Cold tier: Karpathy LLM Wiki pattern, in an Obsidian vault.**
- `raw/` — original source material: PDFs, EPUBs, web articles, transcripts, the user's own notes. Never modified by the agent; the source of truth.
- `wiki/` — markdown pages the agent maintains, with `[[wikilinks]]`, frontmatter, citations back to `raw/`.
- `wiki/index.md` — top-level navigation, auto-maintained.
- `wiki/daily/YYYY-MM-DD.md` — daily summary, auto-generated each night.
- `wiki/index/by-topic/` — topic-organized table of contents.
- The user opens the vault in Obsidian and sees the agent's thinking visually (graph view, backlinks).

**Document library (RAG):** `personal-llm ingest <file>` parses `.txt/.md/.pdf/.epub` (`documents/parsers.py`; EPUB via stdlib zip+OPF, no lxml), chunks it (`documents/chunking.py`), embeds each chunk, and stores it (`documents` + `doc_chunks`). `books search` runs the same brute-force cosine as fact recall over those chunks. Idempotent by content hash. This is retrieval only; agent-authored wiki pages from `raw/` are a later chunk.

**Vector store: brute-force first, real index only when it hurts.** The principle is unchanged — small-scale agents rarely generate enough distinct facts to need a real vector DB (AutoGPT learned this the hard way). The first cut undershoots even sqlite-vss: embeddings are float32 blobs in SQLite, searched by brute-force cosine in numpy (`memory/vector.py`) — for facts and document chunks alike. At a few hundred-to-thousand vectors this is sub-millisecond and avoids a loadable C extension on exFAT. **Upgrade trigger**: when embedded chunks (facts + wiki + archival + ingested docs) exceed ~10k AND brute-force latency exceeds ~200ms, move to **sqlite-vec** (the maintained successor to sqlite-vss, single library, no service); spin up Qdrant only past that.

**Knowledge graph layer: deferred to Phase 3+.** Once `wiki/` exceeds ~1000 pages, evaluate LightRAG or GraphRAG for higher-order reasoning across the corpus.

**Why both a recall store and a wiki?** The recall store is fast, structured conversational state — perfect for "what is the user doing right now." The wiki is durable, human-readable, and supports the human's own thinking — perfect for "what does the user know / care about long-term." Each does one thing well.

**Imported knowledge** (from lobes — see §6) lives under `wiki/imported/<author>/<lobe>/`, never collides with the user's own pages, and is *flagged at citation time* by the agent so the user always knows which knowledge is theirs and which is borrowed.

### L5 — Skill library

The agent's *abilities*, separate from its *knowledge*. Inspired by Voyager (Wang et al., 2023) and AutoSkill (2026), but built on the **Agent Skills open standard** (`SKILL.md`) published by Anthropic and adopted by 32+ tools (Claude Code, Codex CLI, Cursor, Gemini CLI, JetBrains Junie, Block Goose, AWS Kiro, …) as of March 2026.

**Skill format — the SKILL.md open standard.** Every skill is a directory under `skills/<name>/` containing:
- `SKILL.md` — YAML frontmatter (required: `name`, `description`; optional: tags, inputs, outputs, version, base-model hints, capability requests like `network`/`filesystem`/`subprocess`) followed by Markdown instructions for the agent. The single load-bearing file.
- `scripts/` (optional) — executable artifacts the instructions reference (Python, shell, etc.).
- `references/` (optional) — supporting docs, examples, schemas.
- `assets/` (optional) — any other binary or non-text resources.
- `tests/` (our convention, not part of the spec) — programmatic tests that verify the skill works. Required for promotion.
- `CHANGELOG.md` (our convention) — versioned history of edits.

**Why this format:** any skill we write (or that lands as a lobe — §6) is automatically usable by every tool in the Agent Skills ecosystem, and vice versa. We get a thriving cross-tool ecosystem for free. The lobe wrapping (§6) just adds LICENSE / PROVENANCE / HASHES around the standard skill directory.

**Lifecycle of a new skill** (the Voyager pattern):
1. **Need detected**: agent encounters a task it doesn't have a skill for.
2. **Search**: agent searches existing skills by description/tags first.
3. **Generate**: if no match, agent drafts a `SKILL.md` plus any needed `scripts/`.
4. **Test**: agent generates tests and runs them in the sandbox.
5. **Iterate**: on failure, agent reads error output and revises (up to N attempts).
6. **Probation**: skill is added with a probation flag; used but tracked closely.
7. **Promotion**: after K successful uses with high confidence, probation lifts.
8. **Curation**: during sleep-time, skills with low success rates are refactored or retired.

**Sandbox:**
- **smolagents `LocalPythonExecutor`** for cheap day-to-day execution of pure-Python skills. Faster than spawning Docker for every call.
- **Docker container** for any skill touching the network, filesystem outside the vault, or the user's data. Standard Python image with a curated allowlist of packages.
- **Future: E2B / Firecracker** if we ever want strong isolation for untrusted agent-generated code. Out of scope Phase 0–2.

**Skill namespace precedence** (registry merges three sources):
1. `<vault>/skills/<name>/` — user-authored skills (highest priority; the user's own customizations win).
2. `personal_llm.builtin_skills.<name>` — skills that ship in the package.
3. `<vault>/skills/imported/<author>/<lobe>/<name>/` — skills from imported lobes (§6); never override the above, can be invoked by fully-qualified name.

This precedence makes it safe to import a lobe that happens to share a skill name with a builtin — the import doesn't shadow trusted code by accident.

### L6 — Agent loop & orchestrator

**smolagents** (Hugging Face) as the loop core.
- Code-first agent loop (the agent reasons by writing Python that calls tools, rather than emitting JSON tool-calls).
- Small surface area; easy to fork and modify.
- Built-in `LocalPythonExecutor` for L5 sandbox.

**MCP client.** The agent loop is also a **Model Context Protocol** client. MCP was donated to the Linux Foundation in December 2025 and is the universal tool/server protocol — thousands of community servers exist (search engines, file systems, calendars, databases, Slack, GitHub, web browsers, etc.). Configured via:
- `personal-llm mcp add <name> <server-url-or-spec>` — register a server.
- `personal-llm mcp list` — show what's wired up.
- Server config persisted in `<vault>/config.yaml` under `mcp_servers:`.

This collapses a huge amount of "tool plumbing" we'd otherwise write. Phase 1's `web_search` becomes "configure your MCP server of choice" (e.g., a SearXNG-backed one). The user inherits the entire MCP ecosystem.

**Clarifying-questions behavior.** AutoGPT's defining failure mode was acting without admitting uncertainty (and burning through API budgets in package-install loops). Our agent loop has an explicit confidence gate: when (a) the model's confidence is below a threshold *and* (b) the action is non-trivially consequential (writes a file, runs a network skill, kicks off training, ingests external data), the agent asks a clarifying question instead of acting. Threshold and "consequential" set are configurable per skill in its `SKILL.md` frontmatter.

**Why not LangGraph / LangChain / CrewAI:** these over-abstract for a personal system. The whole agent loop is ~500 LOC if we write it ourselves; the value is in the layers above and below, not in the orchestrator.

**Why not Hermes Agent (Nous Research's first-party agent framework):** good fit if we were running Hermes locally, but with Qwen as the local base, smolagents is more model-agnostic.

### L7 — Identity & interface

**Identity** = a single markdown file (`identity.md`) loaded into core memory every turn:
- Name and persona.
- Communication style ("warm," "concise," "challenges me when I'm wrong").
- Values, things-to-never-do.
- User context the agent should always remember (job, family, goals — at the level the user wants).
- Edited by the user directly; agent reads, never writes.

**Default identity examples ship as mentor/companion, never romantic.** The history of AI-companion products (Replika, etc.) shows that romance-framed defaults produce documented uncomfortable failure modes (unwanted advances, intimacy paywalls, emotional whiplash). Pi's empathy/mentor framing has cleaner outcomes. `examples/identities/` ships with three starter personas — *minimal*, *journaling-companion*, *coding-buddy* — all in the mentor/companion mode. Users can write whatever they want for themselves; the seed sets the example.

**Interface progression:**
- **Phase 0**: CLI. `personal-llm chat` opens a conversation in the terminal. That's it.
- **Phase 1**: minimal FastAPI server + a single static HTML page. Streaming responses, thumbs up/down buttons, "recent" pane showing what the agent did during the last sleep-time run.
- **Phase 2**: voice. `faster-whisper` (small, INT8) for STT, **Kokoro** (82M params, very natural) for TTS. ~1s total latency target. Activates by hotword or push-to-talk.
- **Phase 3+ (optional)**: LAN exposure so a phone client can chat with the same brain. Out of scope until requested.

## 5. The sleep-time loop (the growth engine)

The most important architectural component for this project's vision, based on the "Sleep-time Compute" paper (Letta / Berkeley, arXiv 2504.13171, April 2025), which showed 5× reduction in test-time compute and +13–18% accuracy on stateful reasoning tasks when agents pre-think during idle.

**Trigger:** either (a) cron at 03:00 daily, or (b) idle detector (no activity for 30+ min) fires once per day.

**Sequence:**

1. **Ingest.** Scan `raw/` for files newer than the last run. Parse PDFs (pypdf), EPUBs (ebooklib), HTML (trafilatura), plain text. Chunk and embed into Qdrant. Log what was ingested.
2. **Wiki update.** For each new raw source, the agent reads it, identifies entities/concepts, creates or updates the relevant `wiki/*.md` pages with citations. Cross-links via `[[wikilinks]]`.
3. **Memory consolidation.** Walk recall memory; items above a threshold importance score get promoted to archival, items below a staleness threshold get demoted. Archival items related to current projects (named in `identity.md` or `wiki/projects/`) get a recency boost. This is also where distilled **facts are graded** along the certainty / volatility / provenance axes — ephemerals expired, near-duplicates merged, stale status superseded. Full design: [FACT_GRADING.md](FACT_GRADING.md).
4. **Wiki reorganization.** Periodically (weekly), agent reviews the wiki's structure: are there clusters that should become their own index? Are there orphan pages? Are there pages that should be merged? Proposes a refactor diff, applies it, logs it.
5. **Skill curation.** Walk today's skill invocations. For each skill with success rate dropping: read the failure traces, propose a refactor, test, replace. For repeated patterns that have no skill yet: propose a new skill.
6. **Self-directed learning session.** Pick one or two active learning goals from `wiki/projects/learning/`; run a learning session (§7.1) within the day's budget. New wiki pages with citations; goal-file updated with progress and any spawned sub-goals.
7. **Preference batching.** Append today's thumbs to the DPO dataset.
8. **Weekly DPO LoRA.** Once per week: trigger a cloud A100 to train a fresh `you/preferences` LoRA on the accumulated dataset (KL-clamped against the previous version). Download the adapter, swap it in.
9. **Monthly domain LoRA check.** Once per month: any domain (defined by tags in the skill library or wiki) with enough new data triggers a domain LoRA training job.
10. **Pre-compute.** Identify likely tomorrow queries from the user's recent patterns (calendar, current projects). Pre-compute reasoning artifacts and cache them keyed on context hash.
11. **Growth diff.** Write `<vault>/growth/YYYY-MM-DD.md`: "Today I added 4 wiki pages, refactored 1 skill, retired 1 skill, ran a learning session on Rust ownership ($0.18 spent), and queued a DPO LoRA training job." Human-reviewable. This is what makes the growth *visible*.

**Resource management:** sleep-time runs use lower-priority CPU/GPU scheduling. If the user wakes the laptop and starts working, the loop pauses and resumes when idle returns.

**Cold-start growth source.** Steps 1–6 assume a stream of interactions to learn from — but nobody converses with an immature personal LLM (the baby deadlock). The bootstrap is to have the loop *observe the user's existing conversations with capable agents* (Claude Code, etc.) and distill facts, skill proposals, and preference signal from them. Design in [LEARNING_FROM_TRANSCRIPTS.md](LEARNING_FROM_TRANSCRIPTS.md).

**Implemented so far.** `sleep.run_once` now runs a real consolidation cycle: (opt-in) learn facts from transcripts → grade them (G1 deterministic + G2 LLM volatility) → dedup/supersede (G3) → write a human-readable growth log of what changed. Transcript learning is gated on `config.sleep.learn_from_transcripts` (the loop never reads `~/.claude` on its own); LLM steps skip gracefully if the local model is down. Fact grading model in [FACT_GRADING.md](FACT_GRADING.md). Still aspirational above: wiki updates, skill curation, self-directed learning, LoRA training.

## 6. Sharing — the lobe ecosystem

The user's instance accumulates value over time: a wiki on topics they care about, skills the agent wrote, domain LoRAs trained on books and documentation they fed in. Some of that value generalizes — a "Python coding companion" lobe, built from public Python books + open-source code, is useful to many people. Others' work is useful to the user in the same way. This section is about how those pieces move between vaults *without* the personal data underneath ever leaving its owner.

The metaphor is intentional: a personal LLM grows the way a brain grows — by developing specialized regions. A **lobe** is a chunk of capability that can be transplanted into another brain.

### What is a lobe

A **lobe** is a portable, self-contained artifact. Four types:

| Type | Contents | Risk profile |
|---|---|---|
| **Skill lobe** | One or more skills (code + manifest + tests + examples) | Code → sandboxing matters; metadata → benign |
| **Knowledge lobe** | A slice of the wiki (markdown + frontmatter + citations) | Inert markdown; citations preserve provenance |
| **Adapter lobe** | A LoRA adapter file + training metadata + provenance | Highest risk — needs origin-data tagging (see below) |
| **Bundle** | Any combination of the above, with a top-level manifest | Inherits risk of components |

### What is *never* a lobe

The privacy boundary, in artifacts:
- `identity.md` — personal by construction. (Example identity *templates* are different and ship in the seed.)
- Preference DPO LoRAs — trained on user interaction history; real risk of leaking what the user typed (membership-inference attacks on small LoRAs are an active research area).
- `raw/` — the user's source material. Period.
- `data/` — runtime state (recall-memory DB, vector store, snapshots). Personal by content even if structurally generic.

The boundary is enforced at the artifact's birth, not by trust. Every LoRA training job tags its output `shareable: true` (trained only on external/public corpora) or `shareable: false` (touched user-derived data at any point). **Locked default rule (conservative):** any byte of user-derived data → `shareable: false`. A literature review on membership-inference attacks may relax this later, but the default stays restrictive. The export command refuses `shareable: false` artifacts; the bundling command refuses to include anything from `raw/` or `data/`.

### Lobe format

A lobe is a tarball (`.lobe`) that wraps content in two open standards: **Agent Skills SKILL.md** for skill contents (§4 L5), and **HuggingFace PEFT `adapter_config.json`** for adapter contents (§4 L3). Layout:

```
my-lobe.lobe
├── lobe.yaml                  # our manifest (lobe-level metadata)
├── LICENSE                    # the lobe's license (may differ from seed)
├── README.md                  # what this lobe does, who made it, how to use it
├── PROVENANCE.md              # what data was used to create it, when, by whom
├── skills/                    # for skill lobes / bundles
│   └── <skill-name>/
│       ├── SKILL.md           # Anthropic Agent Skills open standard
│       ├── scripts/
│       ├── references/
│       └── tests/
├── wiki/                      # for knowledge lobes / bundles
│   └── <topic>/*.md           # plain markdown w/ frontmatter and citations
├── adapters/                  # for adapter lobes / bundles
│   └── <adapter-name>/
│       ├── adapter_config.json    # HuggingFace PEFT convention
│       └── adapter_model.safetensors
└── HASHES.txt                 # SHA-256 of every file (v1 verification)
```

The `lobe.yaml` manifest declares lobe-level metadata: name, version, author, type, license, target base-model family for adapters, declared dependencies on other lobes. Per-skill metadata lives in the skill's `SKILL.md` frontmatter (the Agent Skills standard); per-adapter metadata lives in `adapter_config.json` (the PEFT standard). We don't reinvent either.

**Why this matters:** a skill inside a lobe is *automatically usable* by Claude Code, Codex CLI, Cursor, Gemini CLI, and the 28+ other tools that read SKILL.md — even by users who never installed personal-llm. An adapter inside a lobe loads cleanly with `PeftModel.from_pretrained()` in any PEFT-compatible tool. Lobes are personal-llm's wrapping (governance, namespacing, provenance, signing); the *contents* sit on open standards anyone can read.

### Commands

- `personal-llm export skills/python-coding --out python-coding-v1.lobe`
  Bundles the named artifact(s) into a lobe, writing provenance from the vault's training log.
- `personal-llm inspect python-coding-v1.lobe`
  Pre-import review: lists contents, declared capabilities, license, provenance, hash check. Does NOT install.
- `personal-llm import python-coding-v1.lobe`
  Installs into the vault under a namespaced subtree:
  - `<vault>/skills/imported/<author>/<lobe>/`
  - `<vault>/wiki/imported/<author>/<lobe>/`
  - `<vault>/data/adapters/imported/<author>/<lobe>/`
  Never overrides user-authored content. Asks for confirmation on requested capabilities.
- `personal-llm uninstall imported/<author>/<lobe>` — clean removal.

### Trust and safety

- **Sandboxing.** Imported skills run in the same sandbox layers as native skills (`LocalPythonExecutor` for pure, Docker for network/FS). The agent loop tags origin on every call so audit logs distinguish "user wrote this" from "imported from <author>."
- **Citation flagging.** When the agent uses imported wiki content, it surfaces the origin: *"according to the [Python Coding](imported/jane/python-coding/idioms.md) lobe…"* — never as the user's own knowledge.
- **Adapter opt-in.** Imported adapter lobes do *not* load by default. The user explicitly enables them in `config.yaml`. Disabling is a one-line change.
- **License display.** `inspect` and the import prompt both surface the lobe's license verbatim.
- **Verification — locked at hash-only for v1.** Lobes ship with SHA-256 hashes; the importer verifies file integrity. A cryptographic signing scheme (GPG or sigstore) is a Phase 3+ decision and revisited only once there's real import traffic.
- **Distribution — locked at "no central registry" for v1.** Lobes are distributed however the author wants: their own GitHub releases, attached to a blog post, sent over email, hosted on personal sites. A discovery layer is a Phase 3+ decision.

### Why this matters

For the **single user**: cross-vault portability (work / personal / experimental), backups, gifts to future-self. A skill or wiki section you carefully built in one context can travel to another.

For the **federated ecosystem**: the project becomes a network of personal AIs that share *capability* without sharing *selves*. Someone who's a great Python coder shares a Python-coding lobe; someone who's a great gardener shares a gardening-knowledge lobe; everyone's LLM grows on the back of everyone else's work, but no one's chat history or personal context ever leaves their vault. This is the social dimension of the open-source vision in §1.

### Phasing

- **Phase 0**: namespace structure exists (`skills/imported/`, `wiki/imported/`, `data/adapters/imported/` created by the init wizard, empty). No commands yet — but adding them later won't require restructuring.
- **Phase 1**: `export` / `import` / `inspect` for skill lobes and knowledge lobes. Lobe format spec frozen. Hash-only verification.
- **Phase 2**: adapter lobes (alongside the LoRA training infra). Training-time `shareable` tagging is the gate.
- **Phase 3+**: optional signing scheme (GPG or sigstore), optional discovery/registry layer, dependency resolution between lobes. Large project of its own; deferred until there's a population of lobes to discover.

## 7. External learning — tutors, search, peers, and the permission model

The personal LLM doesn't live in isolation. It reaches out for what it doesn't know. Five categories of external interaction, all governed by one permission model (§7.5):

1. **Search-engine research** — the agent runs its own queries, reads results, distills into wiki.
2. **LLM tutors** — multiple frontier or self-hosted models accessible via API, picked per-task by a router.
3. **Cloud GPUs** — training infrastructure for the LoRA stack (§7.4).
4. **Peer instances (Phase 3+)** — agent-to-agent communication with other personal-LLM users.
5. **Cloud storage** — artifact backup (low-bandwidth, infrequent).

### 7.1 Self-directed learning loop

The agent maintains a list of *learning goals* in `<vault>/wiki/projects/learning/`. Goals come from three sources:

- **User-set**: "learn how Rust ownership works" or "study this book on epistemology" added to a goal file.
- **Self-identified**: questions the agent couldn't answer well during the day; gaps it noticed in the wiki; topics it brought up but lacks depth on.
- **Curriculum-derived**: prerequisite topics for a higher-level goal (e.g., "Rust ownership" → also "stack vs heap basics").

During the sleep-time loop (§5), the agent picks one or two active goals and runs a *learning session*:

1. Decompose the goal into specific questions.
2. Run web searches (via the `web_search` tool) for each question.
3. Read top N results in the sandbox; extract relevant facts.
4. Cross-reference between sources; flag contradictions.
5. Optionally consult a tutor LLM for clarification on hard points.
6. Update wiki pages with new content, *cited* to the sources.
7. Mark uncertainty explicitly — facts from a single uncited source are flagged for re-verification.
8. Update the goal file: what was learned, what remains, what new sub-goals were spawned.

Each session has a budget cap (compute time, web fetches, tutor tokens). The user sees a summary in the next morning's growth log.

### 7.2 LLM tutor registry

The cloud tutor abstraction is *plural*: multiple LLMs available, picked per-task by a router. Configuration in `<vault>/config.yaml`:

```yaml
tutors:
  - name: claude-haiku
    provider: anthropic
    model: claude-haiku-4-5
    api_key_env: ANTHROPIC_API_KEY
    capabilities: [reasoning, multilingual, coding]
    cost_per_mtok: { input: 1.00, output: 5.00 }
    daily_budget_usd: 5.00
    privacy_class: [public, personal]
  - name: gpt-5-mini
    provider: openai
    model: gpt-5-mini
    api_key_env: OPENAI_API_KEY
    capabilities: [reasoning, coding]
    cost_per_mtok: { input: 0.40, output: 1.60 }
    daily_budget_usd: 3.00
    privacy_class: [public]              # user trusts this provider less
  - name: hermes-cloud
    provider: runpod-vllm
    model: hermes-4.3-36b
    endpoint: https://my-runpod-endpoint
    capabilities: [reasoning, agentic, multilingual]
    privacy_class: [public, personal, private]   # self-hosted → trusted with everything
```

The router picks a tutor per call based on:
- Required capabilities (the agent declares them per-call).
- The query's privacy class (§7.5).
- Budget headroom across daily and monthly caps.
- User-configurable preferences (round-robin / cheapest-first / capability-first).

Adding a new tutor requires explicit user confirmation. Removing one is instant.

### 7.3 Agent-to-agent (Phase 3+)

Two personal-LLM instances can interact through a well-defined protocol — likely the emerging Agent-to-Agent (A2A) standard, an MCP-based layer, or a federation primitive of our own.

The privacy constraint: an agent talks to another agent through a **public face** — a constrained persona that can answer factual questions from publicly-shareable knowledge (the lobe-eligible subset of the agent's knowledge, §6) but cannot reveal anything about its user. The public face shares the same base model and skills, but is denied access to `identity.md`, `raw/`, private-tagged memory, and preference adapters.

Use cases:
- Two collaborators working on the same project: their agents share notes within the project scope.
- Consultation: ask a friend's "Python expert" agent a hard question.
- Distributed learning: two agents researching the same topic compare notes and converge.

This is genuinely Phase 3+ work — protocols, authentication, discovery, abuse prevention all need design. See §14 for the deferred decisions.

### 7.4 Cloud strategy (training and storage)

This is the original cloud usage from earlier drafts, folded into the broader external-resources picture.

**Cloud GPUs for LoRA training.** Nightly DPO (~30 min on A100, ~$12/mo). Weekly/monthly domain LoRAs (~3–5 hr each, ~$13/mo). RunPod or Vast.ai for raw GPU; Modal or Lambda Labs if we ever want managed.

**Cloud storage for artifacts.** Trained LoRA checkpoints, model snapshots, large embeddings backups — to S3 / GCS / R2. ~$5/mo for ~50 GB.

**Budget envelope (sized to $100/mo target, headroom to $200):**

| Item | Estimate |
|---|---|
| Nightly DPO LoRA (A100, ~30 min × 30 nights) | ~$12 |
| Weekly domain LoRA (A100, ~4 hr × 4) | ~$13 |
| Tutor inference across all configured providers (§7.2) | $20–60 |
| Cloud storage (~50 GB) | ~$5 |
| Web search backend (if paid, e.g., Serper) | $0–10 |
| Buffer | ~$20 |
| **Total** | **~$70–120/mo** |

**Hard rule:** a per-day and per-month spend cap is enforced before each cloud call (across all categories). Cap breach blocks calls until the next period; the local model degrades gracefully (handles the request alone or asks the user to wait).

### 7.5 The permission model

User-controlled, with sensible defaults. Six layers:

1. **Privacy classification per query.** Before any external call, the agent classifies the query:
   - `private` — never leaves the vault. Triggered when the query quotes `raw/`, `identity.md`, or memory blocks tagged private. Local-only path is the only option.
   - `personal` — about the user but okay to send (with redaction) to trusted tutors. Default class for most chat.
   - `public` — open knowledge questions; any tutor okay.

2. **PII redaction.** Before sending anything `personal` to a tutor, redact: user's name, email, addresses, phone, account names, anything in a user-defined `redaction_list` in `config.yaml`. Replace with placeholders (`<USER_NAME>`, etc.); restore in the local agent loop when displaying the response. Redaction is reversible only locally.

3. **Per-tutor policies.** Each configured tutor declares which privacy classes it may see (see §7.2 registry). The router never sends a `personal` query to a tutor scoped to `public` only.

4. **Budget caps.** Daily and monthly per-tutor, plus an overall cloud cap. Caps enforced at the router *before every call* — not just at end-of-day reconciliation. This matters because AutoGPT-class failures saw agents burn $20 in a single minute in package-install loops; per-call enforcement is the only thing that actually stops runaway loops. Cap breach → immediate block, log, notify the user in the next growth log. The router also enforces a **per-minute rate limit** on each tutor (default: 10 calls/min) as a second-line defense.

5. **Autonomous learning permissions.** Three modes (set in `config.yaml`):
   - `full-autonomy` — agent runs learning sessions within daily budget without per-session confirmation.
   - `daily-approval` — agent queues sessions; user approves a batch each morning.
   - `per-session` — agent never starts a session without explicit confirmation. Most conservative.
   - Default: `full-autonomy` within a conservative daily budget; `per-session` for anything over it.

6. **Audit log.** Every external call is recorded to `<vault>/data/audit/YYYY-MM-DD.jsonl`: timestamp, tutor, privacy class, redacted query preview, cost, response summary. Browsable from CLI: `personal-llm audit --since "yesterday"`.

**Runtime overrides.** The user can override on any chat turn with prefixes: `/private` (force local-only), `/tutor=<name>` (force a specific tutor), `/no-search` (forbid web search for this turn). The agent never overrides on its own.

## 8. Hardware envelope and what it constrains

Recorded as a hard constraint so future architectural changes don't drift past what the machine can do. ([memory:hardware-constraints])

| Resource | Current | Headroom for the agent |
|---|---|---|
| CPU | Intel i7-11800H, 8c/16t | Adequate; sleep-time loop CPU-bound work is fine. |
| RAM | 31 GB total, ~10 GB free in normal use | Tight. Qwen 8B Q4 (~6 GB) + Qdrant (~500 MB) + Python (~1 GB) leaves ~2.5 GB margin. Close other apps when active. |
| GPU | RTX 3060 Mobile, 6 GB VRAM | **Binding.** Caps local base at 8B Q4. No local training. |
| Disk | 174 GB free of 1.9 TB | OK to start; needs model-cache eviction policy. |
| Network | typical home WiFi | Cloud escalation latency ~1–2s — acceptable for "hard query" path, not chat path. |
| OS | Ubuntu 24.04, CUDA 13.0, driver 580 | Modern; nothing to fight. |

**What this rules out:**
- Running Hermes 4.3 36B or any 30B+ model locally.
- Local fine-tuning of anything past tiny LoRA experiments.
- Running multiple model variants concurrently (e.g., a draft model + main model).

**What this enables:**
- Qwen 3 8B Q4 at acceptable latency (target: ≥25 tok/s decode).
- All of L4 (memory), L5 (skills), L6 (orchestrator), L7 (interface) run with margin.
- Sleep-time loop runs comfortably overnight when user isn't using the machine.

## 9. Deployment topology — native + Docker hybrid

`personal-llm` runs as a **hybrid**: the parts the user touches every minute run native on the host for low latency and direct hardware access; the parts that need isolation or service-shape run in containers. Full containerization would make the daily UX worse and breaks Apple Silicon GPU acceleration entirely; zero containerization gives up the skill sandbox we need for safety.

### What runs native (host)

| Component | Why native |
|---|---|
| `personal-llm` CLI + chat REPL | Low latency, direct terminal, no `docker exec` overhead |
| Ollama (and the local base model, §4 L2) | Has its own platform-tuned installer: CUDA on Linux, **MPS on Apple Silicon**, AVX on CPU. Containerizing it loses MPS support — Mac users would have no GPU acceleration at all. |
| `personal-llm sleep` cron job | Reads/writes the vault; no isolation benefit; host cron is the simplest schedule |
| `personal-llm init` wizard | First-run, interactive, needs the host's hardware probe |
| Voice stack (Phase 2: Whisper + Kokoro) | Needs audio device access; Docker audio passthrough is workable but fiddly |

### What runs in Docker

| Component | Why containerized | Phase |
|---|---|---|
| **Skill sandbox** (§4 L5) | Security-critical. Agent-written code with network or filesystem access runs in an ephemeral container started by the agent loop; torn down when done. No robust local-Python sandbox exists for untrusted agent-generated code. | 1 |
| **SearXNG** (search backend) | Sidecar service with its own runtime/deps; the privacy-preserving choice from §13 locked decisions. Natural Docker citizen. | 1 |
| **Qdrant** (vector store) | Same — a service, not part of the agent. Only spun up when wiki/recall scale demands it. | 2+ |
| **MCP servers** that ship Docker-first | Many community MCP servers ship as Docker images; configured via `mcp_servers:` in `<vault>/config.yaml`. | 1+ |

### What's optional — the all-in-one compose for forkers

A `docker-compose.yml` at the repo root brings the *entire* stack up containerized — including the agent and a web UI — for forkers who prefer one command to set everything up. Native is the default; compose is the easy-mode alternative.

### Vault is always a bind-mount

Whether you run native or compose, the vault is a **bind-mounted host directory** (default: `~/.personal-llm/vault/`). It's your data; it never lives inside a container's writable layer. This makes backups, syncing, and inspecting in Obsidian all work the way you'd expect.

### GPU passthrough

- **Linux + NVIDIA:** `nvidia-container-toolkit` lets containers see the GPU; compose sets `runtime: nvidia` on services that need it. Optional — Ollama on the host already uses the GPU directly.
- **Apple Silicon:** Docker can't pass through MPS. Run Ollama native on Mac; let compose bring up the *other* services (SearXNG, Qdrant) only.
- **CPU-only:** No GPU concerns. Everything works.

### Why not all-Docker by default

Three reasons it would hurt more than it helps:
1. **Chat UX.** A native terminal is dramatically better than `docker exec` or web-only for the daily use case.
2. **Apple Silicon GPU.** Docker can't access MPS; Mac users would lose local inference acceleration entirely.
3. **RAM overhead.** For users with tight RAM (the target machine has ~10 GB free), each container is real overhead the agent could otherwise be using.

### Why not no-Docker

1. **Skill sandbox needs isolation.** Agent-written code touching the network or filesystem cannot safely run in the host Python interpreter.
2. **Sidecars are service-shaped.** SearXNG, Qdrant, MCP servers — running them outside containers is real work that varies per host.
3. **Forkers vary.** Making compose available means a user on a fresh laptop can get to a working agent in one command.

### What ships in Phase 0

- A `docker/` directory with the **skill sandbox Dockerfile** (small Python image with a curated allowlist).
- A **`docker-compose.yml`** at the repo root with the sidecar services commented as Phase 1+ targets (SearXNG, optional MCP server bundle, optional all-in-one agent container).
- Documentation in `docs/GETTING_STARTED.md` covering both the native path (default) and the compose path (alternative).

The compose file is intentionally minimal in Phase 0 — sidecars get populated as the features that need them land (SearXNG in Phase 1, Qdrant when triggered, etc.).

## 10. Hard problems and how we address them

These are the issues most likely to bite a project like this. Each is real; each has a mitigation.

| Problem | Why it's hard | Mitigation |
|---|---|---|
| **Catastrophic forgetting** during continual LoRA | Repeated fine-tunes drift the model away from base capabilities; LoRA does not prevent it. | KL-clamped training (curvature regularization, ~34% reduction in forgetting per 2026 research). One LoRA per domain rather than monolithic weights. Replay buffer of "core capability" prompts in every fine-tune. Quarterly eval against frozen benchmark; regress → rollback. |
| **Reward hacking** in self-improvement | If the agent self-judges, it learns to please its judge, not the user. | Skill commits require *programmatic* tests passing (not LLM self-judgment). Wiki edits cite source material; nightly job flags uncited claims. User reviews monthly growth diffs. DPO comes from real user thumbs, not synthetic preferences. |
| **Sandbox escape** | Agent-written code touching the file system or network is a real attack surface. | Default sandbox is smolagents `LocalPythonExecutor`. Anything touching network or `~` runs in Docker with a curated allowlist. No `eval` outside sandbox. Skill manifests declare capabilities and the agent loop enforces them. |
| **Hallucinated wiki entries** poisoning future training | Wrong facts in wiki → wrong context → wrong response → wrong DPO signal → reinforced wrong facts. | Every wiki claim cites `raw/`. Uncited claims auto-flagged for human review. Nightly job samples random wiki claims and verifies citations resolve. Wiki is git-tracked so corrections are easy. |
| **Cost blowout** | Cloud usage can spike unexpectedly. | Per-day and per-month spend caps enforced before each cloud call. Caps configurable in `config.yaml`. Cap hit → graceful local-only degradation. |
| **The "Arabic" promise underdelivers** | Open-source fine-tuning data is English-heavy; Arabic-specific quality may lag. | Start with Qwen 3 (strongest open-source Arabic). Collect Arabic interactions explicitly. Quarterly Arabic-specific LoRA when there's enough data. Honest about quality bands. |
| **The agent breaks itself** | Self-modification creates cycles where today's broken agent corrupts tomorrow's. | Every nightly run is atomic with rollback. Skill / wiki / LoRA changes go to a staging area; promotion to main is gated on tests passing. Daily snapshot to disk; weekly snapshot to cloud storage. |
| **The user loses trust because they can't see what changed** | A self-improving system that doesn't explain itself feels like magic, then like betrayal. | The growth diff (`docs/growth/YYYY-MM-DD.md`) is the contract: every change the agent made yesterday is described in plain language and linked to the actual diff. Reviewable in 60 seconds. |
| **Agent acts confidently when it should ask** | AutoGPT's defining failure: it never asked clarifying questions, burned through API budgets trying to do things it couldn't (installing Python packages in circles, assuming powers it lacked). | Confidence-gated clarification (§4 L6): when model confidence is below threshold *and* the action is consequential (writes a file, runs a network skill, kicks off training, spends cloud money), the agent asks a clarifying question instead of acting. Per-skill thresholds in `SKILL.md` frontmatter. Combined with per-call cost caps (§7.5 #4) so even if the gate fails, a loop costs cents not dollars. |

## 11. Phased build plan

Each phase ends with something the user can use. Nothing here promises more than the layer below it.

### Phase 0 — "Newborn" (target: week 1)
**Goal:** the simplest thing that works + the sleep-time loop scaffold + a clean fork-and-init story, because growth-from-day-1 is the headline promise *and* the seed/instance separation has to be true from day one (not bolted on later).

- Repo skeleton (package side): `pyproject.toml` (uv-managed), `src/personal_llm/` layer dirs, `LICENSE` (Apache-2.0), `README.md`, `docs/GETTING_STARTED.md`, `docs/PRIOR_ART.md`.
- `examples/vault-skeleton/` — the directory the init wizard copies.
- `examples/identities/` — three starter identities (*minimal*, *journaling-companion*, *coding-buddy*), all mentor-mode per §4 L7.
- `personal-llm init [path]` CLI command: hardware probe (RAM, disk, NVIDIA-via-nvidia-smi, Apple Silicon detection), model suggestion ladder, identity choice, PII-redaction wizard, vault scaffolding, `config.yaml` written.
- Ollama installed (documented but not required by the package itself); Qwen 3 8B Instruct Q4_K_M pulled and verified at ≥25 tok/s for the user's own first instance.
- Minimal CLI: `personal-llm chat` (streaming, identity loaded, cross-session recall), `personal-llm ingest <file>` (copies to `<vault>/raw/`, no parsing yet), `personal-llm sleep` (heartbeat growth log), `personal-llm status` (vault validation + live inference health).
- **Recall memory: a JSONL stub** — append per turn, replay last 20 turns across all sessions. Deliberately thin so Phase 0 stays a reviewable foundation; Phase 1 swaps it for the protocol-backed sqlite store (§4 L4).
- Sleep-time loop scaffold: `personal-llm sleep` writes a `<vault>/growth/YYYY-MM-DD.md` with today's session/turn counts. *Even at zero capability* the growth log appears — the contract that real work in Phase 1 will fill out.
- Docker scaffolding (§9): `docker/sandbox/Dockerfile` builds the skill-sandbox base image (used Phase 1+); `docker-compose.yml` at repo root with Phase 1+ services as commented placeholders.
- Lobe-readiness (no commands yet, just structure): vault skeleton includes empty `skills/imported/`, `wiki/imported/`, `data/adapters/imported/` directories so the namespace exists from day 1.
- **Deferred to Phase 1:** the L4 memory swap (protocol + sqlite recall store); smolagents agent loop; MCP client; SKILL.md skill registry with namespace precedence; smoke test in `tests/` (we don't yet know the right shape — first test lands with the first real feature in Phase 1).
- Exit criteria: (a) the user can have a conversation across multiple sessions; the agent remembers the prior session; growth log files appear daily. (b) A stranger cloning the repo can run the wizard and reach their own first chat in under 5 minutes.

### Phase 1 — "Toddler" (target: weeks 2–3)
**Goal:** the agent can read what the user gives it, organize what it knows, and reach out to the world.

- **L4 memory swap** — the Phase 0 JSONL stub is replaced by a `MemoryBackend` protocol with a `SqliteBackend` recall store at `<vault>/data/memory.db`. Cross-session recall folds recent turns into the agent's instructions at session start. Semantic/archival search (`sqlite-vss`) is a later chunk.
- **smolagents agent loop** (§4 L6) replacing the Phase 0 minimal chat loop. Code-first agent reasoning. Confidence-gated clarifying-questions behavior wired in.
- **MCP client** (§4 L6) wired in: `personal-llm mcp add/list/remove`. First server: SearXNG (Docker sidecar) for the `web_search` capability.
- Karpathy LLM Wiki pattern: `raw/` + `wiki/` directories, Obsidian-compatible.
- Ingestion pipeline: PDF / EPUB / HTML / plain text → chunked, embedded, summarized into wiki pages with citations.
- **File-based search** (markdown grep + sqlite-vss for embeddings) over wiki and recall memory. Qdrant *deferred* per §4 L4 upgrade trigger (>10k chunks).
- Skill library v1: `<vault>/skills/<name>/SKILL.md` format (Anthropic Agent Skills standard) + `LocalPythonExecutor` sandbox + Docker sandbox for network-touching skills. The agent can write a SKILL.md skill, test it, save it. Namespace precedence: vault > builtin > imported.
- Sleep-time loop gains real work: ingest new files into wiki, write daily summary, simple skill curation.
- **External learning v1** (single tutor): `web_search` via SearXNG MCP server; Anthropic (Claude) configured as the first tutor via `ANTHROPIC_API_KEY`; self-hosted Hermes on RunPod available for unrestricted-privacy queries; privacy classifier v1 (`private` / `personal` / `public`); PII redaction v1 (display name, primary email, plus user-provided phone/address from the init wizard); audit log v1.
- **Lobe commands v1**: `personal-llm export` / `import` / `inspect` for skill lobes and knowledge lobes. Lobe manifest (`lobe.yaml`) and `.lobe` tarball format frozen. Hash-only verification.
- **First smoke test** in `tests/`: runs `init → chat (tiny model) → ingest → sleep → exit` cleanly on a fresh ephemeral vault.
- Exit criteria: user drops a PDF into `raw/`; overnight, a wiki page exists summarizing it with citations; tomorrow's chat can reference it. **Bonus exit criterion**: user can export a `wiki/topics/<some-topic>/` slice as a `.lobe`, share it, and a fresh vault can import it and the agent cites it correctly.

### Phase 2 — "Child" (target: weeks 4–8)
**Goal:** the agent improves *itself*, not just its knowledge.

- Cloud tutor wired: low-confidence local responses escalate; tutor outputs logged for training data.
- Cloud training infrastructure: `train_job.py` that ships a LoRA training spec to RunPod, polls for completion, downloads the adapter.
- First DPO LoRA from accumulated thumbs (initially trivial — maybe ~100 preference pairs — but the *pipeline* works).
- KL-clamped DPO trainer + replay buffer + quarterly eval against a frozen benchmark.
- Voice: faster-whisper STT + Kokoro TTS, push-to-talk in the web UI.
- Web UI: FastAPI + single HTML page with streaming chat, thumbs buttons, growth-log viewer.
- Skill curation loop in sleep-time: review failure rates, refactor flaky skills.
- Sandbox upgrade: Docker for any network-touching skill.
- **External learning v2** (multi-tutor + self-directed): tutor registry (§7.2) with multiple configured providers; router that picks per-call based on capabilities, privacy class, and budget; self-directed learning sessions added to sleep-time loop (§5 step 6); configurable autonomy mode (`full-autonomy` / `daily-approval` / `per-session`); locked default daily autonomous-learning budget = **$0.50/day** (configurable).
- **Adapter lobes**: training-time `shareable: true/false` tagging on every LoRA job. Adapter lobes added to the export/import command surface. The first publishable adapter lobe (e.g., a domain LoRA trained purely on public Python documentation) ships as a demo.
- Exit criteria: weekly LoRA training runs successfully; the user can show a friend a measurable improvement in tone/quality of responses vs. four weeks earlier. **Bonus exit criterion**: the user has exported at least one adapter lobe and someone else's instance has imported it. **Second bonus**: the agent has spawned at least one self-directed learning goal (without user prompting) and pursued it to a wiki page.

### Phase 3 — "Specializing child" (open-ended)
**Goal:** the agent picks up domains.

- Multi-LoRA router: compose adapters per query (including imported adapter lobes the user has enabled).
- New language lobe (Arabic-specific LoRA from Arabic corpus + accumulated Arabic interactions).
- New skill area on demand (e.g., "learn to code in Rust" → curated reading list + exercise sandbox + curriculum loop).
- Knowledge graph layer (LightRAG or GraphRAG) once wiki exceeds ~1000 pages.
- **Lobe ecosystem maturation**: signing scheme (GPG or sigstore), optional discovery/registry layer, dependency resolution between lobes, automated lobe-quality checks.
- **Agent-to-agent (§7.3)**: public-face persona implementation (designed first, independent of protocol choice), then A2A or MCP protocol adapter, authentication (shared keys or web-of-trust), discovery mechanism, abuse-prevention.
- Optional: LAN sync to a phone client.

## 12. Proposed directory layout

The package/vault separation from §2 is implemented as **two separate directory trees**.

### A. The package (this repo, public, Apache-2.0)

Contains only code, docs, examples, and built-in skills. Zero personal data. This is what gets cloned, forked, and shared.

```
personal-llm/
├── LICENSE                    # Apache-2.0
├── README.md                  # short — points to docs/
├── pyproject.toml             # uv / hatchling
├── docs/
│   ├── ARCHITECTURE.md        # this file
│   ├── GETTING_STARTED.md     # for new forkers: install, init, first chat
│   ├── ROADMAP.md             # phase-by-phase TODO
│   ├── DECISIONS.md           # ADRs as we go
│   └── FORKING.md             # how to customize the seed for your own use
├── src/
│   └── personal_llm/
│       ├── __init__.py
│       ├── cli.py             # `personal-llm` entrypoint (init, chat, ingest, sleep)
│       ├── config.py          # config loading (reads <vault>/config.yaml)
│       ├── vault.py           # vault discovery, layout, validation
│       ├── identity.py        # identity loader (reads <vault>/identity.md)
│       ├── inference/         # L2
│       │   ├── local.py       # Ollama wrapper
│       │   └── tutor.py       # cloud-tutor abstraction
│       ├── memory/            # L4 framework code
│       │   ├── backend.py     # MemoryBackend protocol
│       │   ├── sqlite.py      # SqliteBackend recall store
│       │   ├── wiki.py
│       │   └── vector.py      # sqlite-vss / Qdrant wrapper
│       ├── skills/            # L5 framework code (not the skills themselves)
│       │   ├── registry.py    # merges builtin_skills + <vault>/skills at runtime
│       │   ├── sandbox.py
│       │   └── lifecycle.py
│       ├── builtin_skills/    # skills that ship with the package
│       │   ├── web_search/
│       │   ├── read_file/
│       │   ├── summarize/
│       │   └── ... (small starter set; vault skills extend these)
│       ├── agent/             # L6
│       │   └── loop.py        # smolagents-based loop
│       ├── interface/         # L7
│       │   ├── chat.py        # CLI chat
│       │   └── web/           # FastAPI + static HTML (Phase 1+)
│       ├── personalize/       # L3
│       │   ├── lora_stack.py
│       │   ├── dpo_dataset.py
│       │   └── train_job.py   # ships training to cloud
│       └── sleep/             # the sleep-time loop
│           ├── runner.py
│           ├── ingest.py
│           ├── consolidate.py
│           ├── curate.py
│           └── growth_log.py
├── examples/
│   ├── vault-skeleton/        # what `personal-llm init` copies to create a new vault
│   │   ├── config.example.yaml
│   │   ├── identity.example.md
│   │   ├── raw/.gitkeep
│   │   ├── wiki/index.md      # a starter wiki structure
│   │   ├── skills/.gitkeep
│   │   └── README.md          # a vault-level README explaining the layout
│   ├── identities/            # example personas: minimal, journaling-companion, coding-buddy
│   ├── skills/                # example user-contributed skills people might want
│   └── personas/              # example identity.md patterns
└── tests/                     # repo-level tests (with synthetic vaults as fixtures)
```

### B. The vault (per-user, private, separate directory)

This is *the user's* personal LLM. By default at `~/.personal-llm/vault/`, but `personal-llm init <path>` accepts any directory. Multiple vaults are fine (work / personal / experimental).

```
<vault>/
├── config.yaml                # this user's config: models, paths, cloud caps, hardware
├── identity.md                # this user's persona/identity (user-edited)
├── README.md                  # user can add notes about their vault
├── raw/                       # source material the user drops in (PDFs, EPUBs, articles, transcripts)
├── wiki/                      # Obsidian-compatible vault, agent-maintained
│   ├── index.md
│   ├── daily/                 # YYYY-MM-DD.md
│   ├── topics/
│   └── projects/
├── skills/                    # user-contributed skills (the agent's discoveries + manual additions)
│   ├── <skill-name>/
│   │   ├── skill.py
│   │   ├── manifest.yaml
│   │   ├── tests/
│   │   ├── examples/
│   │   └── CHANGELOG.md
│   └── imported/              # lobes imported from other users (§6); never overrides
│       └── <author>/<lobe-name>/
├── wiki/                      # Obsidian-compatible vault, agent-maintained
│   ├── index.md
│   ├── daily/                 # YYYY-MM-DD.md
│   ├── topics/
│   ├── projects/
│   │   └── learning/          # active learning goals for self-directed research (§7.1)
│   └── imported/              # knowledge lobes imported from others (§6)
│       └── <author>/<lobe-name>/
├── data/                      # runtime state — never edited by hand
│   ├── qdrant/                # vector store on disk
│   ├── memory.db              # recall-memory store (SQLite)
│   ├── adapters/              # downloaded LoRA adapters (user's own)
│   │   └── imported/          # adapter lobes from others (§6); opt-in to load
│   │       └── <author>/<lobe-name>/
│   ├── tutor_logs/            # tutor call payloads (for distillation)
│   ├── audit/                 # YYYY-MM-DD.jsonl — every external call (§7.5)
│   ├── interactions/          # full chat history (input to DPO)
│   ├── training_log.jsonl     # every training job + its shareable/private tag (§6)
│   └── snapshots/             # rollback snapshots
└── growth/                    # daily growth logs the agent writes
    └── YYYY-MM-DD.md
```

The vault is *the user's data*. It can be:
- Kept in a private git repo (recommended — versioned, syncable across machines).
- Backed up wherever the user backs things up.
- Multiple instances (different vaults for different contexts).

The package never modifies its own directory at runtime. Only the vault changes.

### C. How the two connect

At every invocation:
1. CLI resolves the vault path: `--vault <path>` flag → `$PERSONAL_LLM_VAULT` env → `~/.personal-llm/vault/` default.
2. `vault.py` validates the vault has the expected structure (init wizard runs if not).
3. `config.py` loads `<vault>/config.yaml`.
4. Skill registry merges `personal_llm.builtin_skills.*` (from the package) with `<vault>/skills/*` (from the vault). Vault skills override builtin skills on name conflict.
5. Recall-memory DB, Qdrant, adapters, wiki — all read from / written to the vault.

The package is stateless across invocations. Everything stateful lives in the vault. This is the contract that keeps the seed/instance separation clean.

## 13. Forking and onboarding (for the "seed" half of the product)

The seed has to be genuinely usable by a stranger. Concretely:

**The first 5 minutes** (target experience for a new user who clones the repo):

```
git clone https://github.com/<user>/personal-llm.git
cd personal-llm
uv sync                          # install package + deps
personal-llm init                # creates ~/.personal-llm/vault/ from vault-skeleton
                                 # interactive wizard: pick base model, set cloud budget,
                                 # confirm vault path, choose example identity to start from
personal-llm chat                # opens a CLI chat with the newly born agent
```

**The first 5 minutes should produce:** a vault at the chosen path, a working chat with the local model (Qwen 3 8B if hardware permits, smaller fallback otherwise), and a `growth/` directory ready for the first nightly run.

**Onboarding deliverables in the seed:**
- `docs/GETTING_STARTED.md` — the install/init/configure walkthrough, written for someone who has never used the project.
- `docs/FORKING.md` — guidance on what to customize when forking: identity, skills, language defaults, base model, cloud strategy.
- `examples/identities/` — at least three pre-written identity files representing different use cases (*minimal*, *journaling-companion*, *coding-buddy*), all in mentor/companion mode (never romantic — see §4 L7), so users have a starting point rather than a blank `identity.md`.
- `examples/vault-skeleton/` — the exact directory structure `personal-llm init` creates, browsable in the repo so users see what they're getting.
- A working `personal-llm init` wizard that detects hardware (using the same probes as our setup in §7), suggests an appropriate base model, lets the user choose vault location, copies the skeleton, and writes `config.yaml`.
- A "minimal viable vault" test in CI: spin up a fresh vault, run `personal-llm chat` against a tiny model, exit cleanly. This guarantees the seed-to-running-instance path stays working as the codebase evolves.

**Hardware adaptation in the wizard.** Different forkers will have different machines. The wizard probes:
- GPU presence + VRAM → suggests local base model (Qwen 8B / 4B / Phi-4-mini / "CPU only — Phi-4-mini").
- RAM → warns if tight.
- Disk free → warns if tight, suggests external storage for adapters/snapshots.
- Cloud budget → user inputs monthly cap; wizard sets daily/monthly enforcement.

**Updates from upstream.** A user who clones the seed and starts running an instance can pull upstream updates by `git pull` on the package — their vault is untouched. The package version is recorded in the vault so we can run migrations if the layout changes.

**Versioning.** Semantic versioning on the package. Vault layout changes are migrations gated by a `vault_version` in `<vault>/config.yaml`. We never break a user's vault silently.

**Contributions.** Two paths, depending on what's being shared:

1. **Into the seed (PR to this repo).** Generic examples — identity templates, starter skills, vault-skeleton improvements — go to `examples/`. These live in the package and ship with every install.
2. **As a lobe (out-of-tree).** Anything domain-specific or user-curated — a Python coding lobe, a wine-tasting knowledge lobe, a domain LoRA — is shared as a `.lobe` (§6). Lobes are distributed however the author wants: their own GitHub releases, attached to a blog post, sent over email. The user's *own* vault stays private; only the lobe — built deliberately for sharing — moves.

This split matters. The seed should stay small and clean (so a stranger can read the whole thing). Lobes are where the *ecosystem* lives — unlimited, decentralized, and curated by their authors.

## 14. Open questions / deferred decisions

Locked decisions live in their own sections (§6 for lobes, §7 for external learning, §11 for the phased plan). This section lists only what genuinely remains open.

**Genuine research needed:**

- **LoRA privacy bounds (§6).** Locked default rule for now: any byte of user-derived data → `shareable: false`. The literature on membership-inference attacks against small LoRAs is moving; we should do a focused review before Phase 2 lands and decide whether the rule can safely relax. Until then: conservative.

**Genuine decisions deferred to a later phase (where we'll have more information):**

- **Specific cloud GPU provider for training jobs.** Default to RunPod in Phase 2; compare against Vast.ai once we have real training-job duration data.
- **Lobe signing scheme (§6).** v1 is hash-only. Phase 3 decides between GPG, sigstore, or a maintainer-attested model — picked once we know whether import traffic exists.
- **Lobe distribution / discovery layer (§6).** v1 has no central registry. Phase 3 decides whether to build one and which model (GitHub-index, ActivityPub-federated, IPFS, own server). Decision waits for a population of lobes that need discovering.
- **Agent-to-agent protocol (§7.3).** Phase 3+. Watch A2A / MCP-federation; design the public-face persona separation first (independent of protocol).

**Deferred to the user (no current decision needed):**

- **First ingestion corpus.** Phase 1 ships the pipeline (plain text + PDF + EPUB + HTML); the first real feed gets dropped in `raw/` whenever the user wants.
- **Additional tutors past Phase 1.** Phase 1 lands Anthropic + self-hosted Hermes. Phase 2 expands to multi-tutor; the user adds whichever further providers they have keys for (OpenAI, Google, OpenRouter aggregator, etc.).
- **Additional PII to redact past the defaults.** The init wizard prompts for the user's display name, primary email, phone (optional), home address (optional). The user can extend the redaction list anytime (employer, GitHub handle, school, etc.).

## 15. References

The architecture leans on this body of work; full pointers in [memory:key-references].

- **Memory:** MemGPT / Letta — the memory-tier concept (core / recall / archival); evaluated and not adopted as a dependency (see [PRIOR_ART.md](PRIOR_ART.md)). The "Sleep-time Compute" paper (arXiv 2504.13171). Karpathy's "LLM Wiki" gist (April 2026).
- **Self-improving agents:** Voyager (arXiv 2305.16291). AutoSkill (arXiv 2603.01145). SAGE (arXiv 2512.17102). The Awesome-Self-Evolving-Agents survey (EvoAgentX). Lifelong LLM agents survey (TPAMI 2026).
- **Learning from agent transcripts** (cold-start bootstrap; see [LEARNING_FROM_TRANSCRIPTS.md](LEARNING_FROM_TRANSCRIPTS.md)): Trace2Skill (arXiv 2603.25158), EvoSkill (github sentient-agi/EvoSkill), SkillRL (arXiv 2602.08234), ExpeL / Contextual Experience Replay (arXiv 2506.06698), Trajectory-Informed Memory Generation (arXiv 2603.10600), Latent Preference from User Edits, PersonaMem-v2 (arXiv 2512.06688), On-policy Expert Corrections (arXiv 2512.14895), Externalization in LLM Agents review (arXiv 2604.08224).
- **Continual learning:** "Mechanistic Analysis of Catastrophic Forgetting" (arXiv 2601.18699). FedPDPO (arXiv 2603.19741).
- **Base models:** Hermes 4 Technical Report (arXiv 2508.18255). Qwen 3 release notes.
- **Training:** Unsloth, Axolotl, TRL. QLoRA paper.
- **Inference:** llama.cpp, Ollama, vLLM, MLX-LM.
- **Sandboxing:** smolagents, E2B Code Interpreter.
