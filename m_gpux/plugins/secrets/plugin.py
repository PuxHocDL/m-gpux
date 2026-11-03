"""``secrets`` plugin — keep Modal Secrets in step across every workspace.

Each Modal profile is a separate workspace with its own Secrets, so a job that
works on one account fails on another with "Secret not found". Modal never
returns secret values, so syncing always starts from a local source: an
environment variable, a ``.env`` file or a hidden prompt. Values are sent
straight to Modal and never printed or stored by m-gpux.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import typer
from rich.prompt import Confirm, Prompt
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase
from m_gpux.core.workspaces import WorkspaceError, for_each, resolve_targets, short_error

app = typer.Typer(no_args_is_help=True)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _targets(spec: Optional[str], *, default_active: bool = True) -> list[str]:
    try:
        return resolve_targets(spec, default_active=default_active)
    except WorkspaceError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


def parse_dotenv(text: str) -> dict[str, str]:
    """Minimal ``.env`` parser: ``KEY=VALUE`` lines, ``export`` prefix, quotes, ``#`` comments."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not KEY_RE.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def collect_values(keys: list[str], dotenv: Optional[Path], *, prompt: bool = True) -> dict[str, str]:
    """Values for *keys* from the ``.env`` file, then the environment, then a hidden prompt."""
    from_file = parse_dotenv(dotenv.read_text(encoding="utf-8")) if dotenv else {}
    if dotenv and not keys:
        keys = list(from_file)
    values: dict[str, str] = {}
    for key in keys:
        if not KEY_RE.match(key):
            raise typer.BadParameter(f"'{key}' is not a valid variable name (use KEY, not KEY=VALUE).")
        if key in from_file:
            values[key] = from_file[key]
        elif os.environ.get(key):
            values[key] = os.environ[key]
        elif prompt:
            entered = Prompt.ask(f"[bold cyan]{key}[/bold cyan] [dim](hidden)[/dim]", password=True)
            if not entered:
                raise typer.BadParameter(f"No value for {key}.")
            values[key] = entered
        else:
            raise typer.BadParameter(f"No value for {key} in the .env file or the environment.")
    return values


def _secret_names(_profile: str, client) -> set[str]:
    import modal

    return {s.name for s in modal.Secret.objects.list(client=client) if getattr(s, "name", None)}


@app.command("status")
def status_command(
    names: Optional[list[str]] = typer.Argument(None, help="Secret names to check (default: every name seen)."),
    to: Optional[str] = typer.Option(None, "--to", help="Profiles: 'all' (default), or a comma list."),
) -> None:
    """Which workspace has which Secret."""
    profiles = _targets(to, default_active=False)
    with console.status(f"Listing secrets in {len(profiles)} workspace(s)..."):
        found = for_each(profiles, _secret_names)
    wanted = sorted(set(names or []) or {n for r in found.values() if isinstance(r, set) for n in r})
    if not wanted:
        console.print("[yellow]No secrets in any workspace yet. Try: m-gpux secrets sync hf HF_TOKEN --to all[/yellow]")
        return
    table = Table(title="Secrets per workspace")
    table.add_column("Secret", style="cyan")
    for profile in profiles:
        table.add_column(profile, justify="center")
    for name in wanted:
        cells = []
        for profile in profiles:
            result = found[profile]
            cells.append(
                "[red]error[/red]"
                if isinstance(result, Exception)
                else "[green]✓[/green]"
                if name in result
                else "[dim]—[/dim]"
            )
        table.add_row(name, *cells)
    console.print(table)
    for profile, result in found.items():
        if isinstance(result, Exception):
            console.print(f"[red]{profile}: {short_error(result)}[/red]")
    missing = sum(1 for n in wanted for p in profiles if isinstance(found[p], set) and n not in found[p])
    if missing:
        console.print(f"[dim]{missing} missing. Fill them with: m-gpux secrets sync NAME KEY ... --to all[/dim]")


