"""CLI chat REPL.

A streaming terminal chat. The runtime overrides (/private, /tutor=X, /no-search)
are stubbed for Phase 0 — they parse but the routing isn't wired up yet.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

from personal_llm.agent.loop import ChatAgent
from personal_llm.config import VaultConfig

console = Console()

QUIT_COMMANDS = {"/quit", "/exit", "/q"}
HELP_COMMAND = "/help"
RUNTIME_OVERRIDE_PREFIXES = ("/private", "/local", "/no-search", "/tutor=")


def run(vault_path: Path, config: VaultConfig) -> None:
    """Start an interactive chat session."""
    agent = ChatAgent(vault_path, config)

    ok, msg = agent.health()
    if not ok:
        console.print(f"[red]Inference health check failed:[/red] {msg}")
        console.print(
            "\n[dim]Hint: install Ollama from https://ollama.com and pull the model:[/dim]"
        )
        console.print(f"[bold]  ollama pull {config.local_model.name}[/bold]\n")
        return

    _print_banner(config, vault_path)

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

        # Phase 0: parse runtime overrides but don't yet apply them.
        for prefix in RUNTIME_OVERRIDE_PREFIXES:
            if user_input.startswith(prefix):
                console.print(
                    f"[dim]({prefix} parsed; runtime overrides land in Phase 1)[/dim]"
                )
                user_input = user_input[len(prefix):].lstrip()
                break

        if not user_input:
            continue

        console.print()
        console.print("[bold green]agent[/bold green]")
        buf: list[str] = []
        try:
            for chunk in agent.chat_turn(user_input):
                console.print(chunk, end="", soft_wrap=True, highlight=False)
                buf.append(chunk)
        except KeyboardInterrupt:
            console.print("\n[dim](interrupted)[/dim]")
        console.print()
        console.print()


def _print_banner(config: VaultConfig, vault_path: Path) -> None:
    console.print()
    console.rule("[bold]personal-llm[/bold]")
    console.print(f"[dim]vault:[/dim] {vault_path}")
    console.print(f"[dim]model:[/dim] {config.local_model.name} @ {config.local_model.endpoint}")
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

In Phase 0 the override prefixes are stripped but not yet enforced.
"""
        )
    )
