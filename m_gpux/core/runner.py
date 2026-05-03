"""Helpers for executing generated Modal scripts.

This module hosts ``execute_modal_temp_script`` (the runner used by hub/host
plugins) and ``scan_apps_across_profiles`` (used by the ``stop`` plugin to
discover m-gpux apps across all Modal profiles).

The runner intentionally keeps console output minimal: by default it prints a
small summary of the generated ``modal_runner.py`` (path, app name, GPU,
timeout) and waits for the user to press Enter to run. Pass ``v`` at the
prompt to view the full source, or set ``MGPUX_VERBOSE=1`` to always show it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Optional

from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.metrics import FUNCTIONS as _METRICS_FUNCTIONS
from m_gpux.core.profiles import get_all_profiles
from m_gpux.core.state import save_session, update_session


def _summarize_runner(content: str, runner_file: str) -> Panel:
    """Return a compact summary panel describing the generated script."""
    info: dict[str, str] = {"file": runner_file}

    m = re.search(r'modal\.App\(["\']([^"\']+)', content)
    if m:
        info["app"] = m.group(1)

    # Look only inside the @app.function(...) decorator so we don't pick up
    # `timeout=10` from the metrics helper's nvidia-smi subprocess calls.
    func_block = re.search(r'@app\.function\(([^)]*)\)', content, re.DOTALL)
    func_args = func_block.group(1) if func_block else content

    m = re.search(r'gpu\s*=\s*["\']([^"\']+)', func_args)
    if m:
        info["gpu"] = m.group(1)
    else:
        cpu = re.search(r'cpu\s*=\s*([0-9]+)', func_args)
        mem = re.search(r'memory\s*=\s*([0-9]+)', func_args)
        if cpu:
            info["cpu"] = cpu.group(1) + " cores" + (
                f" / {mem.group(1)} MB" if mem else ""
            )

    m = re.search(r'timeout\s*=\s*([^\),\s]+)', func_args)
    if m:
        info["timeout"] = m.group(1)

    pip = re.search(r'pip_install_from_requirements\(["\']([^"\']+)', content)
    if pip:
        info["deps"] = "from " + os.path.basename(pip.group(1))
    else:
        pip2 = re.search(r'pip_install\(([^)]+)\)', content)
        if pip2:
            pkgs = [p.strip().strip('"\'') for p in pip2.group(1).split(",") if p.strip()]
            if pkgs:
                info["deps"] = ", ".join(pkgs[:5]) + (" …" if len(pkgs) > 5 else "")

    grid = Table.grid(padding=(0, 2))
    for k, v in info.items():
        grid.add_row(f"[dim]{k:>8}[/dim]", f"[bold]{v}[/bold]")

    return Panel(grid, title="Generated Modal Runner", border_style="cyan", expand=False)


def execute_modal_temp_script(
    content: str,
    description: str,
    detach: bool = False,
    session_metadata: dict | None = None,
) -> None:
    """Materialise *content* as ``modal_runner.py``, summarise it, then execute.

    The string ``# __METRICS__`` inside *content* is replaced with the metrics
    helper functions (so generated scripts can call ``_print_metrics`` and
    ``_monitor_metrics``).
    """
    content = content.replace("# __METRICS__", _METRICS_FUNCTIONS)
    runner_file = "modal_runner.py"

    with open(runner_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    console.print()
    console.print(_summarize_runner(content, runner_file))

    verbose = os.environ.get("MGPUX_VERBOSE", "").strip() in ("1", "true", "yes")
    if verbose:
        console.print(Syntax(content, "python", theme="monokai", line_numbers=True))

    console.print(
        f"[dim]Edit [bold]{runner_file}[/bold] freely before running "
        f"(change GPU/CPU, deps, timeout…). Set MGPUX_VERBOSE=1 to always print the full code.[/dim]"
    )

    while True:
        choice = Prompt.ask(
            "[bold cyan][Enter][/bold cyan] run  •  [bold cyan]v[/bold cyan] view code  •  [bold cyan]e[/bold cyan] open in editor  •  [bold cyan]c[/bold cyan] cancel",
            default="",
        ).strip().lower()
        if choice in ("", "r", "run"):
            break
        if choice in ("c", "cancel", "q", "quit"):
            console.print("[yellow]Execution cancelled.[/yellow]")
            return
        if choice in ("v", "view", "show"):
            console.print(Syntax(content, "python", theme="monokai", line_numbers=True))
            continue
        if choice in ("e", "edit", "open"):
            editor = os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "nano")
            try:
                subprocess.run([editor, runner_file])
            except Exception as exc:
                console.print(f"[red]Could not launch editor ({editor}): {exc}[/red]")
            # Re-read possibly edited file
            with open(runner_file, "r", encoding="utf-8") as rf:
                content = rf.read()
            continue

    cmd = ["modal", "run", runner_file]
    if detach:
        cmd.insert(2, "--detach")

    console.print(f"[bold green]Starting {description}…[/bold green]")
    if detach:
        console.print(
            "[dim]Detached: container keeps running if you close this terminal. "
            "Reopen the tunnel URL to reconnect.[/dim]"
        )

    result = None
    try:
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        result = subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        if detach:
            console.print("\n[green]Disconnected locally. The remote container is still running.[/green]")
        else:
            console.print(f"\n[yellow]Execution of {description} interrupted.[/yellow]")

    def _read_app_name() -> Optional[str]:
        try:
            with open(runner_file, "r", encoding="utf-8") as rf:
                for line in rf:
                    if 'modal.App(' in line:
                        m = re.search(r'modal\.App\(["\']([^"\']+)', line)
                        if m:
                            return m.group(1)
                        break
        except Exception:
            return None
        return None

    tracked_session_id: str | None = None
    if detach and session_metadata and (result is None or result.returncode == 0):
        app_name = _read_app_name()
        session = {
            **session_metadata,
            "description": description,
            "app_name": app_name or session_metadata.get("app_name"),
            "state": "running",
        }
        saved = save_session(session)
        tracked_session_id = str(saved["id"])
        console.print(
            f"[green]Tracked session:[/green] [bold]{tracked_session_id}[/bold] "
            f"([cyan]{saved.get('app_name', 'unknown')}[/cyan])"
        )

    stop_choice = Prompt.ask(
        "[bold cyan]Stop the Modal app to release GPU?[/bold cyan]",
        choices=["y", "n"], default="n" if detach else "y",
    )
    if stop_choice.lower() == "y":
        app_name = _read_app_name()
        if app_name:
            subprocess.run(["modal", "app", "stop", app_name], capture_output=True)
            console.print(f"[green]App '{app_name}' stopped. GPU released.[/green]")
            if tracked_session_id:
                update_session(tracked_session_id, state="stopped")
            elif session_metadata and session_metadata.get("id"):
                update_session(str(session_metadata["id"]), state="stopped")
        else:
            console.print("[yellow]Could not determine app name. Stop manually: modal app stop <name>[/yellow]")

    del_choice = Prompt.ask(
        f"[bold cyan]Delete {runner_file}?[/bold cyan]",
        choices=["y", "n"], default="y",
    )
    if del_choice.lower() == "y":
        try:
            os.remove(runner_file)
        except OSError:
            pass


def scan_apps_across_profiles() -> list[tuple[str, str, str, str]]:
    """Scan every configured profile for running m-gpux apps.

    Returns a list of ``(profile, app_id, description, state)`` tuples.
    """
    profiles = get_all_profiles()
    found: list[tuple[str, str, str, str]] = []
    for profile in profiles:
        try:
            result = subprocess.run(
                ["modal", "app", "list", "--env", "main", "--json"],
                capture_output=True, text=True, timeout=15,
                env={**os.environ, "MODAL_PROFILE": profile},
            )
            if result.returncode != 0:
                continue
            apps = json.loads(result.stdout) if result.stdout.strip() else []
            for a in apps:
                desc = a.get("Description", a.get("description", ""))
                state = a.get("State", a.get("state", ""))
                app_id = a.get("App ID", a.get("app_id", ""))
                if desc.startswith("m-gpux") and state in ("deployed", "running"):
                    found.append((profile, app_id, desc, state))
        except Exception:
            continue
    return found
