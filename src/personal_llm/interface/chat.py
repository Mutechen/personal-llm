"""CLI chat REPL.

Builds a smolagents `CodeAgent` once per session (see `agent.smol.build_agent`)
and routes each user turn through `chat_turn`. The agent persists across turns
so smolagents' ReAct trajectory carries in-session continuity; turns are written
to the memory backend so the sleep-time loop sees a record.

Cross-session continuity: at session start, recent turns from the backend are
formatted and folded into the agent's instructions, so the agent picks up where
prior sessions left off. In-session continuity is the ReAct trajectory.

Runtime overrides (/private, /tutor=X, /no-search, /local) are parsed but still
no-ops in Phase 1; they'll wire up alongside the tutor router.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from personal_llm.agent.smol import RECALL_TURNS, build_agent, chat_turn, format_recall_context
from personal_llm.config import VaultConfig
from personal_llm.inference.local import LocalModelClient
from personal_llm.memory import open_backend

console = Console()

QUIT_COMMANDS = {"/quit", "/exit", "/q"}
HELP_COMMAND = "/help"
RUNTIME_OVERRIDE_PREFIXES = ("/private", "/local", "/no-search", "/tutor=")


def run(vault_path: Path, config: VaultConfig) -> None:
    """Start an interactive chat session."""
    client = LocalModelClient(
        model_name=config.local_model.name,
        endpoint=config.local_model.endpoint,
    )
    ok, msg = client.health()
    if not ok:
        console.print(f"[red]Inference health check failed:[/red] {msg}")
        console.print(
            "\n[dim]Hint: install Ollama from https://ollama.com and pull the model:[/dim]"
        )
        console.print(f"[bold]  ollama pull {config.local_model.name}[/bold]\n")
        return

    backend = open_backend(vault_path)
    session_id = backend.new_session_id()
    recalled = backend.recent_turns(RECALL_TURNS)
    agent = build_agent(
        vault_path, config, memory_context=format_recall_context(recalled)
    )
    tool_names = [t.name for t in agent.tools.values()] if hasattr(agent, "tools") else []

    _print_banner(config, vault_path, tool_names, len(recalled))

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]you[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye.[/dim]")
            return

        if not user_input:
            continue
        if user_input.lower() in QUIT_COMMANDS:
            console.print("[dim]Bye.[/dim]")
            return
        if user_input == HELP_COMMAND:
            _print_help()
            continue

        for prefix in RUNTIME_OVERRIDE_PREFIXES:
            if user_input.startswith(prefix):
                console.print(
                    f"[dim]({prefix} parsed; runtime overrides land alongside the tutor router)[/dim]"
                )
                user_input = user_input[len(prefix):].lstrip()
                break

        if not user_input:
            continue

        console.print()
        try:
            with console.status("[dim]thinking…[/dim]", spinner="dots"):
                answer = chat_turn(agent, backend, session_id, user_input)
        except KeyboardInterrupt:
            console.print("[dim](interrupted)[/dim]\n")
            continue
        except Exception as e:
            console.print(f"[red]agent error:[/red] {e}\n")
            continue

        console.print("[bold green]agent[/bold green]")
        console.print(Markdown(answer))
        console.print()


def _print_banner(
    config: VaultConfig, vault_path: Path, tool_names: list[str], recalled: int
) -> None:
    console.print()
    console.rule("[bold]personal-llm[/bold]")
    console.print(f"[dim]vault:[/dim] {vault_path}")
    console.print(f"[dim]model:[/dim] {config.local_model.name} @ {config.local_model.endpoint}")
    console.print(f"[dim]tools:[/dim] {', '.join(tool_names) if tool_names else '(none)'}")
    if recalled:
        console.print(f"[dim]memory:[/dim] {recalled} prior turn(s) recalled")
    console.print(f"[dim]help:[/dim]  {HELP_COMMAND}    [dim]quit:[/dim] /quit")
    console.rule()
    console.print()


def _print_help() -> None:
    console.print(
        Markdown(
            """
**Commands**

- `/quit` (or `/exit`, `/q`) — leave the chat
- `/help` — this message
- `/private <msg>` — (Phase 1+) force a turn to stay local-only
- `/local <msg>` — (Phase 1+) same as `/private`
- `/no-search <msg>` — (Phase 1+) forbid web search for this turn
- `/tutor=<name> <msg>` — (Phase 1+) force a specific tutor

**Memory**

The agent remembers earlier turns within this session (smolagents trajectory)
and recalls recent turns from previous sessions at startup.

The override prefixes are parsed but not yet enforced.
"""
        )
    )
