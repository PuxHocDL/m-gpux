import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
import subprocess
import os
import tomlkit

from m_gpux import __version__
from m_gpux.commands import account
from m_gpux.commands import billing
from m_gpux.commands import hub
from m_gpux.commands import load
from m_gpux.commands import serve
from m_gpux.commands import video
from m_gpux.commands import vision

app = typer.Typer(
    name="m-gpux", 
    help="A powerful, interactive hub and CLI framework for scaling AI workloads on Modal GPUs.\n\nEffortlessly manage multiple Modal profiles, track cross-workspace cloud spend, and spin up A100 notebook servers completely hands-free.",
    short_help="Modal GPU Orchestrator",
    epilog="Made by Pux.",
    no_args_is_help=False
)

console = Console()

app.add_typer(account.app, name="account", help="Configure identities and add multiple Modal profiles.", rich_help_panel="Identity & Finance")
app.add_typer(billing.app, name="billing", help="Track infrastructure costs across workspaces.", rich_help_panel="Identity & Finance")
app.command(name="hub", help="Launch interactive UI to provision Python scripts, Terminals, or Jupyter on GPUs.", rich_help_panel="Compute Engine")(hub.hub_main)
app.add_typer(load.app, name="load", help="Probe a GPU container and display live hardware metrics.", rich_help_panel="Compute Engine")
app.add_typer(serve.app, name="serve", help="Deploy LLMs as OpenAI-compatible APIs with API key auth.", rich_help_panel="Compute Engine")
app.add_typer(video.app, name="video", help="Generate videos from text prompts using LTX-2.3.", rich_help_panel="Compute Engine")
app.add_typer(vision.app, name="vision", help="Train computer vision models on Modal GPUs with local datasets.", rich_help_panel="Compute Engine")

HERO_LOGO = """
[bold cyan] ███╗   ███╗      ██████╗ ██████╗ ██╗   ██╗██╗  ██╗[/bold cyan]
[bold cyan] ████╗ ████║     ██╔════╝ ██╔══██╗██║   ██║╚██╗██╔╝[/bold cyan]
[bold cyan] ██╔████╔██║     ██║  ███╗██████╔╝██║   ██║ ╚███╔╝ [/bold cyan]
[bold cyan] ██║╚██╔╝██║     ██║   ██║██╔═══╝ ██║   ██║ ██╔██╗ [/bold cyan]
[bold cyan] ██║ ╚═╝ ██║     ╚██████╔╝██║     ╚██████╔╝██╔╝ ██╗[/bold cyan]
[bold cyan] ╚═╝     ╚═╝      ╚═════╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝[/bold cyan]
[bold white] Modal GPU Orchestrator[/bold white]
"""


def render_welcome() -> None:
    quick_actions = Table.grid(padding=(0, 2))
    quick_actions.add_row("[bold yellow]m-gpux account add[/bold yellow]", "Configure your Modal token profile")
    quick_actions.add_row("[bold yellow]m-gpux hub[/bold yellow]", "Launch Jupyter, script runner, or web shell")
    quick_actions.add_row("[bold yellow]m-gpux vision train[/bold yellow]", "Train an image classifier from a local dataset")
    quick_actions.add_row("[bold yellow]m-gpux serve deploy[/bold yellow]", "Deploy LLM as OpenAI-compatible API")
    quick_actions.add_row("[bold yellow]m-gpux video generate[/bold yellow]", "Generate video from text prompt (LTX-2.3)")
    quick_actions.add_row("[bold yellow]m-gpux stop[/bold yellow]", "Stop running apps and release GPUs")
    quick_actions.add_row("[bold yellow]m-gpux load probe[/bold yellow]", "Probe a GPU and display hardware metrics")
    quick_actions.add_row("[bold yellow]m-gpux billing usage --all[/bold yellow]", "See total spend across configured accounts")

    console.print(Panel.fit(HERO_LOGO.strip(), border_style="bright_cyan", title="M-GPUX", subtitle=f"v{__version__}"))
    console.print(Panel(quick_actions, title="Quick Actions", border_style="cyan"))
    console.print("[dim]Tip: run m-gpux --help for full command reference.[/dim]\n")

@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        render_welcome()
        
@app.command(rich_help_panel="Utility")
def info():
    """Print framework metadata and system capabilities."""
    console.print(
        Panel(
            f"[bold green]M-GPUX Orchestrator[/bold green]\nVersion: {__version__}\n"
            "Your ultimate utility for interacting with Modal serverless GPU resources.",
            expand=False,
        )
    )


