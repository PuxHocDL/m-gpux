"""Modal profile management.

This module centralises everything related to ``~/.modal.toml`` profiles so
that plugins (account, billing, hub, serve, video, vision, …) all share the
same logic.

The functions exposed here are the *public* API. Underscore-prefixed aliases
(``_select_profile``/``_activate_profile``/``_load_profiles``) are also
exported from :mod:`m_gpux.core` for backwards compatibility with code that
was originally written inside the monolithic ``hub.py``.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

import tomlkit

from m_gpux.core.console import console

MODAL_CONFIG_PATH = os.path.expanduser("~/.modal.toml")
MONTHLY_CREDIT = 30.0


# ─── Config I/O ────────────────────────────────────────────────


def load_config():
    """Load ``~/.modal.toml`` as a :class:`tomlkit.TOMLDocument`."""
    if not os.path.exists(MODAL_CONFIG_PATH):
        return tomlkit.document()
    with open(MODAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        return tomlkit.load(f)


def save_config(doc) -> None:
    """Persist a :class:`tomlkit.TOMLDocument` back to ``~/.modal.toml``."""
    with open(MODAL_CONFIG_PATH, "w", encoding="utf-8") as f:
        tomlkit.dump(doc, f)


def get_all_profiles() -> list[str]:
    """Return profile names defined in ``~/.modal.toml``."""
    if not os.path.exists(MODAL_CONFIG_PATH):
        return []
    with open(MODAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
    return list(doc.keys())


def load_profiles() -> list[tuple[str, bool]]:
    """Return ``[(name, is_active)]`` for each configured profile."""
    if not os.path.exists(MODAL_CONFIG_PATH):
        return []
    with open(MODAL_CONFIG_PATH, "r", encoding="utf-8") as f:
        doc = tomlkit.load(f)
    return [(name, bool(doc[name].get("active", False))) for name in doc]


# ─── Billing helpers ───────────────────────────────────────────


def _get_month_usage(token_id: str, token_secret: str) -> float:
    """Return the current month's usage cost in USD, or ``-1.0`` on failure."""
    try:
        from modal.billing import workspace_billing_report
        from modal.client import Client

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        client = Client.from_credentials(str(token_id), str(token_secret))
        reports = workspace_billing_report(start=month_start, resolution="d", client=client)
        return sum(float(r.get("cost", 0)) for r in reports)
    except Exception:
        return -1.0


def get_best_profile() -> tuple[Optional[str], float]:
    """Return ``(profile_name, remaining_credit)`` with the highest remaining
    monthly credit, or ``(None, 0.0)`` when no usable profile is found.
    """
    doc = load_config()
    best_name: Optional[str] = None
    best_remaining = 0.0
    for p in doc:
        token_id = doc[p].get("token_id")
        token_secret = doc[p].get("token_secret")
        if not token_id or not token_secret:
            continue
        used = _get_month_usage(token_id, token_secret)
        if used < 0:
            continue
        remaining = MONTHLY_CREDIT - used
        if remaining > best_remaining:
            best_remaining = remaining
            best_name = p
    return best_name, best_remaining


def get_all_balances() -> list[tuple[str, float, float]]:
    """Return ``[(profile, used, remaining)]`` sorted by ``remaining`` desc."""
    doc = load_config()
    results: list[tuple[str, float, float]] = []
    for p in doc:
        token_id = doc[p].get("token_id")
        token_secret = doc[p].get("token_secret")
        if not token_id or not token_secret:
            continue
        used = _get_month_usage(token_id, token_secret)
        if used < 0:
            results.append((p, -1, -1))
        else:
            results.append((p, used, max(MONTHLY_CREDIT - used, 0)))
    results.sort(key=lambda x: x[2], reverse=True)
    return results


# ─── Interactive selection ─────────────────────────────────────


def select_profile() -> Optional[str]:
    """Interactive picker. Returns selected profile name, or ``None``."""
    from m_gpux.core.ui import arrow_select  # local import: avoid cycles

    profiles = load_profiles()
    if not profiles:
        console.print("[yellow]No Modal profiles found. Run `m-gpux account add` to configure.[/yellow]")
        return None
    if len(profiles) == 1:
        name, _ = profiles[0]
        console.print(f"  Using profile: [bold cyan]{name}[/bold cyan]")
        return name

    console.print("\n[bold cyan]Step 0: Select Workspace / Profile[/bold cyan]")
    profile_options = [("AUTO", "Smart pick (most credit remaining)")]
    for name, is_active in profiles:
        marker = " (active)" if is_active else ""
        profile_options.append((name, f"Modal profile{marker}"))

    choice_idx = arrow_select(profile_options, title="Select Workspace", default=0)

    if choice_idx == 0:
        console.print("  [cyan]Scanning all accounts for best balance...[/cyan]")
        best_name, best_remaining = get_best_profile()
        if best_name is None:
            console.print("[bold red]Could not determine best profile. Pick manually.[/bold red]")
            return None
        console.print(f"  [bold green]Auto-selected: {best_name} (${best_remaining:.2f} remaining)[/bold green]")
        return best_name

    selected_name, _ = profiles[choice_idx - 1]
    console.print(f"  Using profile: [bold cyan]{selected_name}[/bold cyan]")
    return selected_name


def activate_profile(profile_name: str) -> None:
    """Activate the given profile via ``modal profile activate``."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    result = subprocess.run(
        ["modal", "profile", "activate", profile_name],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        console.print(
            f"[bold red]Failed to activate profile '{profile_name}': {result.stderr.strip()}[/bold red]"
        )


# ─── Token parsing ─────────────────────────────────────────────


def parse_modal_token_command(raw: str):
    """Parse a ``modal token set ...`` command string.

    Returns ``(token_id, token_secret, profile_or_None)`` or ``None`` when the
    command cannot be parsed.
    """
    token_id_match = re.search(r'--token-id\s+(\S+)', raw)
    token_secret_match = re.search(r'--token-secret\s+(\S+)', raw)
    profile_match = re.search(r'--profile[=\s]+(\S+)', raw)
    if token_id_match and token_secret_match:
        return (
            token_id_match.group(1),
            token_secret_match.group(1),
            profile_match.group(1) if profile_match else None,
        )
    return None
