"""Vault config loading and writing.

The config.yaml inside a vault drives runtime behavior: which base model,
where it lives, cloud budget, autonomy mode. The package itself is stateless.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from personal_llm.vault import CONFIG_FILENAME, VAULT_VERSION


class LocalModelConfig(BaseModel):
    """Configuration for the always-on local base model."""

    backend: Literal["ollama"] = "ollama"
    name: str = "qwen3:8b"
    endpoint: str = "http://localhost:11434"


class EmbeddingModelConfig(BaseModel):
    """The local model used to embed text for semantic search.

    Separate from the chat model: embeddings want a small, fast, dedicated model.
    Default `snowflake-arctic-embed2` (1024-dim, multilingual) — so non-English
    sources (e.g. Arabic books) are searchable AND a query in one language can
    retrieve content in another (validated: 5/5 cross-lingual EN/AR/FR, 0% NaN).
    bge-m3 has comparable quality but an intermittent NaN bug on Ollama;
    `nomic-embed-text` is lighter but English-only. Changing this re-embeds on
    the next pass (the embedding store keys on the model name).
    """

    backend: Literal["ollama"] = "ollama"
    name: str = "snowflake-arctic-embed2"
    endpoint: str = "http://localhost:11434"


class CloudConfig(BaseModel):
    """Cloud spending caps and tutor registry placeholders.

    Phase 0: tutor registry is empty. Phase 1+ adds entries here.
    """

    monthly_budget_usd: float = 100.0
    daily_autonomous_learning_budget_usd: float = 0.50
    autonomy_mode: Literal["full-autonomy", "daily-approval", "per-session"] = (
        "daily-approval"
    )
    tutors: list[dict] = Field(default_factory=list)


class RedactionConfig(BaseModel):
    """PII redaction list — applied before any external call.

    Populated by the init wizard. Users can extend in config.yaml directly.
    """

    display_name: str = ""
    primary_email: str = ""
    phone: str = ""
    home_address: str = ""
    extra: list[str] = Field(default_factory=list)


class SleepConfig(BaseModel):
    """What the nightly sleep-time loop does. See ARCHITECTURE.md §5.

    Grading and dedup only ever touch facts already in the vault, so they run by
    default. Learning from transcripts reaches into the user's agent history, so
    it stays opt-in — the loop never reads `~/.claude` unless this is enabled.
    """

    learn_from_transcripts: bool = False
    transcript_source: str | None = None  # defaults to ~/.claude/projects when enabled
    llm_grading: bool = True  # run G2/G3 + fact embeddings in sleep (needs local models)


class VaultConfig(BaseModel):
    """Top-level vault config schema."""

    vault_version: int = VAULT_VERSION
    local_model: LocalModelConfig = Field(default_factory=LocalModelConfig)
    embedding_model: EmbeddingModelConfig = Field(default_factory=EmbeddingModelConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    redaction: RedactionConfig = Field(default_factory=RedactionConfig)
    sleep: SleepConfig = Field(default_factory=SleepConfig)
    mcp_servers: list[dict] = Field(default_factory=list)


def load(vault_path: Path) -> VaultConfig:
    """Load and validate the config.yaml at the vault root."""
    path = vault_path / CONFIG_FILENAME
    if not path.is_file():
        raise FileNotFoundError(
            f"No {CONFIG_FILENAME} in {vault_path}. Run `personal-llm init` first."
        )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return VaultConfig.model_validate(data)


def save(vault_path: Path, config: VaultConfig) -> None:
    """Write the config.yaml back to the vault."""
    path = vault_path / CONFIG_FILENAME
    data = config.model_dump(mode="json")
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
