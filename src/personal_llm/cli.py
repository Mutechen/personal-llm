"""personal-llm CLI entry point.

Phase 0 commands:
    personal-llm init [PATH]    — scaffold a new vault from the bundled skeleton.
    personal-llm chat           — open an interactive chat with the local model.
    personal-llm sleep          — run one sleep-time cycle (writes today's growth log).
    personal-llm ingest FILE    — copy a file into the vault's raw/ for later ingestion.
    personal-llm status         — health check + vault summary.
    personal-llm version        — print version.

Phase 1+ adds: mcp (add/list/remove), audit (--since), export/import/inspect.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from personal_llm import __version__, config as config_mod, vault as vault_mod

app = typer.Typer(
    name="personal-llm",
    help="A personal LLM that grows with you. See docs/ARCHITECTURE.md for the design.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


@app.callback()
def main() -> None:
    """personal-llm — your own personal LLM."""


@app.command()
def version() -> None:
    """Print version and exit."""
    console.print(__version__)


# --------------------------------------------------------------------------- init


@app.command()
def init(
    path: Annotated[
        Optional[str],
        typer.Argument(help="Where to scaffold the vault. Default: ~/.personal-llm/vault"),
    ] = None,
) -> None:
    """Scaffold a new vault and write its config."""
    vault_path = vault_mod.resolve_vault_path(path)
    console.print()
    console.rule("[bold]personal-llm init[/bold]")
    console.print(f"[dim]Target vault:[/dim] [bold]{vault_path}[/bold]\n")

    if vault_mod.exists(vault_path):
        console.print(
            f"[yellow]A vault already exists at {vault_path}.[/yellow] "
            "Init will fill in any missing pieces but never overwrite your config or identity."
        )
        if not Confirm.ask("Continue?", default=True):
            raise typer.Exit(0)

    # 1) Hardware probe.
    hw = _probe_hardware()
    _print_hw(hw)

    # 2) Base model suggestion.
    suggested_model = _suggest_model(hw)
    console.print(f"\n[dim]Suggested local base model:[/dim] [bold]{suggested_model}[/bold]")
    chosen_model = Prompt.ask("Local base model", default=suggested_model)

    # 3) Monthly cloud budget.
    budget_str = Prompt.ask("Monthly cloud budget (USD)", default="100")
    try:
        budget = float(budget_str)
    except ValueError:
        budget = 100.0

    # 4) Pick a starter identity.
    identities = _list_example_identities()
    if identities:
        console.print("\n[dim]Starter identities:[/dim]")
        for i, (name, _path) in enumerate(identities, 1):
            console.print(f"  [bold]{i}[/bold]. {name}")
        choice = Prompt.ask(
            "Pick a starter identity by number (or 'skip' for a blank one)",
            default="1",
        )
        identity_source: Path | None = None
        if choice.lower() != "skip":
            try:
                idx = int(choice) - 1
                identity_source = identities[idx][1]
            except (ValueError, IndexError):
                console.print("[dim]Invalid choice, using minimal identity.[/dim]")
                identity_source = identities[0][1]
    else:
        identity_source = None

    # 5) PII redaction list (mandatory minimum: name + email; phone/address optional).
    console.print(
        "\n[dim]These are redacted before any external API call (Phase 1+):[/dim]"
    )
    display_name = Prompt.ask("Your display name", default="")
    primary_email = Prompt.ask("Your primary email", default="")
    phone = Prompt.ask("Your phone (optional, press Enter to skip)", default="")
    home_address = Prompt.ask("Your home address (optional)", default="")

    # 6) Scaffold the vault.
    console.print()
    console.print(f"[bold]Scaffolding vault at[/bold] {vault_path} ...")
    vault_mod.scaffold(vault_path, identity_source=identity_source)

    # 7) Write the config.
    cfg = config_mod.VaultConfig()
    cfg.local_model.name = chosen_model
    cfg.cloud.monthly_budget_usd = budget
    cfg.redaction.display_name = display_name
    cfg.redaction.primary_email = primary_email
    cfg.redaction.phone = phone
    cfg.redaction.home_address = home_address
    config_mod.save(vault_path, cfg)

    # 7b) Thread the display name into identity.md's placeholder so the agent
    # greets the user by name out of the box. No-op if the user has already
    # edited the file (re-runnable init).
    if display_name:
        vault_mod.personalize_identity(vault_path, display_name)

    # 8) Done.
    console.print("\n[green]Vault created.[/green]\n")
    _print_next_steps(vault_path, chosen_model)


# --------------------------------------------------------------------------- chat


@app.command()
def chat(
    vault: Annotated[
        Optional[str],
        typer.Option("--vault", "-v", help="Vault path override."),
    ] = None,
) -> None:
    """Open an interactive chat session."""
    vault_path = vault_mod.resolve_vault_path(vault)
    if not vault_mod.exists(vault_path):
        console.print(
            f"[red]No vault at {vault_path}.[/red] Run [bold]personal-llm init[/bold] first."
        )
        raise typer.Exit(1)

    cfg = config_mod.load(vault_path)

    # Lazy import so init/version don't pull in rich-prompt + ollama unnecessarily.
    from personal_llm.interface.chat import run as run_chat

    run_chat(vault_path, cfg)


# --------------------------------------------------------------------------- sleep


@app.command()
def sleep(
    vault: Annotated[
        Optional[str],
        typer.Option("--vault", "-v", help="Vault path override."),
    ] = None,
) -> None:
    """Run one sleep-time cycle and write today's growth log."""
    vault_path = vault_mod.resolve_vault_path(vault)
    if not vault_mod.exists(vault_path):
        console.print(f"[red]No vault at {vault_path}.[/red]")
        raise typer.Exit(1)

    from personal_llm.sleep.runner import run_once

    growth_path = run_once(vault_path)
    console.print(f"[green]Wrote[/green] {growth_path}")


