"""``budget`` plugin — monthly spending limits per Modal account.

Budgets feed into AUTO account selection (accounts over budget are skipped),
the low-credit warning when you pick an account by hand, and ``budget check``
/ ``budget watch``, which can stop m-gpux apps on accounts that went over.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import typer
from rich.table import Table

from m_gpux.core.budget import DEFAULT_KEY, budget_for, clear_budget, load_budgets, set_budget
from m_gpux.core.console import console
from m_gpux.core.modal_cli import stop_app
from m_gpux.core.plugin import PluginBase
from m_gpux.core.profiles import MONTHLY_CREDIT, get_all_balances, get_all_profiles
from m_gpux.core.runner import scan_apps_across_profiles

app = typer.Typer(no_args_is_help=True)


@app.command("set")
def set_command(
    amount: float = typer.Argument(..., help="Monthly limit in USD (may be above the free $30 credit)"),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile to limit (default: every account)"),
) -> None:
    """Set a monthly spending limit for one account, or the default for all."""
    if amount < 0:
        console.print("[red]Amount must be >= 0.[/red]")
        raise typer.Exit(1)
    if account and account not in get_all_profiles():
        console.print(f"[red]Profile '{account}' not found.[/red]")
        raise typer.Exit(1)
    set_budget(account, amount)
    target = f"'{account}'" if account else "every account without its own budget"
    console.print(f"[green]Budget ${amount:.2f}/month set for {target}.[/green]")


@app.command("clear")
def clear_command(
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile (default: the all-accounts default)"),
) -> None:
    """Remove a budget."""
    if clear_budget(account):
        console.print("[green]Budget removed.[/green]")
    else:
        console.print("[yellow]No such budget.[/yellow]")


def _status_rows() -> list[tuple[str, float, Optional[float], float]]:
    """``[(profile, used, limit, spendable)]`` for accounts whose usage could be read."""
    budgets = load_budgets()
    return [(name, used, budget_for(name, budgets), left) for name, used, left in get_all_balances() if used >= 0]


def _render(rows) -> list[str]:
    table = Table(title=f"Budgets — {datetime.now():%B %Y}")
    table.add_column("Account", style="cyan")
    table.add_column("Used", justify="right")
    table.add_column("Limit", justify="right")
    table.add_column("Left", justify="right")
    table.add_column("", justify="left")
    over: list[str] = []
    for name, used, limit, left in sorted(rows, key=lambda r: r[3]):
        cap = MONTHLY_CREDIT if limit is None else limit
        pct = used / cap * 100 if cap > 0 else 100.0
        if left <= 0:
            flag = "[bold red]OVER[/bold red]"
            over.append(name)
        elif pct >= 80:
            flag = f"[yellow]{pct:.0f}%[/yellow]"
        else:
            flag = f"[green]{pct:.0f}%[/green]"
        limit_str = f"${limit:.2f}" if limit is not None else f"[dim]${MONTHLY_CREDIT:.0f} credit[/dim]"
        table.add_row(name, f"${used:.2f}", limit_str, f"${left:.2f}", flag)
    console.print(table)
    return over


def _stop_over_budget(over: list[str]) -> int:
    apps = scan_apps_across_profiles(over)
    if not apps:
        console.print("[dim]No running m-gpux apps on the over-budget accounts.[/dim]")
        return 0
    stopped = 0
    for profile, app_id, desc, _ in apps:
        result = stop_app(app_id, profile=profile)
        if result.returncode == 0:
            stopped += 1
            console.print(f"  [red]Stopped[/red] {desc} on {profile}")
        else:
            console.print(f"  [yellow]Could not stop {desc} on {profile}: {result.stderr.strip()}[/yellow]")
    return stopped


@app.command("show")
def show_command() -> None:
    """Show spend vs. budget for every account this month."""
    budgets = load_budgets()
    if DEFAULT_KEY in budgets:
        console.print(f"[dim]Default budget: ${budgets[DEFAULT_KEY]:.2f}/month[/dim]")
    console.print("[cyan]Fetching usage for all accounts...[/cyan]")
    _render(_status_rows())


@app.command("check")
def check_command(
    stop: bool = typer.Option(False, "--stop", help="Stop m-gpux apps on accounts that are over budget"),
) -> None:
    """Exit non-zero if any account is over budget (handy for cron / CI)."""
    over = _render(_status_rows())
    if not over:
        console.print("[green]All accounts within budget.[/green]")
        return
    console.print(f"[bold red]{len(over)} account(s) over budget:[/bold red] {', '.join(over)}")
    if stop:
        _stop_over_budget(over)
    raise typer.Exit(2)


@app.command("watch")
def watch_command(
    interval: int = typer.Option(600, "--interval", "-i", help="Seconds between checks (min 60)"),
    stop: bool = typer.Option(True, "--stop/--no-stop", help="Stop m-gpux apps on accounts that go over budget"),
) -> None:
    """Keep checking budgets and enforce them until Ctrl+C."""
    interval = max(interval, 60)
    console.print(f"[cyan]Watching budgets every {interval}s. Press Ctrl+C to stop.[/cyan]")
    try:
        while True:
            over = _render(_status_rows())
            if over and stop:
                _stop_over_budget(over)
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")


class BudgetPlugin(PluginBase):
    name = "budget"
    help = "Monthly spending limits per account, with optional auto-stop."
    rich_help_panel = "Identity & Finance"

    def register(self, root_app):
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
