"""Thin wrappers around the ``modal`` CLI subcommands m-gpux shells out to.

Modal changed several CLI defaults in 1.4.x, and every call site has to follow:

* ``modal app stop`` prompts for confirmation (1.4.2) — a captured or
  non-interactive subprocess would hang or abort, so we always pass ``--yes``.
* ``modal app logs`` prints the last 100 entries and exits (1.4.0) instead of
  streaming; ``--follow`` restores the streaming behaviour.
* ``modal deploy`` / ``modal app rollover`` accept ``--strategy rolling|recreate``.
"""

from __future__ import annotations

import os
import subprocess
from typing import Optional

DEPLOY_STRATEGIES = ("rolling", "recreate")


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
        ["modal", "app", "stop", "--yes", str(app_ref)],
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
    cmd = ["modal", "app", "logs", str(app_ref)]
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
    cmd = ["modal", "deploy", runner_file]
    if strategy:
        cmd += ["--strategy", strategy]
    return cmd