# --------------------------------------------------------------------------- ingest


@app.command()
def ingest(
    file: Annotated[Path, typer.Argument(help="File to drop into the vault's raw/.")],
    vault: Annotated[
        Optional[str],
        typer.Option("--vault", "-v", help="Vault path override."),
    ] = None,
) -> None:
    """Copy a file into the vault's raw/ directory (Phase 0: no parsing yet)."""
    if not file.is_file():
        console.print(f"[red]Not a file:[/red] {file}")
        raise typer.Exit(1)

    vault_path = vault_mod.resolve_vault_path(vault)
    if not vault_mod.exists(vault_path):
        console.print(f"[red]No vault at {vault_path}.[/red]")
        raise typer.Exit(1)

    raw = vault_path / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    dest = raw / file.name
    if dest.exists():
        console.print(f"[yellow]Already in raw/:[/yellow] {dest.name}")
        raise typer.Exit(0)

    shutil.copy2(file, dest)
    console.print(f"[green]Ingested[/green] {file.name} → {dest}")
    console.print(
        "[dim](Phase 0 just stores the file. Phase 1 parses, embeds, and writes wiki pages.)[/dim]"
    )


# --------------------------------------------------------------------------- status


@app.command()
def status(
    vault: Annotated[
        Optional[str],
        typer.Option("--vault", "-v", help="Vault path override."),
    ] = None,
) -> None:
    """Show vault location, config summary, and inference health."""
    vault_path = vault_mod.resolve_vault_path(vault)

    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column("key", style="dim")
    table.add_column("value")

    table.add_row("version", __version__)
    table.add_row("vault path", str(vault_path))
    table.add_row("vault exists", "yes" if vault_mod.exists(vault_path) else "no")

    if vault_mod.exists(vault_path):
        cfg = config_mod.load(vault_path)
        table.add_row("local model", f"{cfg.local_model.name} @ {cfg.local_model.endpoint}")
        table.add_row("monthly cap", f"${cfg.cloud.monthly_budget_usd:.2f}")
        table.add_row("autonomy", cfg.cloud.autonomy_mode)

        problems = vault_mod.validate(vault_path)
        if problems:
            table.add_row("validation", "[yellow]" + "; ".join(problems) + "[/yellow]")
        else:
            table.add_row("validation", "[green]ok[/green]")

        # Inference health check (lazy import).
        try:
            from personal_llm.inference.local import LocalModelClient

            client = LocalModelClient(cfg.local_model.name, cfg.local_model.endpoint)
            ok, msg = client.health()
            table.add_row("inference", "[green]ok[/green]" if ok else f"[red]{msg}[/red]")
        except Exception as e:
            table.add_row("inference", f"[red]{e}[/red]")

    console.print(table)


