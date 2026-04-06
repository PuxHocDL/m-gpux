import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from m_gpux import __version__
from m_gpux.commands import account
from m_gpux.commands import billing
from m_gpux.commands import hub
from m_gpux.commands import load

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

if __name__ == "__main__":
    app()
