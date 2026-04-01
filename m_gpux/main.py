import typer
from rich.console import Console
from rich.panel import Panel

from m_gpux.commands import account
from m_gpux.commands import billing
from m_gpux.commands import hub

app = typer.Typer(
    name="m-gpux", 
    help="A powerful hub and CLI for managing Modal GPUs, Accounts, and Workspaces",
    no_args_is_help=False
)

console = Console()

app.add_typer(account.app, name="account", help="Manage multi-profile Modal accounts")
app.add_typer(billing.app, name="billing", help="View usage and billing details")
app.command(name="hub", help="Interactive GPU hub to start terminals or notebooks")(hub.hub_main)

UIT_LOGO = """
[bold blue]  _   _  _____  _______ [/bold blue]
[bold blue] | | | ||_   _||__   __|[/bold blue]
[bold blue] | | | |  | |     | |   [/bold blue]
[bold blue] | |_| | _| |_    | |   [/bold blue]
[bold blue]  \___/ |_____|   |_|   [/bold blue]
[bold cyan]    VNU-HCM | M-GPUX    [/bold cyan]
"""

DOCS = """
[bold]Quick Start Guide:[/bold]
1. [yellow]m-gpux account add[/yellow]   - Configure your Modal Token
2. [yellow]m-gpux hub[/yellow]           - Launch Interactive GPU Hub for Jupyter/Scripts
3. [yellow]m-gpux billing usage[/yellow] - Track your $30 monthly cloud credits
"""

@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        console.print(UIT_LOGO)
        console.print(Panel(DOCS.strip(), title="⚡ Welcome to M-GPUX CLI", expand=False, border_style="cyan"))
        console.print("\n[dim]Run `m-gpux --help` for the full command list.[/dim]\n")
        
@app.command()
def info():
    """Print information about m-gpux."""
    console.print(Panel("[bold green]m-gpux[/bold green]\nYour ultimate utility for Modal platform GPU resources.", expand=False))

if __name__ == "__main__":
    app()
