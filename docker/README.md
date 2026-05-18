# docker/

Container resources for personal-llm. See [../docs/ARCHITECTURE.md §9](../docs/ARCHITECTURE.md) for the hybrid native+Docker design.

## What's here (Phase 0)

- **`sandbox/Dockerfile`** — the skill sandbox base image.
  The agent loop (Phase 1+) builds and runs ephemeral containers from this image when executing skills that touch the network or filesystem outside the vault. Pure-Python side-effect-free skills run in smolagents' `LocalPythonExecutor` on the host instead.

## What lands here later (Phase 1+)

- `searxng/settings.yml` — config for the self-hosted SearXNG search sidecar (the default search backend, per §14 locked decisions).
- `agent/Dockerfile` — optional all-in-one image running the personal-llm agent for forkers who prefer compose-first deployment.

These ship alongside the features that need them.

## Build the sandbox image locally

```bash
docker build -t personal-llm/sandbox:latest -f docker/sandbox/Dockerfile .
docker run --rm personal-llm/sandbox:latest    # should print "personal-llm sandbox ready"
```

The agent will reference this image by tag (`personal-llm/sandbox:latest`) in Phase 1. Until then, this is just infrastructure-in-waiting.
