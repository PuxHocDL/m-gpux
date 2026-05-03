"""Workload preset manager."""

from __future__ import annotations

import os

import typer
from rich.prompt import Prompt
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase
from m_gpux.core.runner import execute_modal_temp_script
from m_gpux.core.state import delete_preset, get_preset, list_presets, save_preset
from m_gpux.plugins.hub.plugin import (
    AVAILABLE_CPUS,
    AVAILABLE_GPUS,
    BASH_SCRIPT,
    JUPYTER_SCRIPT,
    _BASHRC,
    _STARSHIP_TOML,
    _TMUX_CONF,
    _TTYD_FLAGS,
    _activate_profile,
    _b64,
    _select_profile,
    _session_metadata,
    _workspace_volume_name,
)
from m_gpux.core.ui import arrow_select

app = typer.Typer(no_args_is_help=True)


def _script_from_preset(preset: dict, local_dir: str) -> tuple[str, str, str]:
    action = str(preset.get("action", "bash"))
    compute_spec = str(preset.get("compute_spec", 'cpu=4, memory=2048'))
    compute_label = str(preset.get("compute_label", "CPU"))
    pip_section = str(preset.get("pip_section", ""))
    exclude_patterns = list(preset.get("exclude_patterns", []))
    local_dir_escaped = os.path.abspath(local_dir).replace("\\", "/")
    workspace_volume = _workspace_volume_name(local_dir)

    if action == "jupyter":
        template = JUPYTER_SCRIPT
        app_name = "m-gpux-jupyter"
    else:
        template = BASH_SCRIPT
        app_name = "m-gpux-shell"

    script = (
        template.replace("{compute_spec}", compute_spec)
        .replace("{local_dir}", local_dir_escaped)
        .replace("{workspace_volume}", workspace_volume)
        .replace("{exclude_patterns}", repr(exclude_patterns))
        .replace("{pip_section}", pip_section)
        .replace("{bashrc_b64}", _b64(_BASHRC))
        .replace("{tmux_b64}", _b64(_TMUX_CONF))
        .replace("{starship_b64}", _b64(_STARSHIP_TOML))
        .replace("{ttyd_flags}", repr(_TTYD_FLAGS))
    )
    return script, workspace_volume, app_name


def run_preset_by_name(name: str, *, kind: str | None = None) -> None:
    preset = get_preset(name)
    if not preset:
        console.print(f"[red]Preset not found:[/red] {name}")
        raise typer.Exit(1)
    profile = preset.get("profile")
    if profile:
        _activate_profile(str(profile))
    local_dir = "."
    script, workspace_volume, app_name = _script_from_preset(preset, local_dir)
    compute_label = str(preset.get("compute_label", "compute"))
    action = str(preset.get("action", "bash"))
    execute_modal_temp_script(
        script,
        f"{action} preset '{name}' on {compute_label}",
        detach=True,
        session_metadata=_session_metadata(
            kind=kind or action,
            profile=str(profile or ""),
            compute_label=compute_label,
            workspace_volume=workspace_volume,
            local_dir=local_dir,
            app_name=app_name,
            preset=name,
        ),
    )


@app.command("list")
def list_command() -> None:
    """List saved workload presets."""
    presets = list_presets()
    if not presets:
        console.print("[yellow]No presets saved yet.[/yellow]")
        return
    table = Table(title="M-GPUX Workload Presets")
    table.add_column("Name", style="bold yellow")
    table.add_column("Action", style="cyan")
    table.add_column("Compute")
    table.add_column("Profile")
    for name, preset in presets.items():
        table.add_row(
            name,
            str(preset.get("action", "")),
            str(preset.get("compute_label", "")),
            str(preset.get("profile", "")),
        )
    console.print(table)


@app.command("show")
def show_command(name: str) -> None:
    """Show one preset."""
    preset = get_preset(name)
    if not preset:
        console.print(f"[red]Preset not found:[/red] {name}")
        raise typer.Exit(1)
    table = Table.grid(padding=(0, 2))
    for key in sorted(preset):
        table.add_row(f"[dim]{key}[/dim]", str(preset[key]))
    console.print(table)


@app.command("create")
def create_command() -> None:
    """Create a workload preset interactively."""
    name = Prompt.ask("Preset name")
    profile = _select_profile() or ""
    action_idx = arrow_select(
        [("bash", "Remote dev shell"), ("jupyter", "Jupyter Lab dev session")],
        title="Preset action",
        default=0,
    )
    action = "bash" if action_idx == 0 else "jupyter"

    compute_idx = arrow_select(
        [("GPU", "GPU acceleration"), ("CPU", "CPU-only")],
        title="Compute type",
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
        compute_spec = f"cpu={cores}, memory={memory}"
        compute_label = f"CPU ({cores} cores, {memory} MB)"
    else:
        gpu_values = list(AVAILABLE_GPUS.values())
        gpu_idx = arrow_select([(gpu, desc) for gpu, desc in gpu_values], title="GPU", default=1)
        gpu = gpu_values[gpu_idx][0]
        compute_spec = f'gpu="{gpu}"'
        compute_label = gpu

    packages = Prompt.ask("Comma-separated pip packages (blank for none)", default="")
    pip_section = ""
    if packages.strip():
        quoted = ", ".join(repr(p.strip()) for p in packages.split(",") if p.strip())
        pip_section = f".pip_install({quoted})"
    excludes = Prompt.ask(
        "Exclude patterns",
        default=".venv,venv,__pycache__,.git,node_modules,.mypy_cache,.pytest_cache,*.egg-info,.tox",
    )
    save_preset(
        name,
        {
            "action": action,
            "profile": profile,
            "compute_spec": compute_spec,
            "compute_label": compute_label,
            "pip_section": pip_section,
            "exclude_patterns": [p.strip() for p in excludes.split(",") if p.strip()],
        },
    )
    console.print(f"[green]Saved preset:[/green] [bold]{name}[/bold]")


@app.command("run")
def run_command(name: str) -> None:
    """Run a saved preset in the current workspace."""
    run_preset_by_name(name)


@app.command("delete")
def delete_command(name: str) -> None:
    """Delete a saved preset."""
    if delete_preset(name):
        console.print(f"[green]Deleted preset:[/green] {name}")
    else:
        console.print(f"[yellow]Preset not found:[/yellow] {name}")


class PresetPlugin(PluginBase):
    name = "preset"
    help = "Save and rerun common workload presets."
    rich_help_panel = "Workspace"

    def register(self, root_app):
        root_app.add_typer(app, name=self.name, help=self.help, rich_help_panel=self.rich_help_panel)
