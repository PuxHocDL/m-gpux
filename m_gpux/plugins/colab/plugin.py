"""``m-gpux colab``: the Google Colab CLI across several Google accounts, with AUTO account selection."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.prompt import Confirm
from rich.table import Table

from m_gpux.core import colab
from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase

app = typer.Typer(
    help="Google Colab CLI across several Google accounts: compute units, runtimes, AUTO runs.",
    no_args_is_help=True,
)

PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}


def _fail(message: str, code: int = 1) -> None:
    console.print(f"[bold red]{message}[/bold red]")
    raise typer.Exit(code)


def _require_cli() -> None:
    if not colab.executable():
        _fail("The Colab CLI is not installed. Run: uv tool install google-colab-cli   (needs Python 3.12+)")


def _resolve(name: Optional[str]) -> str:
    """An account name, or AUTO (most compute units left) for None / 'auto'."""
    _require_cli()
    if not name or name.lower() == "auto":
        console.print("[cyan]Checking compute units on every Colab account…[/cyan]")
        picked = colab.pick_account()
        if not picked:
            _fail("No logged-in Colab account could report a balance. Log in with `m-gpux colab login <name>`.")
        console.print(f"[green]AUTO picked[/green] [bold]{picked}[/bold]")
        return picked
    if name not in colab.account_names():
        _fail(f"Unknown Colab account {name!r}. Accounts: {', '.join(colab.account_names())}")
    return name


def _passthrough(name: str, args: list[str]) -> None:
    try:
        result = colab.run(name, args, interactive=True, timeout=None)
    except colab.ColabError as exc:
        _fail(str(exc))
    raise typer.Exit(result.returncode)


@app.command("accounts")
def accounts_command() -> None:
    """Google accounts with their compute-unit balance, burn rate and live runtimes."""
    _require_cli()
    table = Table(title="Colab accounts", header_style="bold cyan")
    for column in ("Account", "Login", "Compute units", "Rate", "Runtimes"):
        table.add_column(column)
    for r in colab.overview():
        usage = r["usage"]
        if not r["logged_in"]:
            login, units = "[yellow]not logged in[/yellow]", f"[dim]m-gpux colab login {r['name']}[/dim]"
        elif r["error"]:
            login, units = "[red]error[/red]", f"[red]{r['error'][:60]}[/red]"
        else:
            login, units = "[green]ok[/green]", f"[bold]{usage['balance']:.2f}[/bold]"
        table.add_row(
            f"[bold]{r['name']}[/bold]",
            login,
            units,
            f"{usage['rate']:.2f}/h" if usage else "—",
            "\n".join(f"{s['name'] or '?'} · {s['hardware']}" for s in r["sessions"]) or ("0" if usage else "—"),
        )
    console.print(table)


@app.command("login")
def login_command(
    name: str = typer.Argument(..., help="Account name, e.g. 'work' (use 'main' for your normal home)."),
) -> None:
    """Log a Google account in (opens Google's OAuth flow in this terminal)."""
    _require_cli()
    try:
        home = colab.create_account_home(name)
    except colab.ColabError as exc:
        _fail(str(exc))
    console.print(f"[cyan]Logging in '{name}' (token kept under {home}). Follow the prompts below.[/cyan]")
    # `usage` needs a token, so it runs the OAuth flow when there is none, then shows the balance.
    _passthrough(name, ["usage"])


@app.command("remove")
def remove_command(name: str = typer.Argument(..., help="Extra account to delete.")) -> None:
    """Delete an extra account's home folder and its saved login."""
    if name == colab.MAIN:
        _fail("The 'main' account is your normal home folder; it cannot be removed here.")
    home = colab.home_of(name)
    if not home.is_dir():
        _fail(f"No Colab account named {name!r}.")
    if not Confirm.ask(f"Delete [bold]{home}[/bold] (its Colab login and session state)?", default=False):
        raise typer.Exit(0)
    shutil.rmtree(home)
    console.print(f"[green]Removed {name}.[/green]")


@app.command("run", context_settings=PASSTHROUGH)
def run_command(
    ctx: typer.Context,
    script: Path = typer.Argument(..., help="Local Python script (or notebook) to run on a fresh VM."),
    gpu: Optional[str] = typer.Option(None, "--gpu", help=f"One of {', '.join(colab.GPUS)}."),
    tpu: Optional[str] = typer.Option(None, "--tpu", help=f"One of {', '.join(colab.TPUS)}."),
    high_mem: bool = typer.Option(False, "--high-mem", help="High-RAM machine shape (Colab Pro)."),
    keep: bool = typer.Option(False, "--keep", help="Keep the VM after the script ends."),
    account: Optional[str] = typer.Option(None, "--as", "-a", help="Account to run as, or 'auto' (default)."),
) -> None:
    """Run a script on a fresh Colab VM, then release it. Extra arguments go to the script."""
    if gpu and gpu not in colab.GPUS:
        _fail(f"--gpu must be one of {', '.join(colab.GPUS)}")
    if tpu and tpu not in colab.TPUS:
        _fail(f"--tpu must be one of {', '.join(colab.TPUS)}")
    if not script.is_file():
        _fail(f"{script} does not exist.")
    name = _resolve(account)
    args = ["run"]
    if gpu:
        args += ["--gpu", gpu]
    if tpu:
        args += ["--tpu", tpu]
    if high_mem:
        args.append("--high-mem")
    if keep:
        args.append("--keep")
    _passthrough(name, [*args, str(script), *ctx.args])


@app.command("new")
def new_command(
    session: str = typer.Option(..., "--session", "-s", help="Name for the runtime."),
    gpu: Optional[str] = typer.Option(None, "--gpu", help=f"One of {', '.join(colab.GPUS)}."),
    tpu: Optional[str] = typer.Option(None, "--tpu", help=f"One of {', '.join(colab.TPUS)}."),
    high_mem: bool = typer.Option(False, "--high-mem", help="High-RAM machine shape (Colab Pro)."),
    account: Optional[str] = typer.Option(None, "--as", "-a", help="Account, or 'auto' (default)."),
) -> None:
    """Start a named runtime you can `exec`, `upload` and `download` against (via `m-gpux colab as`)."""
    name = _resolve(account)
    args = ["new", "-s", session]
    if gpu:
        args += ["--gpu", gpu]
    if tpu:
        args += ["--tpu", tpu]
    if high_mem:
        args.append("--high-mem")
    console.print(f"[dim]Then: m-gpux colab as {name} -- exec -s {session} -f script.py[/dim]")
    _passthrough(name, args)


@app.command("sessions")
def sessions_command(
    account: Optional[str] = typer.Option(None, "--as", "-a", help="Only this account (default: all)."),
) -> None:
    """Live runtimes on every logged-in account."""
    _require_cli()
    names = [account] if account else [a["name"] for a in colab.accounts() if a["logged_in"]]
    table = Table(title="Colab runtimes", header_style="bold cyan")
    for column in ("Account", "Session", "Hardware", "Shape", "Variant"):
        table.add_column(column)
    shown = 0
    for name in names:
        try:
            for s in colab.sessions(name):
                table.add_row(name, s["name"] or "[dim]?[/dim]", s["hardware"], s["shape"], s["variant"])
                shown += 1
        except (colab.ColabError, subprocess.TimeoutExpired) as exc:
            table.add_row(name, f"[red]{str(exc)[:60]}[/red]", "", "", "")
    console.print(table if shown or names else "[yellow]No logged-in accounts.[/yellow]")


@app.command("stop")
def stop_command(
    session: str = typer.Argument(..., help="Runtime name."),
    account: str = typer.Option(colab.MAIN, "--as", "-a", help="Account that owns it."),
) -> None:
    """Stop a runtime and release its VM."""
    _passthrough(_resolve(account), ["stop", "-s", session])


@app.command("as", context_settings=PASSTHROUGH)
def as_command(
    ctx: typer.Context,
    account: str = typer.Argument(..., help="Account name, or 'auto'."),
) -> None:
    """Run any colab command as ACCOUNT:  m-gpux colab as work -- exec -s trainer -f train.py"""
    _passthrough(_resolve(account), list(ctx.args))


class ColabPlugin(PluginBase):
    name = "colab"
    help = "Google Colab CLI across accounts: compute units, runtimes, AUTO runs (works on Windows)."
    rich_help_panel = "Other clouds"

    def register(self, root_app: typer.Typer) -> None:
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
