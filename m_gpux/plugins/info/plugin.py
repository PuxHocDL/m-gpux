"""``info`` plugin — prints framework metadata."""

from rich.panel import Panel

from m_gpux import __version__
from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase


def info_command() -> None:
    """Print framework metadata and system capabilities."""
    console.print(
        Panel(
            f"[bold green]M-GPUX Orchestrator[/bold green]\nVersion: {__version__}\n"
            "Your ultimate utility for interacting with Modal serverless GPU resources.",
            expand=False,
        )
    )


class InfoPlugin(PluginBase):
    name = "info"
    help = "Print framework metadata and system capabilities."
    rich_help_panel = "Utility"

    def register(self, root_app):
        root_app.command(
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )(info_command)
