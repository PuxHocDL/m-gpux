import typer
from rich.console import Console
from rich.table import Table
import os
import tomlkit

app = typer.Typer(no_args_is_help=True)
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

@app.command("list")
def list_accounts():
    """List all available Modal profiles."""
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
    
@app.command("switch")
def switch_account(name: str):
    """Switch the active Modal profile."""
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

@app.command("add")
def add_account(name: str = typer.Option(..., prompt="Profile Name"),
                token_id: str = typer.Option(..., prompt="Modal Token ID"),
                token_secret: str = typer.Option(..., prompt="Modal Token Secret")):
    """Add a new Modal profile."""
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

