"""m-gpux CLI entry point.

The CLI is now a thin assembly layer: it builds a Typer app and asks
:func:`m_gpux.core.discover_plugins` to populate it from the plugin registry.

To add a new command, write a plugin (see :mod:`m_gpux.core.plugin`) — there
is no need to modify this file.
"""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from m_gpux import __version__
from m_gpux.core import PluginRegistry, discover_plugins
from m_gpux.core.console import console

app = typer.Typer(
    name="m-gpux",
    help=(
        "A powerful, interactive hub and CLI framework for scaling AI workloads "
        "on Modal GPUs.\n\nEffortlessly manage multiple Modal profiles, track "
        "cross-workspace cloud spend, and spin up GPU sessions hands-free."
    ),
    short_help="Modal GPU Orchestrator",
    epilog="Made by Pux.",
    no_args_is_help=False,
)

# ─── Plugin discovery ─────────────────────────────────────────
registry = PluginRegistry()
discover_plugins(registry)
registry.install(app)


# ─── Welcome screen ───────────────────────────────────────────

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
