"""``m-gpux ui``: a local web dashboard for accounts, compute and workloads."""

from __future__ import annotations

import sys
import threading
import webbrowser

import typer
from rich.panel import Panel

from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase

DEFAULT_PORT = 7878
LOOPBACK = ("127.0.0.1", "localhost")


def ui_command(
    port: int = typer.Option(
        DEFAULT_PORT, "--port", "-p", min=0, max=65535, help="Port to listen on; the next free one is used if taken."
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Interface to bind. Anything but loopback exposes your accounts to the network."
    ),
    no_browser: bool = typer.Option(False, "--no-browser", help="Print the URL instead of opening a browser."),
) -> None:
    """Open the local dashboard: accounts, apps, containers, sandboxes, sessions and costs."""
    from m_gpux.plugins.ui import data
    from m_gpux.plugins.ui.server import DashboardServer

    server = None
    error: OSError | None = None
    for candidate in [0] if port == 0 else range(port, min(port + 20, 65536)):
        try:
            server = DashboardServer((host, candidate))
            break
        except OSError as exc:
            error = exc
    if server is None:
        console.print(f"[bold red]Could not start the dashboard on {host}:{port}: {error}[/bold red]")
        raise typer.Exit(1)

    if host not in LOOPBACK:
        console.print(
            f"[bold yellow]Listening on {host}: anyone who can reach this address and has the URL "
            "below can manage your Modal accounts.[/bold yellow]"
        )
    console.print(
        Panel(
            "[bold]m-gpux dashboard is running[/bold]\n"
            "[dim]The link below carries a private token that changes on every start.\n"
            "Press Ctrl+C to stop.[/dim]",
            border_style="green",
            expand=False,
        )
    )
    # Its own unwrapped line, so terminals keep the whole link clickable.
    console.print(f"[bold green]{server.url}[/bold green]", soft_wrap=True)
    sys.stdout.flush()
    threading.Thread(target=data.prefetch, name="m-gpux-ui-prefetch", daemon=True).start()
    if not no_browser:
        webbrowser.open(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("[dim]Dashboard stopped.[/dim]")
    finally:
        server.server_close()


class UIPlugin(PluginBase):
    name = "ui"
    help = "Local web dashboard for accounts, compute, workloads and costs."
    rich_help_panel = "Start here"

    def register(self, root_app: typer.Typer) -> None:
        root_app.command(name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)(ui_command)