@app.command("sync")
def sync_command(
    name: str = typer.Argument(..., help="Secret name on Modal, e.g. 'hf' or 'wandb'."),
    keys: Optional[list[str]] = typer.Argument(
        None, help="Variable names to store (values never on the command line)."
    ),
    to: Optional[str] = typer.Option("all", "--to", help="Profiles: 'all' (default), a comma list, or '' for active."),
    dotenv: Optional[Path] = typer.Option(None, "--from-dotenv", help="Read values from a .env file."),
    replace: bool = typer.Option(False, "--replace", help="Replace the whole Secret instead of merging keys into it."),
    no_prompt: bool = typer.Option(False, "--no-prompt", help="Fail instead of prompting for a missing value."),
) -> None:
    """Create or update a Secret with the same keys in every target workspace.

    Values come from --from-dotenv, then environment variables with the same
    name, then a hidden prompt. Existing Secrets are merged (other keys stay)
    unless --replace is given.
    """
    if not NAME_RE.match(name):
        console.print("[red]Secret names use letters, digits, '.', '_' and '-'.[/red]")
        raise typer.Exit(1)
    if dotenv and not dotenv.is_file():
        console.print(f"[red]{dotenv} not found.[/red]")
        raise typer.Exit(1)
    if not keys and not dotenv:
        console.print("[red]Name at least one KEY, or pass --from-dotenv FILE.[/red]")
        raise typer.Exit(1)
    profiles = _targets(to)
    values = collect_values(list(keys or []), dotenv, prompt=not no_prompt)
    if not values:
        console.print("[red]Nothing to store.[/red]")
        raise typer.Exit(1)

    def apply(_profile: str, client) -> str:
        import modal

        exists = name in _secret_names(_profile, client)
        if exists and not replace:
            modal.Secret.from_name(name, client=client).update(values)
            return "updated"
        if exists:
            modal.Secret.objects.delete(name, client=client, allow_missing=True)
        modal.Secret.objects.create(name, values, client=client)
        return "replaced" if exists else "created"

    with console.status(f"Writing '{name}' to {len(profiles)} workspace(s)..."):
        results = for_each(profiles, apply)
    keys_text = ", ".join(sorted(values))
    failed = 0
    for profile, result in results.items():
        if isinstance(result, Exception):
            failed += 1
            console.print(f"  [red]✗ {profile}[/red] {short_error(result)}")
        else:
            console.print(f"  [green]✓ {profile}[/green] {result} [dim]({keys_text})[/dim]")
    console.print(
        f"\n[bold]{len(results) - failed}/{len(results)} workspaces.[/bold] "
        f'[dim]Use it with secrets=[modal.Secret.from_name("{name}")] or `secrets = ["{name}"]` in mgpux.toml.[/dim]'
    )
    if failed:
        raise typer.Exit(1)


@app.command("delete")
def delete_command(
    name: str = typer.Argument(..., help="Secret to delete."),
    to: Optional[str] = typer.Option(None, "--to", help="Profiles: 'all', a comma list, or empty for the active one."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation."),
) -> None:
    """Delete a Secret from one or more workspaces."""
    profiles = _targets(to)
    if not yes and not Confirm.ask(f"Delete secret '{name}' from {', '.join(profiles)}?", default=False):
        raise typer.Exit(0)

    def remove(_profile: str, client) -> str:
        import modal

        modal.Secret.objects.delete(name, client=client, allow_missing=True)
        return "deleted"

    results = for_each(profiles, remove)
    for profile, result in results.items():
        if isinstance(result, Exception):
            console.print(f"  [red]✗ {profile}[/red] {short_error(result)}")
        else:
            console.print(f"  [green]✓ {profile}[/green] {result}")


class SecretsPlugin(PluginBase):
    name = "secrets"
    help = "Keep Modal Secrets in sync across every workspace."
    rich_help_panel = "Workspace"

    def register(self, root_app):
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