# --------------------------------------------------------------------------- helpers


def _probe_hardware() -> dict:
    """Best-effort hardware probe. Returns dict with whatever we found."""
    import psutil

    info: dict = {
        "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "disk_free_gb": None,
        "gpu_vendor": None,
        "gpu_vram_gb": None,
    }

    home = Path.home()
    info["disk_free_gb"] = round(shutil.disk_usage(home).free / (1024**3), 1)

    # NVIDIA via nvidia-smi.
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        import subprocess

        try:
            out = subprocess.run(
                [nvidia_smi, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if out.returncode == 0 and out.stdout.strip():
                first_line = out.stdout.strip().splitlines()[0]
                info["gpu_vendor"] = "nvidia"
                info["gpu_vram_gb"] = round(int(first_line) / 1024, 1)
        except Exception:
            pass

    if info["gpu_vendor"] is None and sys.platform == "darwin":
        # Treat Apple Silicon as having unified memory; suggest based on RAM.
        info["gpu_vendor"] = "apple-silicon"
        info["gpu_vram_gb"] = info["ram_total_gb"]

    return info


def _print_hw(hw: dict) -> None:
    table = Table(title="Hardware probe", show_header=False, box=None, pad_edge=False)
    table.add_column(style="dim")
    table.add_column()
    table.add_row("RAM", f"{hw['ram_total_gb']} GB")
    table.add_row("Disk free in $HOME", f"{hw['disk_free_gb']} GB")
    if hw["gpu_vendor"]:
        table.add_row("GPU", f"{hw['gpu_vendor']} ({hw['gpu_vram_gb']} GB VRAM)")
    else:
        table.add_row("GPU", "[dim]not detected (CPU only)[/dim]")
    console.print(table)


def _suggest_model(hw: dict) -> str:
    """Suggest an Ollama model name based on the hardware probe.

    Aligns with docs/ARCHITECTURE.md §4 L1 — fall-back ladder.
    Tags verified against the Ollama registry as of 2026-05.
    """
    vram = hw.get("gpu_vram_gb") or 0
    if vram >= 16:
        return "qwen3:14b"
    if vram >= 5:
        return "qwen3:8b"
    # CPU-only or weak GPU.
    return "phi3:mini"


def _list_example_identities() -> list[tuple[str, Path]]:
    """Find bundled example identities. Sorted alphabetically; minimal first by convention."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "examples" / "identities",  # source layout
        here.parent / "_examples" / "identities",  # installed layout
    ]
    for d in candidates:
        if d.is_dir():
            return sorted(((p.stem, p) for p in d.glob("*.md")), key=lambda t: t[0])
    return []


def _print_next_steps(vault_path: Path, model: str) -> None:
    console.print("[bold]Next:[/bold]")
    console.print(
        f"  1. Install Ollama (https://ollama.com) and pull your model:\n"
        f"     [bold]ollama pull {model}[/bold]"
    )
    console.print(f"  2. Edit your identity: [bold]{vault_path / 'identity.md'}[/bold]")
    console.print("  3. Start chatting: [bold]personal-llm chat[/bold]")
    console.print("  4. (optional) Schedule the sleep-time loop via cron:")
    console.print("     [dim]0 3 * * *  personal-llm sleep[/dim]")
    console.print()
