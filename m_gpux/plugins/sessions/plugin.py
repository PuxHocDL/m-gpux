"""Session manager for Hub/dev Modal apps."""

from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

import typer
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase
from m_gpux.core.state import forget_session, get_session, list_sessions, update_session

app = typer.Typer(no_args_is_help=True)


def _require_session(session_id: str) -> dict:
    session = get_session(session_id)
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(1)
    return session


@app.command("list")
def list_command() -> None:
    """List locally tracked Hub/dev sessions."""
    sessions = list_sessions()
    if not sessions:
        console.print("[yellow]No tracked sessions yet.[/yellow]")
        console.print("[dim]Launch `m-gpux dev` or keep a Hub app running to create one.[/dim]")
        return

    table = Table(title="Tracked M-GPUX Sessions")
    table.add_column("ID", style="bold yellow")
    table.add_column("Kind", style="cyan")
    table.add_column("Profile")
    table.add_column("Compute")
    table.add_column("App")
    table.add_column("State")
    table.add_column("Workspace Volume", style="dim")
    for session in sessions:
        table.add_row(
            str(session.get("id", "")),
            str(session.get("kind", "")),
            str(session.get("profile", "")),
            str(session.get("compute", "")),
            str(session.get("app_name", "")),
            str(session.get("state", "unknown")),
            str(session.get("workspace_volume", "")),
        )
    console.print(table)


@app.command("show")
def show_command(session_id: str) -> None:
    """Show one session's metadata."""
    session = _require_session(session_id)
    table = Table.grid(padding=(0, 2))
    for key in sorted(session):
        table.add_row(f"[dim]{key}[/dim]", str(session[key]))
    console.print(table)


@app.command("logs")
def logs_command(session_id: str) -> None:
    """Stream Modal logs for a tracked session."""
    session = _require_session(session_id)
    app_name = session.get("app_name")
    if not app_name:
        console.print("[red]Session has no app_name.[/red]")
        raise typer.Exit(1)
    env = {**os.environ}
    if session.get("profile"):
        env["MODAL_PROFILE"] = str(session["profile"])
    subprocess.run(["modal", "app", "logs", str(app_name)], env=env)


@app.command("open")
def open_command(session_id: str) -> None:
    """Open a stored URL, or show logs to recover the tunnel URL."""
    session = _require_session(session_id)
    url = session.get("url")
    if url:
        webbrowser.open(str(url))
        console.print(f"[green]Opened:[/green] {url}")
        return
    console.print("[yellow]No URL is stored locally for this session.[/yellow]")
    console.print("[dim]The remote app prints its tunnel URL in logs. Run:[/dim]")
    console.print(f"[bold cyan]m-gpux sessions logs {session.get('id')}[/bold cyan]")


@app.command("pull")
def pull_command(
    session_id: str,
    to: Path = typer.Option(Path("./m-gpux-workspace"), "--to", help="Local destination folder"),
) -> None:
    """Pull the session workspace Volume back to local disk."""
    session = _require_session(session_id)
    volume = session.get("workspace_volume")
    if not volume:
        console.print("[red]Session has no workspace_volume.[/red]")
        raise typer.Exit(1)
    to.mkdir(parents=True, exist_ok=True)
    subprocess.run(["modal", "volume", "get", str(volume), "/", str(to)])


@app.command("stop")
def stop_command(session_id: str) -> None:
    """Stop the Modal app for a tracked session."""
    session = _require_session(session_id)
    app_name = session.get("app_name")
    if not app_name:
        console.print("[red]Session has no app_name.[/red]")
        raise typer.Exit(1)
    env = {**os.environ}
    if session.get("profile"):
        env["MODAL_PROFILE"] = str(session["profile"])
    result = subprocess.run(["modal", "app", "stop", str(app_name)], env=env)
    if result.returncode == 0:
        update_session(session_id, state="stopped")
        console.print(f"[green]Stopped session {session_id}.[/green]")


@app.command("forget")
def forget_command(session_id: str) -> None:
    """Remove a session from the local session list."""
    if forget_session(session_id):
        console.print(f"[green]Forgot session:[/green] {session_id}")
    else:
        console.print(f"[yellow]Session not found:[/yellow] {session_id}")


class SessionsPlugin(PluginBase):
    name = "sessions"
    help = "List, inspect, stop, and pull Hub/dev sessions."
    rich_help_panel = "Workspace"

    def register(self, root_app):
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
