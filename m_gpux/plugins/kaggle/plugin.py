"""``m-gpux kaggle``: the Kaggle CLI across a zoo of accounts, with AUTO account selection."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

import typer
from rich.prompt import Confirm
from rich.table import Table

from m_gpux.core import kaggle as kz
from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase

app = typer.Typer(
    help="Kaggle CLI across several accounts: GPU quota, live kernels, pushes with AUTO account choice.",
    no_args_is_help=True,
)

PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


def _fail(message: str, code: int = 1) -> None:
    console.print(f"[bold red]{message}[/bold red]")
    raise typer.Exit(code)


def _resolve(name: Optional[str]) -> kz.KaggleAccount:
    """An account by name, or AUTO (most GPU hours left with a free slot) for None / 'auto'."""
    if not kz.executable():
        _fail("The kaggle CLI is not installed. Run: pip install kaggle")
    if not name or name.lower() == "auto":
        console.print("[cyan]Checking GPU quota and live kernels on every Kaggle account…[/cyan]")
        picked = kz.pick_account()
        if not picked:
            _fail("No Kaggle account has a free GPU slot and quota left.")
        console.print(f"[green]AUTO picked[/green] [bold]{picked}[/bold]")
        name = picked
    try:
        return kz.get_account(name)
    except kz.KaggleError as exc:
        _fail(str(exc))
        raise  # unreachable; keeps type checkers happy


def _hours(q: Optional[dict]) -> str:
    if not q:
        return "—"
    tone = "red" if q["remaining"] <= 0 else "yellow" if q["remaining"] < 0.25 * (q["total"] or 1) else "green"
    return f"[{tone}]{q['remaining']:.1f}[/{tone}] / {q['total']:.0f} h"


@app.command("accounts")
def accounts_command() -> None:
    """Accounts in ~/.kaggle/zoo.json with their weekly GPU and TPU hours left."""
    if not kz.accounts():
        _fail(f"No Kaggle accounts. Add one with `m-gpux kaggle add <token>` (stored in {kz.ZOO_PATH}).")
    rows = kz.overview(with_kernels=False)
    table = Table(title="Kaggle accounts", header_style="bold cyan")
    for column in ("Account", "Team", "Credentials", "GPU left", "TPU left", "Resets (UTC)"):
        table.add_column(column)
    table.add_column("Note", max_width=36, overflow="ellipsis", no_wrap=True)
    for r in rows:
        quota = r.get("quota") or {}
        reset = (quota.get("gpu") or {}).get("refresh_at") or ""
        table.add_row(
            f"[bold]{r['name']}[/bold]" + (" [dim](default)[/dim]" if r["default"] else ""),
            r["team"] or "—",
            r["credentials"],
            _hours(quota.get("gpu")) if not r["error"] else f"[red]{r['error'][:40]}[/red]",
            _hours(quota.get("tpu")),
            reset[:16].replace("T", " "),
            r["note"] or "",
        )
    console.print(table)


@app.command("add")
def add_command(
    token: str = typer.Argument(..., help="An API token from kaggle.com/settings (KGAT_…)."),
    user: Optional[str] = typer.Option(None, "--user", help="Username, if it cannot be detected."),
    team: str = typer.Option("", "--team", help="Competition team, used to count submissions per team."),
    note: str = typer.Option("", "--note", help="Free-form note shown in listings."),
) -> None:
    """Register an account by its API token (the username is detected)."""
    try:
        name = kz.add_account(token, user=user, team=team, note=note)
    except kz.KaggleError as exc:
        _fail(str(exc))
    console.print(f"[green]Added Kaggle account[/green] [bold]{name}[/bold]")


@app.command("remove")
def remove_command(name: str = typer.Argument(..., help="Account to forget.")) -> None:
    """Forget an account (its token is deleted from zoo.json, not revoked)."""
    if not Confirm.ask(f"Remove Kaggle account [bold]{name}[/bold] from {kz.ZOO_PATH}?", default=False):
        raise typer.Exit(0)
    if not kz.remove_account(name):
        _fail(f"No account named {name!r}.")
    console.print(f"[green]Removed {name}.[/green]")


@app.command("status")
def status_command(
    competition: Optional[str] = typer.Option(None, "--comp", "-c", help="Also count today's submissions per team."),
    hours: int = typer.Option(14, "--hours", help="Look at kernels run in the last N hours."),
) -> None:
    """Live (running / queued) kernels and GPU hours per account; submissions today per team."""
    rows = kz.overview(hours=hours)
    table = Table(title=f"Kaggle kernels running or queued (run in the last {hours} h)", header_style="bold cyan")
    for column in ("Account", "Slots", "GPU left", "Live kernels"):
        table.add_column(column)
    for r in rows:
        live = r.get("live") or []
        if r["error"]:
            table.add_row(r["name"], "—", f"[red]{r['error'][:60]}[/red]", "")
            continue
        free = max(0, kz.GPU_SLOTS - len(live))
        table.add_row(
            r["name"],
            f"[{'green' if free else 'red'}]{free} free[/] / {kz.GPU_SLOTS}",
            _hours((r.get("quota") or {}).get("gpu")),
            "\n".join(f"{k['state']:<8} {k['ref']}" for k in live) or "[dim]none[/dim]",
        )
    console.print(table)
    if competition:
        _team_submissions(competition)


def _team_submissions(competition: str) -> None:
    teams: dict[str, kz.KaggleAccount] = {}
    for account in kz.accounts():
        teams.setdefault(account.team or account.name, account)
    table = Table(title=f"Submissions today (UTC) on {competition}", header_style="bold cyan")
    for column in ("Team", "Used", "Latest"):
        table.add_column(column)
    for team, account in teams.items():
        try:
            subs = kz.submissions_today(account, competition)
        except (kz.KaggleError, subprocess.TimeoutExpired) as exc:
            table.add_row(team, "[red]?[/red]", str(exc)[:60])
            continue
        latest = subs[0] if subs else None
        table.add_row(
            team,
            str(len(subs)),
            f"{latest['status']} {latest.get('public_score') or ''} {latest['description'][:40]}" if latest else "—",
        )
    console.print(table)


@app.command("free")
def free_command() -> None:
    """Accounts with a free GPU slot, most GPU hours left first."""
    rows = [r for r in kz.overview() if not r["error"]]
    rows.sort(key=lambda r: (r.get("quota") or {}).get("gpu", {}).get("remaining", 0), reverse=True)
    shown = 0
    for r in rows:
        free = kz.GPU_SLOTS - len(r.get("live") or [])
        gpu = (r.get("quota") or {}).get("gpu")
        if free > 0 and gpu and gpu["remaining"] > 0:
            note = r["note"] if len(r["note"]) <= 48 else r["note"][:47] + "…"
            console.print(f"[bold]{r['name']:<18}[/bold] {free} slot(s)  {_hours(gpu)}  [dim]{note}[/dim]")
            shown += 1
    if not shown:
        console.print("[yellow]No account has a free GPU slot with quota left.[/yellow]")


@app.command("run", context_settings=PASSTHROUGH)
def run_command(
    ctx: typer.Context,
    account: str = typer.Argument(..., help="Account name, or 'auto'."),
) -> None:
    """Run any kaggle command as ACCOUNT:  m-gpux kaggle run kietvo2207 -- kernels list --mine"""
    acc = _resolve(account)
    try:
        result = kz.run(acc, list(ctx.args), capture=False, timeout=None)
    except kz.KaggleError as exc:
        _fail(str(exc))
    raise typer.Exit(result.returncode)


def _wait(acc: kz.KaggleAccount, ref: str, poll: int, timeout_h: float) -> str:
    deadline = time.monotonic() + timeout_h * 3600
    last = None
    with console.status(f"Waiting for {ref}…") as status:
        while time.monotonic() < deadline:
            state = kz.kernel_status(acc, ref)
            if state != last:
                console.print(f"[dim]{time.strftime('%H:%M:%S')}[/dim] {ref}: [bold]{state}[/bold]")
                last = state
            if state in kz.DONE_STATES or state == "NOT_FOUND":
                return state
            status.update(f"{ref}: {state} (next check in {poll}s)")
            time.sleep(poll)
    return last or "UNKNOWN"


@app.command("push")
def push_command(
    folder: Path = typer.Argument(Path("."), help="Kernel folder with kernel-metadata.json."),
    account: Optional[str] = typer.Option(
        None, "--as", "-a", help="Account to push as, or 'auto'. Default: the owner in kernel-metadata.json."
    ),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait until the kernel finishes."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="With --wait: download the output here."),
    poll: int = typer.Option(30, "--poll", min=5, help="Seconds between status checks."),
    timeout_h: float = typer.Option(13.0, "--timeout-h", help="Give up waiting after this many hours."),
) -> None:
    """Push a kernel folder, optionally as another account (the folder itself is left unchanged)."""
    folder = folder.expanduser().resolve()
    try:
        owner = str(kz.read_kernel_metadata(folder)["id"]).split("/", 1)[0]
    except kz.KaggleError as exc:
        _fail(str(exc))
    # Without --as, push as the owner named in the metadata (or with the machine's credentials when there is no zoo).
    acc = _resolve(account or (owner if kz.load_zoo()["accounts"] else "default"))
    try:
        pushed = kz.push_kernel(acc, folder)
    except (kz.KaggleError, subprocess.TimeoutExpired) as exc:
        _fail(f"Push failed: {exc}")
    console.print(pushed["output"])
    console.print(
        f"[green]Pushed[/green] [bold]{pushed['ref']}[/bold]"
        + (f" version {pushed['version']}" if pushed["version"] else "")
        + f"  [dim]https://www.kaggle.com/code/{pushed['ref']}[/dim]"
    )
    if not wait:
        console.print(f"[dim]Follow it with: m-gpux kaggle watch {pushed['ref']} --as {acc.name}[/dim]")
        return
    _finish(acc, pushed["ref"], out or Path("kaggle_out") / pushed["ref"].split("/", 1)[1], poll, timeout_h)


def _finish(acc: kz.KaggleAccount, ref: str, out: Path, poll: int, timeout_h: float) -> None:
    state = _wait(acc, ref, poll, timeout_h)
    if state != "COMPLETE":
        _fail(f"{ref} ended as {state}; see https://www.kaggle.com/code/{ref}")
    console.print(f"[cyan]Downloading output to {out}…[/cyan]")
    result = kz.download_output(acc, ref, out)
    if result.returncode != 0:
        _fail("kaggle kernels output failed.")
    console.print(f"[green]Done.[/green] Output in [bold]{out}[/bold]")


@app.command("watch")
def watch_command(
    ref: str = typer.Argument(..., help="Kernel as owner/slug."),
    account: Optional[str] = typer.Option(None, "--as", "-a", help="Account that can see the kernel (default: owner)."),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Download the output here (default kaggle_out/<slug>)."
    ),
    poll: int = typer.Option(30, "--poll", min=5),
    timeout_h: float = typer.Option(13.0, "--timeout-h"),
) -> None:
    """Wait for a kernel to finish, then download its output."""
    if "/" not in ref:
        _fail("Give the kernel as owner/slug.")
    acc = _resolve(account or ref.split("/", 1)[0])
    _finish(acc, ref, out or Path("kaggle_out") / ref.split("/", 1)[1], poll, timeout_h)


class KagglePlugin(PluginBase):
    name = "kaggle"
    help = "Kaggle CLI across accounts: quota, live kernels, AUTO pushes and output downloads."
    rich_help_panel = "Other clouds"

    def register(self, root_app: typer.Typer) -> None:
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
