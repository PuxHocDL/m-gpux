import typer
from rich.console import Console
from rich.panel import Panel

from m_gpux.commands import account
from m_gpux.commands import billing
from m_gpux.commands import hub

app = typer.Typer(
    name="m-gpux", 
    help="A powerful hub and CLI for managing Modal GPUs, Accounts, and Workspaces",
    no_args_is_help=True
)

console = Console()

app.add_typer(account.app, name="account", help="Manage multi-profile Modal accounts")
app.add_typer(billing.app, name="billing", help="View usage and billing details")
app.command(name="hub", help="Interactive GPU hub to start terminals or notebooks")(hub.hub_main)

@app.command()
def info():
    """Print information about m-gpux."""
    console.print(Panel("[bold green]m-gpux[/bold green]\nYour ultimate utility for Modal platform GPU resources.", expand=False))

if __name__ == "__main__":
    app()
