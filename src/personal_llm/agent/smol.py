"""smolagents-backed agent (Phase 1).

Backs both the single-shot `personal-llm ask` and the interactive `personal-llm
chat` REPL. The agent discovers the skill library at construction time and
exposes any builtin skill with a `tool.py` as a smolagents tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from smolagents import CodeAgent, OpenAIServerModel
from smolagents.monitoring import LogLevel

from personal_llm.agent.tools import build_smolagents_tools
from personal_llm.config import VaultConfig
from personal_llm.identity import load as load_identity
from personal_llm.memory import MemoryBackend
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
        verbosity_level=LogLevel.OFF,
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


def chat_turn(
    agent: CodeAgent,
    backend: MemoryBackend,
    session_id: str,
    user_message: str,
) -> str:
    """Run one chat-REPL turn against an already-built agent.

    Writes the user message and final answer to the memory backend so the
    sleep-time loop sees a complete record. The agent's own ReAct trajectory is
    preserved across turns by `reset=False`; that's what gives the REPL
    in-session continuity without prompt-stuffing.
    """
    backend.append_turn(session_id, "user", user_message)
    answer = str(agent.run(user_message, reset=False))
    backend.append_turn(session_id, "assistant", answer)
    return answer
