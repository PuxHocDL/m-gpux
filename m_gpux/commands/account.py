import typer
from rich.console import Console
from rich.table import Table
import os
import tomlkit

app = typer.Typer(
    help="Manage Multi-Profile Modal Accounts.\n\nEasily switch between different Modal organizational, personal, or test environment identities.",
    short_help="Identity Management",
    no_args_is_help=True
)
console = Console()

MODAL_CONFIG_PATH = os.path.expanduser("~/.modal.toml")

def load_config():
    if not os.path.exists(MODAL_CONFIG_PATH):
        return tomlkit.document()
    with open(MODAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        return tomlkit.load(f)

def save_config(doc):
    with open(MODAL_CONFIG_PATH, "w", encoding="utf-8") as f:
        tomlkit.dump(doc, f)

@app.command("list", help="Display all configured Modal profiles and current active status.")
def list_accounts():
    """List all available Modal profiles. Shows a table highlighting the currently active workspace."""
    doc = load_config()
    profiles = list(doc.keys())
    
    table = Table(title="Modal Workspaces (Profiles)")
    table.add_column("Profile Name", style="cyan")
    table.add_column("Status", style="green")
    
    if not profiles:
        console.print("[yellow]No profiles found. Run `m-gpux account add` to configure.[/yellow]")
        return

    for p in profiles:
        is_active = doc[p].get("active", False)
        status = "[bold green]Active[/bold green]" if is_active else ""
        table.add_row(p, status)
        
    console.print(table)
    
@app.command("switch", help="Switch the active global profile for Modal deployments.")
def switch_account(name: str = typer.Argument(..., help="Target profile name to activate")):
    """Switch the active Modal profile. Subsequent `m-gpux hub` runs will deploy to this account's infrastructure."""
    doc = load_config()
    if name not in doc:
        console.print(f"[red]Error: Profile '{name}' not found.[/red]")
        raise typer.Exit(1)
        
    for p in doc.keys():
        if "active" in doc[p]:
            del doc[p]["active"]
            
    doc[name]["active"] = True
    save_config(doc)
    console.print(f"[green]Successfully switched to profile '{name}'[/green]")

@app.command("add", help="Add a new profile using Token ID and Secret.")
def add_account(
    name: str = typer.Option(..., prompt="Profile Name", help="A friendly name for this profile (e.g. 'personal' or 'work')"),
    token_id: str = typer.Option(..., prompt="Modal Token ID", help="The Token ID from your Modal dashboard"),
    token_secret: str = typer.Option(..., prompt="Modal Token Secret", help="The Token Secret from your Modal dashboard")
):
    """Add a new Modal profile by providing credentials securely to local storage."""
    doc = load_config()
    name = name.strip()
        
    if name not in doc:
        doc[name] = tomlkit.table()
        
    doc[name]["token_id"] = token_id
    doc[name]["token_secret"] = token_secret
    
    if len(doc.keys()) == 1:
        doc[name]["active"] = True
        
    save_config(doc)
    console.print(f"[green]Added profile '{name}' successfully![/green]")

@app.command("remove")
def remove_account(name: str = typer.Argument(..., help="Name of the Modal profile to remove")):
    """Remove a Modal profile."""
    doc = load_config()
    
    if name not in doc:
        console.print(f"[red]Error: Profile '{name}' not found.[/red]")
        raise typer.Exit(1)
        
    was_active = doc[name].get("active", False)
    del doc[name]
    
    if was_active and len(doc.keys()) > 0:
        new_active = list(doc.keys())[0]
        doc[new_active]["active"] = True
        console.print(f"[yellow]Active profile was deleted. Defaulted active status to '{new_active}'.[/yellow]")
        
    save_config(doc)
    console.print(f"[green]Successfully removed profile '{name}'[/green]")

