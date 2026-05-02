"""``stop`` plugin — discover & stop running m-gpux Modal apps."""

from __future__ import annotations

import json
import os
import subprocess

import typer
from rich.prompt import Prompt
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase
from m_gpux.core.runner import scan_apps_across_profiles


def _scan_current_profile() -> list[tuple[str, str, str, str]]:
    try:
        result = subprocess.run(
            ["modal", "app", "list", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        raw = json.loads(result.stdout) if result.stdout.strip() else []
        p_result = subprocess.run(
            ["modal", "profile", "current"],
            capture_output=True, text=True, timeout=5,
        )
        current_profile = p_result.stdout.strip() if p_result.returncode == 0 else "unknown"
        apps: list[tuple[str, str, str, str]] = []
        for a in raw:
            desc = a.get("Description", a.get("description", ""))
            state = a.get("State", a.get("state", ""))
            app_id = a.get("App ID", a.get("app_id", ""))
            if desc.startswith("m-gpux") and state in ("deployed", "running"):
                apps.append((current_profile, app_id, desc, state))
        return apps
    except Exception:
        return []


def stop_command(
    all_profiles: bool = typer.Option(
        False, "--all", help="Scan and stop apps across ALL Modal profiles"
    ),
) -> None:
    """Stop running m-gpux apps (Jupyter, shells, LLM servers, etc.)."""
    console.print("[cyan]Scanning for running m-gpux apps...[/cyan]")

    apps = scan_apps_across_profiles() if all_profiles else _scan_current_profile()

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

    choice = Prompt.ask("Select app to stop (0=all)", default="0")
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


class StopPlugin(PluginBase):
    name = "stop"
    help = "Stop running m-gpux apps and release GPUs."
    rich_help_panel = "Utility"

    def register(self, root_app):
        root_app.command(
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )(stop_command)
