"""Auto dev container command."""

from __future__ import annotations

import os
from typing import Optional

import typer
from rich.prompt import Prompt

from m_gpux.core.console import console
from m_gpux.core.plugin import PluginBase
from m_gpux.core.runner import execute_modal_temp_script
from m_gpux.core.ui import arrow_select
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


def dev_command(
    preset: Optional[str] = typer.Option(None, "--preset", "-p", help="Run a saved preset as a dev container"),
) -> None:
    """Launch a VS Code-like Modal dev container for the current folder."""
    if preset:
        run_preset_by_name(preset, kind="dev")
        return

    profile = _select_profile()
    if profile is None:
        raise typer.Exit(1)
    _activate_profile(profile)

    compute_spec, compute_label = _choose_compute()
    pip_section = _prompt_pip_section()
    exclude_patterns = _prompt_excludes()
    preset_name = _maybe_save_workload_preset(
        action="dev",
        profile=profile,
        compute_spec=compute_spec,
        compute_label=compute_label,
        pip_section=pip_section,
        exclude_patterns=exclude_patterns,
    )

    local_dir_escaped = os.path.abspath(".").replace("\\", "/")
    workspace_volume = _workspace_volume_name(".")
    script = (
        BASH_SCRIPT.replace("{compute_spec}", compute_spec)
        .replace("{local_dir}", local_dir_escaped)
        .replace("{workspace_volume}", workspace_volume)
        .replace("{exclude_patterns}", repr(exclude_patterns))
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
            workspace_volume=workspace_volume,
            local_dir=".",
            app_name="m-gpux-shell",
            preset=preset_name,
        ),
    )


class DevPlugin(PluginBase):
    name = "dev"
    help = "Launch a persistent VS Code-like Modal dev container."
    rich_help_panel = "Workspace"

    def register(self, root_app):
        root_app.command(
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )(dev_command)
