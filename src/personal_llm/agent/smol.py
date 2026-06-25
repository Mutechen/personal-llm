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
from personal_llm.memory import MemoryBackend, open_backend
from personal_llm.skills import discover

DEFAULT_MAX_STEPS = 6

# How many prior-session turns to recall into a new chat session's context.
RECALL_TURNS = 20

# How many curated facts to fold into the agent's context (most-durable first).
RECALL_FACTS = 50

# How many query-relevant facts to retrieve per request via semantic search.
RELEVANT_FACTS_K = 8


@dataclass
class AgentRunResult:
    """What an `ask` invocation returns. Kept small so the CLI can format it cheaply."""

    answer: str
    steps_taken: int
    tools_available: list[str]


def format_recall_context(turns: list[dict[str, str]]) -> str:
    """Render prior-session turns as a context block for the agent's instructions.

    Returns an empty string when there are no turns, so callers can pass the
    result straight through to `build_agent` without a guard.
    """
    if not turns:
        return ""
    body = "\n".join(f"{t['role']}: {t['content']}" for t in turns)
    return (
        "## Recent conversation history\n\n"
        "Earlier exchanges with this user, for context. Continue the "
        "relationship naturally; do not repeat these back verbatim.\n\n"
        f"{body}"
    )


def format_facts_context(facts: list[dict[str, str]]) -> str:
    """Render curated facts as a "what I know about you" block for instructions.

    Returns an empty string when there are no facts, so callers can pass the
    result straight through without a guard.
    """
    if not facts:
        return ""
    body = "\n".join(f"- {f['text']}" for f in facts)
    return (
        "## What you know about this user\n\n"
        "Durable facts distilled from prior work, most stable first. Treat them "
        "as background you already know; weave them in naturally when relevant, "
        "don't recite them back.\n\n"
        f"{body}"
    )


def format_relevant_facts(facts: list[dict[str, str]]) -> str:
    """Render query-relevant facts (from semantic search) as a per-request block.

    Returns an empty string when there are no facts, so callers can pass the
    result straight through without a guard.
    """
    if not facts:
        return ""
    body = "\n".join(f"- {f['text']}" for f in facts)
    return (
        "## Facts relevant to this request\n\n"
        "Distilled facts retrieved by meaning for what was just asked. Use them "
        "if relevant; ignore them if not.\n\n"
        f"{body}"
    )


def retrieve_relevant_facts(
    backend: MemoryBackend,
    config: VaultConfig,
    query: str,
    k: int = RELEVANT_FACTS_K,
) -> list[dict]:
    """Semantically search the user's facts for ones bearing on `query`.

    Searches only already-embedded facts (the sleep loop and `recall` keep
    embeddings current), so the agent path stays fast. Returns [] when the
    embedding model is unavailable, so the agent still runs without it.
    """
    from personal_llm.inference.local import LocalModelClient

    ok, _ = LocalModelClient(
        config.embedding_model.name, config.embedding_model.endpoint
    ).health()
    if not ok:
        return []

    from personal_llm.learning.embeddings import semantic_search

    return semantic_search(backend, config, query, k=k, ensure_embedded=False)


def build_memory_context(backend: MemoryBackend, recall_turns: int = 0) -> str:
    """Assemble the agent's memory block: curated facts, then optional recent turns."""
    parts = []
    facts_block = format_facts_context(backend.recall_facts(RECALL_FACTS))
    if facts_block:
        parts.append(facts_block)
    if recall_turns:
        turns_block = format_recall_context(backend.recent_turns(recall_turns))
        if turns_block:
            parts.append(turns_block)
    return "\n\n".join(parts)


def build_agent(
    vault_path: Path,
    config: VaultConfig,
    max_steps: int = DEFAULT_MAX_STEPS,
    memory_context: str | None = None,
) -> CodeAgent:
    """Construct a CodeAgent with the user's identity, model, and skill toolbelt.

    The identity.md is appended to smolagents' default system prompt so the
    model knows who it's helping. (Replacing the default prompt is more invasive
    and risks breaking the code-execution conventions smolagents relies on.)

    `memory_context`, when provided, is appended to the instructions — this is
    how the chat REPL gives the agent cross-session recall. `ask` leaves it
    unset and stays stateless.
    """
    model = OpenAIServerModel(
        model_id=config.local_model.name,
        api_base=f"{config.local_model.endpoint.rstrip('/')}/v1",
        api_key="ollama",  # Ollama ignores this; the client requires a non-empty value.
    )

    skills = discover(vault_path)
    tools = build_smolagents_tools(skills, vault_root=vault_path)

    identity = load_identity(vault_path)
    instructions = f"{identity}\n\n{memory_context}" if memory_context else identity

    agent = CodeAgent(
        tools=tools,
        model=model,
        max_steps=max_steps,
        instructions=instructions,
        verbosity_level=LogLevel.OFF,
    )
    return agent


def ask(
    vault_path: Path,
    config: VaultConfig,
    prompt: str,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> AgentRunResult:
    """Single-shot agent invocation. No conversation state, but it recalls both
    the durable curated facts (identity grounding) and the facts most relevant to
    this prompt (semantic search), so a one-off `ask` already knows the user."""
    backend = open_backend(vault_path)
    durable = build_memory_context(backend)
    relevant = format_relevant_facts(retrieve_relevant_facts(backend, config, prompt))
    memory_context = "\n\n".join(b for b in (durable, relevant) if b) or None
    agent = build_agent(
        vault_path, config, max_steps=max_steps, memory_context=memory_context
    )
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
    extra_context: str = "",
) -> str:
    """Run one chat-REPL turn against an already-built agent.

    Writes the user message and final answer to the memory backend so the
    sleep-time loop sees a complete record. The agent's own ReAct trajectory is
    preserved across turns by `reset=False`; that's what gives the REPL
    in-session continuity without prompt-stuffing.

    `extra_context` (e.g. query-relevant facts the REPL retrieved for this turn)
    is prepended to the prompt the agent sees, but the *stored* user turn is the
    raw message, so transcripts stay clean. Retrieval lives in the caller so this
    handler has no model dependency and stays unit-testable.
    """
    backend.append_turn(session_id, "user", user_message)
    prompt = f"{extra_context}\n\n{user_message}" if extra_context else user_message
    answer = str(agent.run(prompt, reset=False))
    backend.append_turn(session_id, "assistant", answer)
    return answer
