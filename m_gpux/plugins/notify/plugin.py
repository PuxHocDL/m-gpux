"""``notify`` plugin — push m-gpux events to Discord, Slack, Telegram, ntfy or a webhook.

``m-gpux notify add`` registers a channel, ``notify test`` checks it, and
``notify watch`` runs a small loop that reports when m-gpux apps stop or run
too long, when an account runs low on credit or goes over budget, and when a
gateway job finishes. ``up``, ``sweep``, ``run``, ``gateway submit --wait``
and ``budget check`` notify on their own.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import typer
from rich.prompt import Prompt
from rich.table import Table

from m_gpux.core import notify as core
from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase
from m_gpux.core.state import STATE_DIR, _read_json, _write_json

app = typer.Typer(no_args_is_help=True)

WATCH_STATE_PATH = STATE_DIR / "notify_watch.json"


def _fail(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(1)


def parse_duration(text: str) -> int:
    """``90``, ``45m``, ``4h``, ``1d`` → seconds."""
    raw = text.strip().lower()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        if raw and raw[-1] in units:
            return int(float(raw[:-1]) * units[raw[-1]])
        return int(float(raw))
    except ValueError as exc:
        raise typer.BadParameter(f"'{text}' is not a duration like 30m, 4h or 1d.") from exc


def human(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d{(seconds % 86400) // 3600}h"


# ─── Channels ───────────────────────────────────────────────────


@app.command("add")
def add_command(
    kind: Optional[str] = typer.Argument(None, help=f"Channel type: {', '.join(core.TYPES)}."),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Channel name (default: the type)."),
    url: Optional[str] = typer.Option(None, "--url", help="Webhook / topic URL (prompted, hidden, when omitted)."),
    chat_id: Optional[str] = typer.Option(None, "--chat-id", help="Telegram chat id."),
    events: Optional[str] = typer.Option(None, "--events", help="Comma list of events (default: all)."),
) -> None:
    """Add or replace a notification channel, then send a test message."""
    if kind is None:
        from m_gpux.core.ui import arrow_select

        kinds = list(core.TYPES)
        kind = kinds[arrow_select([(k, d) for k, d in core.TYPES.items()], title="Channel type")]
    kind = kind.lower()
    if kind not in core.TYPES:
        _fail(f"Unknown type '{kind}'. Use one of: {', '.join(core.TYPES)}.")
    channel: dict[str, Any] = {"name": name or kind, "type": kind}
    if events:
        channel["events"] = [e.strip() for e in events.split(",") if e.strip()]
    if kind == "telegram":
        channel["bot_token"] = Prompt.ask("[bold cyan]Bot token[/bold cyan] [dim](hidden)[/dim]", password=True)
        channel["chat_id"] = chat_id or Prompt.ask("[bold cyan]Chat id[/bold cyan]")
    else:
        # Webhook URLs are credentials: prompt hidden so they stay out of shell history.
        channel["url"] = url or Prompt.ask(
            f"[bold cyan]{core.TYPES[kind]}[/bold cyan] [dim](hidden)[/dim]", password=True
        )
    try:
        clean = core.add_channel(channel)
    except core.NotifyError as exc:
        _fail(str(exc))
        return
    console.print(f"[green]Saved channel '{clean['name']}'[/green] [dim]{core.masked(clean)}[/dim]")
    _report(core.send("test", "m-gpux notifications are on", "This channel is connected.", channels=[clean]))


@app.command("list")
def list_command() -> None:
    """Configured channels (secrets masked)."""
    channels = core.load_channels()
    if not channels:
        console.print("[yellow]No channels yet. Try: m-gpux notify add discord[/yellow]")
        return
    table = Table(title="Notification channels")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Target", style="dim")
    table.add_column("Events")
    for c in channels:
        table.add_row(c["name"], c["type"], core.masked(c), ", ".join(c.get("events") or ["*"]))
    console.print(table)


@app.command("events")
def events_command() -> None:
    """Events a channel can subscribe to."""
    table = Table(title="Events")
    table.add_column("Event", style="cyan")
    table.add_column("When")
    for event, desc in core.EVENTS.items():
        table.add_row(event, desc)
    console.print(table)


@app.command("remove")
def remove_command(name: str = typer.Argument(..., help="Channel name.")) -> None:
    """Delete a channel."""
    if core.remove_channel(name):
        console.print(f"[green]Removed '{name}'.[/green]")
    else:
        _fail(f"No channel named '{name}'.")


def _report(results: list[tuple[str, bool, str]]) -> None:
    if not results:
        console.print("[yellow]No channel is subscribed to that event.[/yellow]")
        return
    for name, ok, error in results:
        console.print(f"  [green]✓ {name}[/green]" if ok else f"  [red]✗ {name}[/red] {error}")
    if not all(ok for _, ok, _ in results):
        raise typer.Exit(1)


@app.command("test")
def test_command(channel: Optional[str] = typer.Argument(None, help="One channel (default: all).")) -> None:
    """Send a test message."""
    channels = [c for c in core.load_channels() if channel in (None, c["name"])]
    if not channels:
        _fail("No matching channel. Add one with: m-gpux notify add")
    _report(core.send("test", "m-gpux test notification", f"Sent from {_host()}.", channels=channels))


@app.command("send")
def send_command(
    title: str = typer.Argument(..., help="Title / first line."),
    message: str = typer.Argument("", help="Body."),
    event: str = typer.Option("test", "--event", help="Event name used for channel filtering."),
    level: str = typer.Option("info", "--level", help="info, success, warning or error."),
) -> None:
    """Send a custom message (handy at the end of your own scripts)."""
    if event not in core.EVENTS:
        _fail(f"Unknown event '{event}'. See: m-gpux notify events")
    _report(core.send(event, title, message, level=level))


def _host() -> str:
    import platform

    return platform.node() or "this machine"


# ─── Watch ──────────────────────────────────────────────────────


def diff_apps(
    previous: dict[str, dict[str, Any]],
    apps: list[tuple[str, str, str, str]],
    now: float,
    long_running: int,
) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str, str, str]]]:
    """Compare the last seen apps with ``scan_apps_across_profiles`` output.

    Returns ``(new_state, events)`` where each event is
    ``(event, title, message, level)``. Pure, so it is unit-tested.
    """
    state: dict[str, dict[str, Any]] = {}
    events: list[tuple[str, str, str, str]] = []
    for profile, app_id, desc, _app_state in apps:
        key = f"{profile}/{app_id}"
        seen = previous.get(key) or {"first_seen": now, "desc": desc, "profile": profile, "warned": False}
        seen = {**seen, "desc": desc}
        age = now - float(seen["first_seen"])
        if long_running and age >= long_running and not seen.get("warned"):
            events.append(
                (
                    "app.long_running",
                    f"{desc} has been running {human(age)}",
                    f"Account {profile} · app {app_id}. Stop it with: m-gpux stop",
                    "warning",
                )
            )
            seen["warned"] = True
        state[key] = seen
    for key, seen in previous.items():
        if key not in state:
            age = now - float(seen.get("first_seen", now))
            events.append(
                (
                    "app.stopped",
                    f"{seen.get('desc', key)} stopped",
                    f"Account {seen.get('profile', '?')} · ran at least {human(age)}.",
                    "info",
                )
            )
    return state, events


def credit_events(
    balances: list[tuple[str, float, float]],
    low_credit: float,
    warned: dict[str, str],
    month: str,
) -> tuple[dict[str, str], list[tuple[str, str, str, str]]]:
    """Low-credit / over-budget alerts, at most once per account per month and kind."""
    from m_gpux.core.budget import budget_for

    events = []
    warned = dict(warned)
    for profile, used, spendable in balances:
        if used < 0:
            continue
        budget = budget_for(profile)
        if budget is not None and used >= budget and warned.get(f"over:{profile}") != month:
            events.append(
                (
                    "budget.over",
                    f"{profile} is over its budget",
                    f"${used:.2f} used of ${budget:.2f} this month.",
                    "error",
                )
            )
            warned[f"over:{profile}"] = month
        elif spendable <= low_credit and warned.get(f"low:{profile}") != month:
            events.append(
                (
                    "credit.low",
                    f"{profile} is low on credit",
                    f"${spendable:.2f} left this month (${used:.2f} used).",
                    "warning",
                )
            )
            warned[f"low:{profile}"] = month
    return warned, events


def _gateway_events() -> list[tuple[str, str, str, str]]:
    """Refresh unfinished gateway jobs and report the ones that just finished."""
    from m_gpux.core.state import get_gateway_endpoint, list_gateway_jobs, save_gateway_job

    state = get_gateway_endpoint()
    if not state:
        return []
    from m_gpux.plugins.gateway.client import TERMINAL_STATES, GatewayHTTPError, gateway_request

    events = []
    for job in list_gateway_jobs():
        if job.get("status") in TERMINAL_STATES:
            continue
        try:
            current = gateway_request(state["url"], state["api_key"], f"/v1/jobs/{job['id']}", timeout=20)
        except GatewayHTTPError as exc:
            if exc.status != 404:
                continue
            current = {**job, "status": "expired"}
        except Exception:
            continue
        if not isinstance(current, dict):
            continue
        save_gateway_job(current)
        if current.get("status") in TERMINAL_STATES:
            events.append(job_event(current))
    return events


def job_event(job: dict[str, Any]) -> tuple[str, str, str, str]:
    status = str(job.get("status"))
    ok = status == "succeeded"
    return (
        "job.done" if ok else "job.failed",
        f"Gateway job {job.get('task', '')} {status}",
        f"Job {job.get('id')}. Details: m-gpux gateway result {job.get('id')}",
        "success" if ok else "error",
    )


def _emit(events: list[tuple[str, str, str, str]]) -> None:
    for event, title, message, level in events:
        stamp = datetime.now().strftime("%H:%M:%S")
        console.print(f"[dim]{stamp}[/dim] [bold]{event}[/bold] {title}")
        failed = [n for n, ok, _ in core.send(event, title, message, level=level) if not ok]
        if failed:
            console.print(f"[red]  delivery failed: {', '.join(failed)}[/red]")


@app.command("watch")
def watch_command(
    interval: int = typer.Option(120, "--interval", "-i", help="Seconds between app checks (min 30)."),
    long_running: str = typer.Option("4h", "--long-running", help="Warn when an app runs longer (0 = off)."),
    low_credit: float = typer.Option(5.0, "--low-credit", help="Warn when an account has this many $ left."),
    credit_every: int = typer.Option(900, "--credit-every", help="Seconds between billing checks (min 300)."),
    once: bool = typer.Option(False, "--once", help="Check once and exit (for cron / Task Scheduler)."),
) -> None:
    """Watch apps, credit and gateway jobs; notify on changes until Ctrl+C."""
    from m_gpux.core.profiles import get_all_balances
    from m_gpux.core.runner import scan_apps_across_profiles

    if not core.load_channels():
        console.print("[yellow]No channels configured — events are only printed. Add one: m-gpux notify add[/yellow]")
    limit = parse_duration(long_running) if long_running not in ("0", "off") else 0
    interval = max(interval, 30)
    credit_every = max(credit_every, 300)
    saved = _read_json(WATCH_STATE_PATH, {})
    apps_state = saved.get("apps", {}) if isinstance(saved, dict) else {}
    warned = saved.get("warned", {}) if isinstance(saved, dict) else {}
    last_credit = 0.0
    if not once:
        console.print(f"[cyan]Watching every {interval}s. Ctrl+C to stop.[/cyan]")
    try:
        while True:
            now = time.time()
            apps_state, events = diff_apps(apps_state, scan_apps_across_profiles(), now, limit)
            if now - last_credit >= credit_every:
                month = datetime.now(timezone.utc).strftime("%Y-%m")
                warned, credit = credit_events(get_all_balances(), low_credit, warned, month)
                events += credit
                last_credit = now
            events += _gateway_events()
            _emit(events)
            _write_json(WATCH_STATE_PATH, {"apps": apps_state, "warned": warned})
            if once:
                if not events:
                    console.print(f"[green]Checked {len(apps_state)} running app(s); nothing to report.[/green]")
                return
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")


class NotifyPlugin(PluginBase):
    name = "notify"
    help = "Notifications to Discord, Slack, Telegram, ntfy or a webhook."
    rich_help_panel = "Utility"

    def register(self, root_app):
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
