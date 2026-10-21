"""Thin wrappers around the ``modal`` CLI subcommands m-gpux shells out to.

Modal changed several CLI defaults in 1.4.x, and every call site has to follow:

* ``modal app stop`` prompts for confirmation (1.4.2) — a captured or
  non-interactive subprocess would hang or abort, so we always pass ``--yes``.
* ``modal app logs`` prints the last 100 entries and exits (1.4.0) instead of
  streaming; ``--follow`` restores the streaming behaviour.
* ``modal deploy`` / ``modal app rollover`` accept ``--strategy rolling|recreate``.

Every call goes through :func:`modal_cmd` rather than a bare ``"modal"``: the
``modal`` script is often missing from ``PATH`` even though the package is
installed (``pipx install m-gpux`` only exposes ``m-gpux``; ``pip install
--user`` on macOS puts scripts in ``~/Library/Python/3.x/bin``; Windows puts
them in ``Scripts``), and a ``modal`` that *is* on ``PATH`` may belong to a
different, older interpreter.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Optional

DEPLOY_STRATEGIES = ("rolling", "recreate")

# Runs the modal CLI in this interpreter without `-m`, which would put the
# current directory first on sys.path and let a project file such as
# `click.py` or `grpc/` shadow modal's own dependencies.
_MODAL_BOOTSTRAP = (
    "import sys\n"
    "if sys.path and sys.path[0] in ('', '.'):\n"
    "    del sys.path[0]\n"
    "sys.argv[0] = 'modal'\n"
    "from modal.__main__ import main\n"
    "main()\n"
)


def _script_dirs() -> list[Path]:
    # Only directories this interpreter installs into: a user-scheme dir such
    # as ~/.local/bin is shared across Python versions and may hold a stale modal.
    dirs = [Path(sys.executable).parent] if sys.executable else []
    scripts = sysconfig.get_path("scripts")
    if scripts:
        dirs.append(Path(scripts))
    return dirs


@functools.lru_cache(maxsize=1)
def modal_executable() -> tuple[str, ...]:
    """Return the argv prefix that launches the modal CLI m-gpux depends on.

    Prefers the ``modal`` script installed next to this interpreter, then the
    in-process bootstrap (always the right modal version), and only then
    whatever ``modal`` is on ``PATH``.
    """
    override = os.environ.get("MGPUX_MODAL_CLI", "").strip()
    if override:
        return (override,)
    name = "modal.exe" if os.name == "nt" else "modal"
    for directory in _script_dirs():
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return (str(candidate),)
    if sys.executable:
        return (sys.executable, "-c", _MODAL_BOOTSTRAP)
    return (shutil.which("modal") or "modal",)


def modal_cmd(*args: str) -> list[str]:
    """Build a full modal CLI command line, e.g. ``modal_cmd("app", "list")``."""
    return [*modal_executable(), *(str(a) for a in args)]


def modal_env(profile: Optional[str] = None) -> dict[str, str]:
    """Return ``os.environ`` with ``MODAL_PROFILE`` pinned when *profile* is given."""
    env = {**os.environ}
    if profile:
        env["MODAL_PROFILE"] = str(profile)
    return env


def stop_app(
    app_ref: str,
    *,
    profile: Optional[str] = None,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Stop an app by name or ID without the interactive confirmation prompt."""
    return subprocess.run(
        modal_cmd("app", "stop", "--yes", str(app_ref)),
        capture_output=capture,
        text=True,
        env=modal_env(profile),
    )


def app_logs_cmd(
    app_ref: str,
    *,
    follow: bool = True,
    tail: Optional[int] = None,
    since: Optional[str] = None,
    search: Optional[str] = None,
    source: Optional[str] = None,
    timestamps: bool = False,
) -> list[str]:
    """Build a ``modal app logs`` command line."""
    cmd = modal_cmd("app", "logs", str(app_ref))
    if follow:
        cmd.append("--follow")
    if tail is not None:
        cmd += ["--tail", str(tail)]
    if since:
        cmd += ["--since", since]
    if search:
        cmd += ["--search", search]
    if source:
        cmd += ["--source", source]
    if timestamps:
        cmd.append("--timestamps")
    return cmd


def deploy_cmd(runner_file: str, strategy: Optional[str] = None) -> list[str]:
    """Build a ``modal deploy`` command line, optionally with a deployment strategy."""
    cmd = modal_cmd("deploy", runner_file)
    if strategy:
        cmd += ["--strategy", strategy]
    return cmd
