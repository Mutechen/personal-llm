"""smolagents-backed agent (Phase 1).

The Phase 0 `ChatAgent` (loop.py) is still the chat REPL's backend — it streams
raw model output with identity + recent turns prepended, no tools. This module
adds the tool-using path: a smolagents `CodeAgent` that discovers the skill
library and can invoke any builtin skill with a `tool.py`.

Single-shot only for now. Wiring it into the chat REPL is a separate, deliberate
chunk — that's the customer-facing piece that gates the next PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from smolagents import CodeAgent, OpenAIServerModel

from personal_llm.agent.tools import build_smolagents_tools
from personal_llm.config import VaultConfig
from personal_llm.identity import load as load_identity
from personal_llm.skills import discover

DEFAULT_MAX_STEPS = 6


@dataclass
class AgentRunResult:
    """What an `ask` invocation returns. Kept small so the CLI can format it cheaply."""

    answer: str
    steps_taken: int
    tools_available: list[str]


def build_agent(
    vault_path: Path,
    config: VaultConfig,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> CodeAgent:
    """Construct a CodeAgent with the user's identity, model, and skill toolbelt.

    The identity.md is appended to smolagents' default system prompt so the
    model knows who it's helping. (Replacing the default prompt is more invasive
    and risks breaking the code-execution conventions smolagents relies on.)
    """
    model = OpenAIServerModel(
        model_id=config.local_model.name,
        api_base=f"{config.local_model.endpoint.rstrip('/')}/v1",
        api_key="ollama",  # Ollama ignores this; the client requires a non-empty value.
    )

    skills = discover(vault_path)
    tools = build_smolagents_tools(skills, vault_root=vault_path)

    identity = load_identity(vault_path)

    agent = CodeAgent(
        tools=tools,
        model=model,
        max_steps=max_steps,
        instructions=identity,
    )
    return agent


def ask(
    vault_path: Path,
    config: VaultConfig,
    prompt: str,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> AgentRunResult:
    """Single-shot agent invocation. Builds a fresh agent each call (no session state)."""
    agent = build_agent(vault_path, config, max_steps=max_steps)
    answer = agent.run(prompt)
    return AgentRunResult(
        answer=str(answer),
        steps_taken=getattr(agent, "step_number", 0),
        tools_available=[t.name for t in agent.tools.values()] if hasattr(agent, "tools") else [],
    )
