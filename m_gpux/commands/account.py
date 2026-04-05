import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt
import os
import re
import tomlkit
from datetime import datetime, timezone

MONTHLY_CREDIT = 30.0

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

def _get_month_usage(token_id: str, token_secret: str) -> float:
    """Fetch usage cost for the current billing month (since 1st of the month)."""
    try:
        from modal.billing import workspace_billing_report
        from modal.client import Client

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        client = Client.from_credentials(str(token_id), str(token_secret))
        reports = workspace_billing_report(start=month_start, resolution="d", client=client)
        return sum(float(r.get("cost", 0)) for r in reports)
    except Exception:
        return -1.0  # signal fetch failure


@app.command("list", help="Display all configured Modal profiles and current active status.")
def list_accounts():
    """List all available Modal profiles with remaining monthly credits."""
    doc = load_config()
    profiles = list(doc.keys())

    if not profiles:
        console.print("[yellow]No profiles found. Run `m-gpux account add` to configure.[/yellow]")
        return

    console.print("[cyan]Fetching billing data...[/cyan]")

    table = Table(title="Modal Workspaces (Profiles)")
    table.add_column("Profile Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Used", style="red", justify="right")
    table.add_column("Remaining", style="green", justify="right")

    total_remaining = 0.0

    for p in profiles:
        is_active = doc[p].get("active", False)
        status = "[bold green]Active[/bold green]" if is_active else ""

        token_id = doc[p].get("token_id")
        token_secret = doc[p].get("token_secret")

        if token_id and token_secret:
            used = _get_month_usage(token_id, token_secret)
            if used < 0:
                used_str = "[yellow]Error[/yellow]"
                remaining_str = "[yellow]?[/yellow]"
            else:
                remaining = max(MONTHLY_CREDIT - used, 0)
                total_remaining += remaining
                used_str = f"${used:.2f}"
                if remaining < 5:
                    remaining_str = f"[bold red]${remaining:.2f}[/bold red]"
                elif remaining < 15:
                    remaining_str = f"[yellow]${remaining:.2f}[/yellow]"
                else:
                    remaining_str = f"[green]${remaining:.2f}[/green]"
        else:
            used_str = "[dim]N/A[/dim]"
            remaining_str = "[dim]N/A[/dim]"

        table.add_row(p, status, used_str, remaining_str)

    console.print(table)
    console.print(f"\n[bold]Total remaining across all profiles: [green]${total_remaining:.2f}[/green][/bold]")
    now = datetime.now()
    console.print(f"[dim]Credits reset on the 1st of each month ($30/account). Current period: {now.strftime('%B %Y')}[/dim]")


def get_best_profile():
    """Return the profile name with the most remaining credit, or None.
    
    Used by smart rotation to auto-pick the cheapest account.
    Returns (profile_name, remaining_credit) or (None, 0).
    """
    doc = load_config()
    best_name = None
    best_remaining = 0.0

    for p in doc:
        token_id = doc[p].get("token_id")
        token_secret = doc[p].get("token_secret")
        if not token_id or not token_secret:
            continue
        used = _get_month_usage(token_id, token_secret)
        if used < 0:
            continue
        remaining = MONTHLY_CREDIT - used
        if remaining > best_remaining:
            best_remaining = remaining
            best_name = p

    return best_name, best_remaining


def get_all_balances():
    """Return list of (profile_name, used, remaining) for all profiles, sorted by remaining desc."""
    doc = load_config()
    results = []
    for p in doc:
        token_id = doc[p].get("token_id")
        token_secret = doc[p].get("token_secret")
        if not token_id or not token_secret:
            continue
        used = _get_month_usage(token_id, token_secret)
        if used < 0:
            results.append((p, -1, -1))
        else:
            results.append((p, used, max(MONTHLY_CREDIT - used, 0)))
    results.sort(key=lambda x: x[2], reverse=True)
    return results
    
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

def _parse_modal_token_command(raw: str):
    """Parse a `modal token set ...` command string and extract token-id, token-secret, profile."""
    token_id_match = re.search(r'--token-id\s+(\S+)', raw)
    token_secret_match = re.search(r'--token-secret\s+(\S+)', raw)
    profile_match = re.search(r'--profile[=\s]+(\S+)', raw)
    if token_id_match and token_secret_match:
        return (
            token_id_match.group(1),
            token_secret_match.group(1),
            profile_match.group(1) if profile_match else None,
        )
    return None


@app.command("add", help="Add a new profile using Token ID and Secret, or paste a `modal token set` command.")
def add_account(
    name: str = typer.Option(None, help="A friendly name for this profile (e.g. 'personal' or 'work')"),
    token_id: str = typer.Option(None, help="The Token ID from your Modal dashboard"),
    token_secret: str = typer.Option(None, help="The Token Secret from your Modal dashboard")
):
    """Add a new Modal profile by providing credentials securely to local storage.
    
    You can either provide --name, --token-id, --token-secret individually,
    or paste the full `modal token set ...` command when prompted."""
    doc = load_config()

    # If not all args provided, try paste shortcut first
    if not (token_id and token_secret):
        console.print(
            "[cyan]Tip: You can paste the full `modal token set --token-id ... --token-secret ... --profile=...` command.[/cyan]"
        )
        raw = Prompt.ask("[bold cyan]Paste command or press Enter to fill manually[/bold cyan]", default="")
        parsed = _parse_modal_token_command(raw) if raw.strip() else None
        if parsed:
            token_id, token_secret, parsed_name = parsed
            if parsed_name and not name:
                name = parsed_name
            console.print(f"[green]Parsed token from command successfully![/green]")
        else:
            if not token_id:
                token_id = Prompt.ask("Modal Token ID")
            if not token_secret:
                token_secret = Prompt.ask("Modal Token Secret")

    if not name:
        name = Prompt.ask("Profile Name")

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

