"""Vault discovery, scaffolding, and validation.

A vault is the per-user directory that holds *your* personal-llm state:
identity, raw sources, wiki, skills, data, growth logs. The package never
writes to itself; only the vault changes at runtime.

Discovery order:
    1. --vault <path>           (CLI flag, highest priority)
    2. $PERSONAL_LLM_VAULT      (env var)
    3. ~/.personal-llm/vault    (default)
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

VAULT_VERSION = 1
DEFAULT_VAULT_PATH = Path.home() / ".personal-llm" / "vault"
ENV_VAR = "PERSONAL_LLM_VAULT"
CONFIG_FILENAME = "config.yaml"
IDENTITY_FILENAME = "identity.md"

# Directories that every vault must contain. Created by the init wizard.
REQUIRED_DIRS = (
    "raw",
    "wiki",
    "wiki/daily",
    "wiki/topics",
    "wiki/projects",
    "wiki/projects/learning",
    "wiki/imported",
    "skills",
    "skills/imported",
    "data",
    "data/letta",
    "data/qdrant",
    "data/adapters",
    "data/adapters/imported",
    "data/tutor_logs",
    "data/audit",
    "data/interactions",
    "data/snapshots",
    "growth",
)


def resolve_vault_path(cli_flag: str | None = None) -> Path:
    """Resolve which vault directory to use, in priority order."""
    if cli_flag:
        return Path(cli_flag).expanduser().resolve()
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_VAULT_PATH


def exists(vault_path: Path) -> bool:
    """A vault exists if its config.yaml is present."""
    return (vault_path / CONFIG_FILENAME).is_file()


def validate(vault_path: Path) -> list[str]:
    """Return a list of problems with the vault. Empty list means valid."""
    problems: list[str] = []
    if not vault_path.is_dir():
        return [f"Vault directory does not exist: {vault_path}"]
    if not (vault_path / CONFIG_FILENAME).is_file():
        problems.append(f"Missing {CONFIG_FILENAME}")
    if not (vault_path / IDENTITY_FILENAME).is_file():
        problems.append(f"Missing {IDENTITY_FILENAME}")
    for d in REQUIRED_DIRS:
        if not (vault_path / d).is_dir():
            problems.append(f"Missing directory: {d}/")
    return problems


def scaffold(vault_path: Path, identity_source: Path | None = None) -> None:
    """Create a new vault from the bundled skeleton.

    Copies examples/vault-skeleton/ into vault_path. If identity_source is given,
    its contents become identity.md (otherwise the example identity is used).
    """
    vault_path.mkdir(parents=True, exist_ok=True)

    skeleton = _skeleton_dir()
    if not skeleton.is_dir():
        raise FileNotFoundError(
            f"Vault skeleton not found at {skeleton}. "
            "If you cloned this repo, ensure examples/vault-skeleton/ is present."
        )

    for src in skeleton.rglob("*"):
        rel = src.relative_to(skeleton)
        dst = vault_path / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            # Don't clobber existing files (re-runnable init).
            if not dst.exists():
                shutil.copy2(src, dst)

    # Required directories must exist even if the skeleton only had a .gitkeep.
    for d in REQUIRED_DIRS:
        (vault_path / d).mkdir(parents=True, exist_ok=True)

    if identity_source is not None and identity_source.is_file():
        shutil.copy2(identity_source, vault_path / IDENTITY_FILENAME)

    # Default placement of identity.md if the skeleton shipped identity.example.md.
    example = vault_path / "identity.example.md"
    target = vault_path / IDENTITY_FILENAME
    if example.is_file() and not target.is_file():
        shutil.copy2(example, target)


def personalize_identity(vault_path: Path, display_name: str) -> bool:
    """Replace the `(your name)` placeholder in identity.md with the user's name.

    Run once during `init`, after the skeleton is copied and the user has supplied
    a display name. Idempotent: if the placeholder is already gone (user edited
    the file, or a prior init already substituted), this is a no-op.

    This is the init wizard threading user-supplied input through during
    scaffolding — *not* the runtime agent rewriting its own system prompt.
    The hard rule "agent never writes identity.md" still holds at chat/sleep time.
    """
    if not display_name:
        return False
    path = vault_path / IDENTITY_FILENAME
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    placeholder = "(your name)"
    if placeholder not in text:
        return False
    path.write_text(text.replace(placeholder, display_name), encoding="utf-8")
    return True


def _skeleton_dir() -> Path:
    """Locate examples/vault-skeleton/ relative to this package.

    Looks in two places:
      - <repo>/examples/vault-skeleton/  (when running from source)
      - <pkg>/_examples/vault-skeleton/  (when installed via shared-data)
    """
    here = Path(__file__).resolve()
    # From source layout: src/personal_llm/vault.py -> repo root is parents[2]
    repo_root = here.parents[2]
    candidate = repo_root / "examples" / "vault-skeleton"
    if candidate.is_dir():
        return candidate
    # Installed layout fallback.
    return here.parent / "_examples" / "vault-skeleton"
