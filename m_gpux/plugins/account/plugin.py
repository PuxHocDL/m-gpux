import typer
from rich.console import Console
from rich.prompt import Prompt
import os
import re
import tomlkit
from datetime import datetime

MONTHLY_CREDIT = 30.0

app = typer.Typer(
    help="Manage Multi-Profile Modal Accounts.\n\nEasily switch between different Modal organizational, personal, or test environment identities.",
    short_help="Identity Management",
    no_args_is_help=True,
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
    """List all available Modal profiles with remaining monthly credits."""
    doc = load_config()
    profiles = list(doc.keys())

    if not profiles:
        console.print("[yellow]No profiles found. Run `m-gpux account add` to configure.[/yellow]")
        return

    from m_gpux.core.cards import card_grid, load_usages, profile_card

    with console.status("[cyan]Fetching billing data...[/cyan]"):
        usages = load_usages()

    cards = [profile_card(p, bool(doc[p].get("active", False)), usages.get(p)) for p in profiles]
    console.print()
    console.print(card_grid(cards))
    total_remaining = sum(u.left for u in usages.values() if u.used >= 0)
    console.print(f"\n[bold]Total remaining across all profiles: [green]${total_remaining:.2f}[/green][/bold]")
    now = datetime.now()
    console.print(
        f"[dim]Credits reset on the 1st of each month ($30/account). Current period: {now.strftime('%B %Y')}[/dim]"
    )


from m_gpux.core.profiles import get_all_balances, get_best_profile  # noqa: E402,F401


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
    token_id_match = re.search(r"--token-id\s+(\S+)", raw)
    token_secret_match = re.search(r"--token-secret\s+(\S+)", raw)
    profile_match = re.search(r"--profile[=\s]+(\S+)", raw)
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
    token_secret: str = typer.Option(None, help="The Token Secret from your Modal dashboard"),
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
            console.print("[green]Parsed token from command successfully![/green]")
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


# ─── Plugin registration ──────────────────────────────────────
from m_gpux.core.plugin import PluginBase as _PluginBase


class AccountPlugin(_PluginBase):
    name = "account"
    help = "Configure identities and add multiple Modal profiles."
    rich_help_panel = "Identity & Finance"

    def register(self, root_app):
        root_app.add_typer(
            app,
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )
