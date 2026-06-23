#!/usr/bin/env bash
# Portable launcher for `personal-llm sleep`. Used by the systemd service unit,
# and runnable by hand. Resolves the CLI whether it is installed on PATH or run
# from a source checkout via uv.
#
# Ollama being down is handled inside the command (the loop skips model-backed
# steps), so this script does not gate on it.
set -euo pipefail

# systemd user services start with a minimal PATH; restore the usual bin dirs so
# `personal-llm` / `uv` resolve.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# Preferred: an installed console script.
if command -v personal-llm >/dev/null 2>&1; then
  exec personal-llm sleep
fi

# Fallback: a source checkout run through uv (e.g. exFAT installs that cannot
# use bin-links). PERSONAL_LLM_REPO overrides the auto-detected repo root;
# UV_PROJECT_ENVIRONMENT (if set by the unit) points uv at an ext4 venv.
REPO="${PERSONAL_LLM_REPO:-"$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"}"
exec uv run --project "$REPO" personal-llm sleep
