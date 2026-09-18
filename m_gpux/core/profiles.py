"""Modal profile management.

This module centralises everything related to ``~/.modal.toml`` profiles so
that plugins (account, billing, hub, serve, …) all share the
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
from typing import Optional

import tomlkit

from m_gpux.core.console import console

MODAL_CONFIG_PATH = os.path.expanduser("~/.modal.toml")
MONTHLY_CREDIT = 30.0
# Below this many dollars of spendable credit, a manually picked account
# triggers an offer to switch to the best account instead.
LOW_CREDIT_THRESHOLD = 1.0


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
    from m_gpux.core.billing import month_usage

    return month_usage(token_id, token_secret)


def get_best_profile() -> tuple[Optional[str], float]:
    """Return ``(profile_name, spendable)`` for the account with the most money
    m-gpux may still spend this month (free credit, capped by any budget), or
    ``(None, 0.0)`` when no usable profile is found.
    """
    best_name: Optional[str] = None
    best_remaining = 0.0
    for name, used, remaining in get_all_balances():
        if used >= 0 and remaining > best_remaining:
            best_name, best_remaining = name, remaining
    return best_name, best_remaining


def _profile_usage(doc, profile: str) -> Optional[float]:
    token_id = doc[profile].get("token_id")
    token_secret = doc[profile].get("token_secret")
    if not token_id or not token_secret:
        return None
    return _get_month_usage(token_id, token_secret)


def get_all_balances() -> list[tuple[str, float, float]]:
    """Return ``[(profile, used, spendable)]`` sorted by ``spendable`` desc.

    ``spendable`` is the free credit left, or the budget left when a budget is
    set (see :mod:`m_gpux.core.budget`). ``used == -1`` marks a failed lookup.
    Accounts are queried in parallel.
    """
    from concurrent.futures import ThreadPoolExecutor

    from m_gpux.core.budget import load_budgets, spendable

    doc = load_config()
    budgets = load_budgets()
    names = list(doc.keys())
    with ThreadPoolExecutor(max_workers=min(8, max(len(names), 1))) as pool:
        usages = list(pool.map(lambda n: _profile_usage(doc, n), names))

    results: list[tuple[str, float, float]] = []
    for name, used in zip(names, usages):
        if used is None:
            continue
        if used < 0:
            results.append((name, -1, -1))
        else:
            results.append((name, used, spendable(name, used, MONTHLY_CREDIT, budgets)))
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def check_profile_credit(profile: str) -> Optional[str]:
    """Warn when *profile* is nearly out of spendable credit and offer to switch.

    Returns the profile to use (possibly a different one), or ``None`` if the
    user declines both. Set ``MGPUX_SKIP_CREDIT_CHECK=1`` to skip the lookup.
    """
    if os.environ.get("MGPUX_SKIP_CREDIT_CHECK", "").strip() in ("1", "true", "yes"):
        return profile
    from rich.prompt import Prompt

    from m_gpux.core.budget import budget_for, spendable

    doc = load_config()
    if profile not in doc:
        return profile
    used = _profile_usage(doc, profile)
    if used is None or used < 0:
        return profile
    left = spendable(profile, used, MONTHLY_CREDIT)
    if left >= LOW_CREDIT_THRESHOLD:
        return profile

    limit = budget_for(profile)
    reason = f"budget ${limit:.2f}" if limit is not None else f"${MONTHLY_CREDIT:.0f} monthly credit"
    console.print(
        f"  [bold yellow]'{profile}' has only ${left:.2f} left this month "
        f"(${used:.2f} used of {reason}).[/bold yellow]"
    )
    choice = Prompt.ask(
        "  [bold cyan]s[/bold cyan] switch to the account with the most credit  •  "
        "[bold cyan]c[/bold cyan] continue anyway  •  [bold cyan]q[/bold cyan] quit",
        choices=["s", "c", "q"], default="s",
    )
    if choice == "q":
        return None
    if choice == "c":
        return profile
    console.print("  [cyan]Scanning all accounts for best balance...[/cyan]")
    best_name, best_remaining = get_best_profile()
    if best_name is None or best_name == profile:
        console.print("  [yellow]No account has more credit left — keeping the current one.[/yellow]")
        return profile
    console.print(f"  [bold green]Switched to {best_name} (${best_remaining:.2f} left)[/bold green]")
    return best_name


# ─── Interactive selection ─────────────────────────────────────


def select_profile() -> Optional[str]:
    """Interactive picker. Returns selected profile name, or ``None``."""
    if os.environ.get("MODAL_PROFILE"):
        return os.environ.get("MODAL_PROFILE")
    env_profile = os.environ.get("MGPUX_PROFILE", "").strip()
    from m_gpux.core.ui import arrow_select  # local import: avoid cycles

    profiles = load_profiles()
    if not profiles:
        console.print("[yellow]No Modal profiles found. Run `m-gpux account add` to configure.[/yellow]")
        return None
    if len(profiles) == 1:
        name, _ = profiles[0]
        console.print(f"  Using profile: [bold cyan]{name}[/bold cyan]")
        return name
    if env_profile:
        if env_profile in [name for name, _ in profiles]:
            console.print(f"  Using profile from MGPUX_PROFILE: [bold cyan]{env_profile}[/bold cyan]")
            return env_profile
        console.print(f"[yellow]MGPUX_PROFILE={env_profile!r} not found, falling back to picker.[/yellow]")

    console.print("\n[bold cyan]Step 0: Select Workspace / Profile[/bold cyan]")
    profile_options = [("AUTO", "Smart pick (most credit / budget remaining)")]
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
    return check_profile_credit(selected_name)


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