MODAL_CONFIG_PATH = os.path.expanduser("~/.modal.toml")


def _get_all_profiles():
    """Return list of profile names from ~/.modal.toml."""
    if not os.path.exists(MODAL_CONFIG_PATH):
        return []
    with open(MODAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
    return list(doc.keys())


def _scan_apps_across_profiles():
    """Scan all profiles for running m-gpux apps. Returns list of (profile, app_id, description, state)."""
    profiles = _get_all_profiles()
    all_apps = []
    for profile in profiles:
        try:
            result = subprocess.run(
                ["modal", "app", "list", "--env", "main", "--json"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "MODAL_PROFILE": profile},
            )
            if result.returncode != 0:
                continue
            import json
            apps = json.loads(result.stdout) if result.stdout.strip() else []
            for a in apps:
                desc = a.get("Description", a.get("description", ""))
                state = a.get("State", a.get("state", ""))
                app_id = a.get("App ID", a.get("app_id", ""))
                if desc.startswith("m-gpux") and state in ("deployed", "running"):
                    all_apps.append((profile, app_id, desc, state))
        except Exception:
            continue
    return all_apps


@app.command(rich_help_panel="Utility")
def stop(
    all_profiles: bool = typer.Option(False, "--all", help="Scan and stop apps across ALL Modal profiles"),
):
    """Stop running m-gpux apps (Jupyter, shells, LLM servers, etc.)."""

    console.print("[cyan]Scanning for running m-gpux apps...[/cyan]")

    if all_profiles:
        apps = _scan_apps_across_profiles()
    else:
        # Current profile only
        try:
            result = subprocess.run(
                ["modal", "app", "list", "--json"],
                capture_output=True, text=True, timeout=15,
            )
            import json
            raw = json.loads(result.stdout) if result.stdout.strip() else []
            # Get current profile name
            p_result = subprocess.run(
                ["modal", "profile", "current"],
                capture_output=True, text=True, timeout=5,
            )
            current_profile = p_result.stdout.strip() if p_result.returncode == 0 else "unknown"
            apps = []
            for a in raw:
                desc = a.get("Description", a.get("description", ""))
                state = a.get("State", a.get("state", ""))
                app_id = a.get("App ID", a.get("app_id", ""))
                if desc.startswith("m-gpux") and state in ("deployed", "running"):
                    apps.append((current_profile, app_id, desc, state))
        except Exception:
            apps = []

    if not apps:
        console.print("[yellow]No running m-gpux apps found.[/yellow]")
        console.print("[dim]Tip: use --all to scan across all profiles.[/dim]")
        return

    table = Table(title="Running M-GPUX Apps")
    table.add_column("#", style="bold yellow", width=3)
    table.add_column("Profile", style="cyan")
    table.add_column("App ID", style="dim")
    table.add_column("Name", style="white")
    table.add_column("State", style="green")

    for idx, (profile, app_id, desc, state) in enumerate(apps, 1):
        table.add_row(str(idx), profile, app_id[:20], desc, state)

    console.print(table)

    console.print(f"\n  [bold yellow]0[/bold yellow]: Stop ALL ({len(apps)} apps)")
    for idx, (profile, _, desc, _) in enumerate(apps, 1):
        console.print(f"  [bold yellow]{idx}[/bold yellow]: {desc} ({profile})")

    choice = Prompt.ask(
        "Select app to stop (0=all)",
        default="0",
    )

    if choice == "0":
        targets = apps
    else:
        try:
            targets = [apps[int(choice) - 1]]
        except (ValueError, IndexError):
            console.print("[red]Invalid choice.[/red]")
            return

    for profile, app_id, desc, _ in targets:
        console.print(f"  [cyan]Stopping {desc} on {profile}...[/cyan]")
        result = subprocess.run(
            ["modal", "app", "stop", app_id],
            capture_output=True, text=True,
            env={**os.environ, "MODAL_PROFILE": profile},
        )
        if result.returncode == 0:
            console.print(f"  [green]Stopped {desc}[/green]")
        else:
            console.print(f"  [red]Failed: {result.stderr.strip()}[/red]")

    console.print(f"\n[bold green]Done. {len(targets)} app(s) stopped.[/bold green]")

if __name__ == "__main__":
    app()
