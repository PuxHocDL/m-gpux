"""``dev`` plugin — dev boxes on Modal Sandboxes (plus the classic web terminal)."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase
from m_gpux.core.runner import execute_modal_temp_script
from m_gpux.core.ui import arrow_select
from m_gpux.core.ignore import to_recursive_ignore
from m_gpux.plugins.hub.plugin import (
    AVAILABLE_CPUS,
    AVAILABLE_GPUS,
    BASH_SCRIPT,
    _BASHRC,
    _STARSHIP_TOML,
    _TMUX_CONF,
    _TTYD_FLAGS,
    _activate_profile,
    _b64,
    _maybe_save_workload_preset,
    _select_profile,
    _session_metadata,
    _workspace_volume_name,
)
from m_gpux.plugins.preset.plugin import run_preset_by_name
from m_gpux.core.gpus import ask_gpu_count
from m_gpux.core.images import pick_published_image
from m_gpux.core.modal_cli import modal_env
from m_gpux.core.pricing import cpu_hourly, fmt_hourly, gpu_hourly
from m_gpux.plugins.dev import devbox


def _choose_compute() -> tuple[str, str]:
    compute_idx = arrow_select(
        [("GPU", "GPU acceleration"), ("CPU", "CPU-only")],
        title="Dev container compute",
        default=0,
    )
    if compute_idx == 1:
        cpu_keys = list(AVAILABLE_CPUS.keys())
        cpu_idx = arrow_select(
            [(f"{AVAILABLE_CPUS[k][0]} cores", AVAILABLE_CPUS[k][2]) for k in cpu_keys],
            title="CPU",
            default=3,
        )
        cores, memory, _ = AVAILABLE_CPUS[cpu_keys[cpu_idx]]
        return f"cpu={cores}, memory={memory}", f"CPU ({cores} cores, {memory} MB)"

    gpu_values = list(AVAILABLE_GPUS.values())
    gpu_idx = arrow_select([(gpu, desc) for gpu, desc in gpu_values], title="GPU", default=1)
    gpu = gpu_values[gpu_idx][0]
    return f'gpu="{gpu}"', gpu


def _prompt_pip_section() -> str:
    if os.path.exists("requirements.txt"):
        use_req = Prompt.ask(
            "[green]Found requirements.txt.[/green] Install dependencies from it?",
            choices=["y", "n"],
            default="y",
        )
        if use_req == "y":
            req_path = os.path.abspath("requirements.txt").replace("\\", "/")
            return f'.pip_install_from_requirements("{req_path}")'
    packages = Prompt.ask("Extra pip packages (comma-separated, blank for none)", default="")
    if not packages.strip():
        return ""
    quoted = ", ".join(repr(p.strip()) for p in packages.split(",") if p.strip())
    return f".pip_install({quoted})"


def _prompt_excludes() -> list[str]:
    excludes = Prompt.ask(
        "Exclude patterns",
        default=".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox,dist,build",
    )
    return [p.strip() for p in excludes.split(",") if p.strip()]


def web_command() -> None:
    """Launch the classic browser-terminal dev container for the current folder."""

    profile = _select_profile()
    if profile is None:
        raise typer.Exit(1)
    _activate_profile(profile)

    compute_spec, compute_label = _choose_compute()
    python_version = "3.12"
    pip_section = _prompt_pip_section()
    exclude_patterns = _prompt_excludes()
    preset_name = _maybe_save_workload_preset(
        action="dev",
        profile=profile,
        compute_spec=compute_spec,
        compute_label=compute_label,
        python_version=python_version,
        pip_section=pip_section,
        exclude_patterns=exclude_patterns,
    )

    local_dir_escaped = os.path.abspath(".").replace("\\", "/")
    workspace_volume = _workspace_volume_name(".")
    script = (
        BASH_SCRIPT.replace("{compute_spec}", compute_spec)
        .replace("{python_version}", python_version)
        .replace("{local_dir}", local_dir_escaped)
        .replace("{workspace_volume}", workspace_volume)
        .replace("{exclude_patterns}", repr(to_recursive_ignore(exclude_patterns)))
        .replace("{pip_section}", pip_section)
        .replace("{bashrc_b64}", _b64(_BASHRC))
        .replace("{tmux_b64}", _b64(_TMUX_CONF))
        .replace("{starship_b64}", _b64(_STARSHIP_TOML))
        .replace("{ttyd_flags}", repr(_TTYD_FLAGS))
    )
    execute_modal_temp_script(
        script,
        f"Dev Container on {compute_label}",
        detach=True,
        session_metadata=_session_metadata(
            kind="dev",
            profile=profile,
            compute_label=compute_label,
            python_version=python_version,
            workspace_volume=workspace_volume,
            local_dir=".",
            app_name="m-gpux-shell",
            preset=preset_name,
        ),
    )


# ─── Dev boxes (Sandbox-based) ────────────────────────────────

app = typer.Typer(
    help=(
        "Persistent dev boxes on Modal Sandboxes: SSH / VS Code Remote, "
        "pause & resume without losing installs, two-way file sync."
    ),
    invoke_without_command=True,
)


def _box_or_exit(name: Optional[str]) -> tuple[str, dict]:
    try:
        resolved = devbox.resolve_name(name)
    except KeyError as e:
        console.print(f"[red]{e.args[0]}[/red]")
        raise typer.Exit(1)
    return resolved, devbox.load_boxes()[resolved]


def _hourly(box: dict) -> float:
    total = cpu_hourly(float(box.get("cpu") or 0.125), int(box.get("memory") or 1024), sandbox=True)
    return total + (gpu_hourly(box["gpu"]) or 0.0 if box.get("gpu") else 0.0)


def _running_or_exit(box: dict):
    sb = devbox.get_sandbox(box)
    if sb is None:
        console.print(f"[yellow]Dev box is {box.get('state', 'stopped')}. Run `m-gpux dev resume`.[/yellow]")
        raise typer.Exit(1)
    return sb


def _print_connect_help(name: str, box: dict) -> None:
    alias = devbox.ssh_host_alias(name)
    expires = time.strftime("%H:%M", time.localtime(box["started_at"] + box["timeout_hours"] * 3600))
    lines = [f"[bold green]Dev box '{name}' is running[/bold green] on {box['compute_label']} "
             f"· {fmt_hourly(_hourly(box))}"]
    if box.get("ssh", True):
        lines += [
            f"  ssh:      [bold cyan]ssh {alias}[/bold cyan]   (or `m-gpux dev ssh`)",
            f"  VS Code:  [bold cyan]m-gpux dev code[/bold cyan]   (Remote-SSH → {alias})",
        ]
    lines += [
        "  shell:    [bold cyan]m-gpux dev shell[/bold cyan]",
        "  sync:     [bold cyan]m-gpux dev sync push[/bold cyan] / [bold cyan]pull[/bold cyan]",
        f"  [yellow]Stops automatically at {expires}.[/yellow] Run [bold]m-gpux dev pause[/bold] before then "
        "to keep your changes (installs + files) for later.",
    ]
    console.print(Panel("\n".join(lines), border_style="green"))


def _pick_box_compute() -> tuple[Optional[str], float, int, str]:
    """Returns (gpu or None, cpu cores, memory MB, label)."""
    idx = arrow_select(
        [("GPU", "GPU dev box"), ("CPU", "CPU-only — note: Sandbox CPU costs ~3× Function CPU")],
        title="Dev box compute",
        default=0,
    )
    if idx == 1:
        keys = list(AVAILABLE_CPUS.keys())
        opts = []
        for k in keys:
            cores, mem, _ = AVAILABLE_CPUS[k]
            opts.append((f"{cores} cores", f"{mem // 1024 or 0.5} GB · {fmt_hourly(cpu_hourly(cores, mem, sandbox=True))}"))
        cores, mem, _ = AVAILABLE_CPUS[keys[arrow_select(opts, title='CPU', default=2)]]
        return None, float(cores), int(mem), f"CPU ({cores} cores)"
    gpu_values = list(AVAILABLE_GPUS.values())
    gpu_idx = arrow_select([(g, d) for g, d in gpu_values], title="GPU", default=1)
    gpu = ask_gpu_count(gpu_values[gpu_idx][0])
    return gpu, 4.0, 16384, gpu


@app.callback()
def _dev_root(
    ctx: typer.Context,
    preset: Optional[str] = typer.Option(None, "--preset", "-p", help="Run a saved preset (classic web terminal)"),
) -> None:
    if preset:
        run_preset_by_name(preset, kind="dev")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        ctx.invoke(up_command)


@app.command("up")
def up_command(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Box name (default: this folder's name)"),
    image: Optional[str] = typer.Option(None, "--image", help="Published image to start from (m-gpux image build)"),
    hours: float = typer.Option(12, "--hours", help=f"Auto-stop after this many hours (max {devbox.MAX_TIMEOUT_HOURS})"),
    ssh: bool = typer.Option(True, "--ssh/--no-ssh", help="Run sshd for ssh / VS Code Remote-SSH"),
    lock_ip: bool = typer.Option(False, "--lock-ip", help="Only accept connections from your current public IP"),
    upload: bool = typer.Option(True, "--upload/--no-upload", help="Copy this folder into /workspace"),
) -> None:
    """Create a dev box for the current folder and connect to it."""
    box_name = devbox.slugify(name or Path.cwd().name)
    existing = devbox.load_boxes().get(box_name)
    if existing and existing.get("state") in ("running", "paused"):
        verb = "resume" if existing["state"] == "paused" else "ssh"
        console.print(f"[yellow]Dev box '{box_name}' already exists ({existing['state']}). "
                      f"Use `m-gpux dev {verb}` or `m-gpux dev down` first.[/yellow]")
        raise typer.Exit(1)
    if not 0 < hours <= devbox.MAX_TIMEOUT_HOURS:
        console.print(f"[red]--hours must be between 0 and {devbox.MAX_TIMEOUT_HOURS}.[/red]")
        raise typer.Exit(1)

    profile = _select_profile()
    if profile is None:
        raise typer.Exit(1)
    gpu, cpu, memory, label = _pick_box_compute()
    python_version = "3.12"
    if image is None:
        image = pick_published_image(profile)
    requirements = None
    if image is None and upload and os.path.exists("requirements.txt"):
        if Prompt.ask("[green]Found requirements.txt.[/green] Install it into the box?",
                      choices=["y", "n"], default="y") == "y":
            requirements = os.path.abspath("requirements.txt")
    excludes = _prompt_excludes() if upload else []

    allow_cidr = None
    if lock_ip:
        ip = devbox.public_ip()
        if ip is None:
            console.print("[red]Could not detect your public IP; drop --lock-ip or try again.[/red]")
            raise typer.Exit(1)
        allow_cidr = f"{ip}/32" if ":" not in ip else f"{ip}/128"

    box = {
        "profile": profile, "gpu": gpu, "cpu": cpu, "memory": memory, "compute_label": label,
        "python": python_version, "image": image, "ssh": ssh, "allow_cidr": allow_cidr,
        "timeout_hours": hours, "local_dir": os.path.abspath(".") if upload else None,
        "excludes": excludes, "created_at": time.time(),
    }
    console.print(f"\n[bold]Creating dev box '{box_name}'[/bold] · {label} · {fmt_hourly(_hourly(box))} "
                  f"· auto-stop in {hours:g}h")
    try:
        client = devbox.client_for(profile)
        img = devbox.build_image(
            client, base_image=image, python_version=python_version,
            local_dir=box["local_dir"], excludes=excludes, requirements=requirements,
        )
        devbox.create_sandbox(client, box_name, img, box)
    except Exception as e:
        console.print(f"[red]Could not start the dev box: {e}[/red]")
        raise typer.Exit(1)
    box["last_push"] = time.time()
    devbox.save_box(box_name, box)
    _print_connect_help(box_name, box)


@app.command("list")
def list_command() -> None:
    """List dev boxes and their state."""
    boxes = devbox.load_boxes()
    if not boxes:
        console.print("[dim]No dev boxes. Create one with `m-gpux dev up`.[/dim]")
        return
    table = Table(title="Dev boxes")
    for col in ("Name", "State", "Account", "Compute", "Cost", "Auto-stop", "Folder"):
        table.add_column(col)
    for name, box in sorted(boxes.items()):
        state = box.get("state", "?")
        if state == "running" and devbox.get_sandbox(box) is None:
            state = "expired"  # timed out or stopped outside m-gpux
            box["state"] = state
            devbox.save_box(name, box)
        stop_at = "-"
        if state == "running":
            stop_at = time.strftime("%m-%d %H:%M", time.localtime(box["started_at"] + box["timeout_hours"] * 3600))
        color = {"running": "green", "paused": "cyan", "expired": "red"}.get(state, "white")
        table.add_row(name, f"[{color}]{state}[/{color}]", box.get("profile", ""), box.get("compute_label", ""),
                      fmt_hourly(_hourly(box)) if state == "running" else "$0 (paused)" if state == "paused" else "-",
                      stop_at, box.get("local_dir") or "-")
    console.print(table)


@app.command("ssh")
def ssh_command(name: Optional[str] = typer.Argument(None)) -> None:
    """Open an SSH session to a dev box."""
    name, box = _box_or_exit(name)
    _running_or_exit(box)
    subprocess.run(["ssh", devbox.ssh_host_alias(name)])


@app.command("code")
def code_command(name: Optional[str] = typer.Argument(None)) -> None:
    """Open the dev box in VS Code (Remote-SSH)."""
    name, box = _box_or_exit(name)
    _running_or_exit(box)
    code = shutil.which("code")
    if not code:
        console.print(f"[yellow]`code` not on PATH. In VS Code: Remote-SSH → Connect to Host → "
                      f"{devbox.ssh_host_alias(name)}[/yellow]")
        raise typer.Exit(1)
    subprocess.run([code, "--remote", f"ssh-remote+{devbox.ssh_host_alias(name)}", devbox.WORKDIR])
    console.print(f"[green]Opening {devbox.ssh_host_alias(name)}:{devbox.WORKDIR} in VS Code.[/green]")


@app.command("shell")
def shell_command(name: Optional[str] = typer.Argument(None)) -> None:
    """Open a terminal in the dev box (Modal shell; over SSH on Windows)."""
    name, box = _box_or_exit(name)
    sb = _running_or_exit(box)
    if os.name == "nt":
        # `modal shell` is not supported on Windows; SSH is.
        if not box.get("ssh", True):
            console.print("[red]`modal shell` doesn't support Windows and this box has no SSH "
                          "(created with --no-ssh). Recreate it with SSH enabled.[/red]")
            raise typer.Exit(1)
        subprocess.run(["ssh", devbox.ssh_host_alias(name)])
        return
    subprocess.run(["modal", "shell", sb.object_id], env=modal_env(box["profile"]))


@app.command("pause")
def pause_command(
    name: Optional[str] = typer.Argument(None),
    keep_days: int = typer.Option(30, "--keep-days", help="How long Modal keeps the snapshot"),
) -> None:
    """Snapshot the whole box and stop it — no compute is billed while paused."""
    name, box = _box_or_exit(name)
    sb = _running_or_exit(box)
    console.print(f"[cyan]Snapshotting '{name}' (installed packages + files)...[/cyan]")
    try:
        snapshot = sb.snapshot_filesystem(timeout=900, ttl=keep_days * 86400)
    except Exception as e:
        console.print(f"[red]Snapshot failed, box left running: {e}[/red]")
        raise typer.Exit(1)
    sb.terminate()
    box.update(state="paused", snapshot_id=snapshot.object_id, sandbox_id=None,
               paused_at=time.time(), snapshot_expires=time.time() + keep_days * 86400)
    devbox.save_box(name, box)
    console.print(f"[green]Paused '{name}'. Resume any time in the next {keep_days} days: "
                  f"[bold]m-gpux dev resume {name}[/bold][/green]")


@app.command("resume")
def resume_command(
    name: Optional[str] = typer.Argument(None),
    hours: Optional[float] = typer.Option(None, "--hours", help="Auto-stop after this many hours"),
) -> None:
    """Start a paused (or expired) box again from its last snapshot."""
    import modal

    name, box = _box_or_exit(name)
    if devbox.get_sandbox(box) is not None:
        console.print(f"[green]'{name}' is already running.[/green]")
        _print_connect_help(name, box)
        return
    if not box.get("snapshot_id"):
        console.print(f"[red]'{name}' has no snapshot (it expired before being paused). "
                      f"Recreate it with `m-gpux dev down {name}` then `m-gpux dev up`.[/red]")
        raise typer.Exit(1)
    if hours:
        box["timeout_hours"] = min(hours, devbox.MAX_TIMEOUT_HOURS)
    console.print(f"[cyan]Resuming '{name}' on {box['compute_label']}...[/cyan]")
    try:
        client = devbox.client_for(box["profile"])
        image = modal.Image.from_id(box["snapshot_id"], client=client)
        devbox.create_sandbox(client, name, image, box)
    except Exception as e:
        console.print(f"[red]Could not resume: {e}[/red]")
        raise typer.Exit(1)
    devbox.save_box(name, box)
    _print_connect_help(name, box)


@app.command("sync")
def sync_command(
    direction: str = typer.Argument(..., help="push (local → box) or pull (box → local)"),
    name: Optional[str] = typer.Argument(None),
    all_files: bool = typer.Option(False, "--all", help="push: send every file, not only files changed since last push"),
    to: Optional[str] = typer.Option(None, "--to", help="pull: destination folder (default: the box's source folder)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="pull: overwrite local files without asking"),
) -> None:
    """Copy files between this machine and the box's /workspace."""
    if direction not in ("push", "pull"):
        console.print("[red]Direction must be 'push' or 'pull'.[/red]")
        raise typer.Exit(1)
    name, box = _box_or_exit(name)
    sb = _running_or_exit(box)
    excludes = box.get("excludes") or devbox.DEFAULT_EXCLUDES
    if direction == "push":
        src = box.get("local_dir") or os.path.abspath(".")
        since = 0.0 if all_files else float(box.get("last_push") or 0.0)
        started = time.time()
        n = devbox.push(sb, src, excludes, since=since)
        box["last_push"] = started
        devbox.save_box(name, box)
        console.print(f"[green]Pushed {n} file(s) from {src} → {devbox.WORKDIR}.[/green]")
        return
    dest = to or box.get("local_dir") or os.path.abspath(".")
    if not yes and Prompt.ask(f"Overwrite files in [bold]{dest}[/bold] with the box's copies?",
                              choices=["y", "n"], default="n") != "y":
        raise typer.Exit()
    os.makedirs(dest, exist_ok=True)
    n = devbox.pull(sb, dest, excludes)
    console.print(f"[green]Pulled {n} file(s) → {dest}.[/green]")


@app.command("down")
def down_command(
    name: Optional[str] = typer.Argument(None),
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask for confirmation"),
) -> None:
    """Delete a dev box: stop it and forget its snapshot."""
    name, box = _box_or_exit(name)
    if not yes and Prompt.ask(f"Delete dev box '{name}'? Unsynced changes are lost.",
                              choices=["y", "n"], default="n") != "y":
        raise typer.Exit()
    sb = devbox.get_sandbox(box)
    if sb is not None:
        sb.terminate()
    devbox.remove_ssh_config(name)
    devbox.delete_box(name)
    console.print(f"[green]Deleted dev box '{name}'.[/green]")


app.command("web", help="Classic dev container: browser terminal (ttyd) via a Modal Function.")(web_command)


class DevPlugin(PluginBase):
    name = "dev"
    help = "Dev boxes on GPUs: SSH / VS Code Remote, pause & resume, file sync."
    rich_help_panel = "Workspace"

    def register(self, root_app):
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
