# personal-llm

A personal LLM that grows with you. Open-source seed for your own personal AI.

**Status:** Phase 0 ("newborn") — early scaffolding.

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
personal-llm chat                    # opens a chat in your terminal
```

For the install/init/configure walkthrough, see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

## Deployment topology

personal-llm runs as a **hybrid** of native and containerized components — native for what you touch every minute (CLI, chat REPL, Ollama, sleep cron) and Docker for what needs isolation or service-shape (skill sandbox, SearXNG, Qdrant, MCP servers). A `docker-compose.yml` at the repo root is the optional one-command path for forkers who prefer compose. See [ARCHITECTURE.md §9](docs/ARCHITECTURE.md) for the full split.

## Design

The whole architecture in one diagram, layered:

```
L7  Identity & Interface       CLI · web · voice · identity.md
L6  Agent loop & orchestrator  smolagents + MCP client
L5  Skill library              Agent Skills (SKILL.md) standard
L4  Memory & knowledge base    Letta state · Karpathy LLM Wiki
L3  Personalization layer      LoRA stack · DPO · KL-clamped
L2  Inference runtime          Ollama · llama.cpp · (cloud tutors)
L1  Base model ("genes")       Qwen 3 8B local · Hermes 36B (cloud)

Sleep-time meta-loop: ingest · consolidate · curate · learn · pre-compute
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design (12 sections, ~10k words). See [docs/PRIOR_ART.md](docs/PRIOR_ART.md) for what we learned from earlier attempts (Khoj, Letta, Voyager, AutoGPT failures, etc.) and which open standards we adopt.

## Open standards adopted

- **[Anthropic Agent Skills (`SKILL.md`)](https://agentskills.io/)** — our skill format. Cross-tool compatible with 32+ agent tools.
- **[Model Context Protocol (MCP)](https://modelcontextprotocol.io/)** — our external-tool plumbing. Inherit thousands of community servers.
- **[HuggingFace PEFT (`adapter_config.json`)](https://huggingface.co/docs/peft/)** — our adapter format. Cross-tool loadable.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Contributing

The seed should stay small and clean. Two contribution paths:

1. **Into the seed (PR here)** — generic examples (identity templates, starter skills, vault-skeleton improvements) go to `examples/`.
2. **As a lobe (out-of-tree)** — anything domain-specific or user-curated ships as a `.lobe` archive (see [docs/ARCHITECTURE.md §6](docs/ARCHITECTURE.md)). Lobes are distributed however you choose; the personal-llm community has no central registry by design.

Your own personal vault stays private. The seed never holds personal data.
