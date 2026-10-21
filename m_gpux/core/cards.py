"""Profile cards: one box per Modal account, used by ``account list``, the
launch-time profile picker and the interactive menu.

Each card shows the account name, whether it is active, what m-gpux may still
spend this month (free credit or budget left) and a usage bar. Balances come
from Modal's billing API, which takes a moment per account, so the picker
draws the cards immediately and fills the numbers in when they arrive.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from rich import box
from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from m_gpux.core.console import console
from m_gpux.core.ui import _plain_select, _read_key

CARD_WIDTH = 34


@dataclass
class Usage:
    """Month-to-date spend for one account. ``used < 0`` means the lookup failed."""

    used: float
    cap: float
    left: float
    has_budget: bool


@dataclass
class Picked:
    """Result of :func:`pick_profile`. ``auto`` marks the AUTO card; then *name*
    is the account it chose (empty if none had credit) and *left* its balance."""

    name: str
    auto: bool = False
    left: Optional[float] = None


def load_usages() -> dict[str, Usage]:
    """Query every account's spend in parallel (accounts without a token are skipped)."""
    from m_gpux.core.budget import budget_for, load_budgets
    from m_gpux.core.profiles import MONTHLY_CREDIT, get_all_balances

    budgets = load_budgets()
    out: dict[str, Usage] = {}
    for name, used, left in get_all_balances():
        limit = budget_for(name, budgets)
        out[name] = Usage(
            used=used, cap=MONTHLY_CREDIT if limit is None else limit, left=left, has_budget=limit is not None
        )
    return out


def _usage_bar(used: float, cap: float, width: int, style: str) -> Text:
    filled = 0 if cap <= 0 else round(width * min(max(used / cap, 0.0), 1.0))
    return Text.assemble(("━" * filled, style), ("━" * (width - filled), "grey30"))


def _money_style(left: float) -> str:
    if left < 5:
        return "bold red"
    if left < 15:
        return "bold yellow"
    return "bold green"


def profile_card(
    name: str,
    active: bool,
    usage: Optional[Usage],
    *,
    loading: bool = False,
    selected: bool = False,
    width: int = CARD_WIDTH,
) -> Panel:
    """A single account card. *usage* is ``None`` when unknown (no token, or not loaded)."""
    inner = width - 4
    title = Text(f" {name} ", style="bold white" if selected else "bold")
    if active:
        title.append("● active ", style="bold green")

    if loading:
        body: RenderableType = Group(Text("checking balance…", style="dim"), Text(""), Text(""))
    elif usage is None:
        body = Group(Text("no usage data", style="dim"), Text("token missing or unreadable", style="dim"), Text(""))
    elif usage.used < 0:
        body = Group(
            Text("usage unavailable", style="yellow"), Text("billing API didn't answer", style="dim"), Text("")
        )
    else:
        kind = "budget" if usage.has_budget else "credit"
        body = Group(
            Text.assemble((f"${usage.left:,.2f}", _money_style(usage.left)), (" left this month", "dim")),
            _usage_bar(
                usage.used, usage.cap, inner, "red" if usage.left < 5 else ("yellow" if usage.left < 15 else "green")
            ),
            Text(f"${usage.used:,.2f} used of ${usage.cap:,.0f} {kind}", style="dim"),
        )
    return Panel(
        body,
        title=title,
        title_align="left",
        width=width,
        box=box.HEAVY if selected else box.ROUNDED,
        border_style="bold cyan" if selected else ("green" if active else "grey50"),
        padding=(0, 1),
    )


def auto_card(best: Optional[tuple[str, float]], *, loading: bool, selected: bool, width: int = CARD_WIDTH) -> Panel:
    """The AUTO choice: whichever account has the most left."""
    if loading:
        pick = Text("checking accounts…", style="dim")
    elif best:
        pick = Text.assemble(("→ ", "dim"), (best[0], "bold"), ("  ", ""), (f"${best[1]:,.2f}", _money_style(best[1])))
    else:
        pick = Text("no account has credit left", style="yellow")
    return Panel(
        Group(Text("Most credit / budget left", style="dim"), pick, Text("")),
        title=Text(" ✦ AUTO ", style="bold magenta" if not selected else "bold white"),
        title_align="left",
        width=width,
        box=box.HEAVY if selected else box.ROUNDED,
        border_style="bold cyan" if selected else "magenta",
        padding=(0, 1),
    )


def _columns_for(count: int, width: int = CARD_WIDTH) -> int:
    return max(1, min(count, (console.width - 2) // (width + 1)))


def card_grid(cards: list[RenderableType], columns: Optional[int] = None) -> Table:
    columns = columns or _columns_for(len(cards))
    grid = Table.grid(padding=(0, 1))
    for _ in range(columns):
        grid.add_column()
    for i in range(0, len(cards), columns):
        row = cards[i : i + columns]
        grid.add_row(*row, *([""] * (columns - len(row))))
    return grid


def card_select(
    render: Callable[[int, bool], RenderableType],
    count: int,
    *,
    title: str,
    labels: list[tuple[str, str]],
    default: int = 0,
    changed: Optional[threading.Event] = None,
) -> Optional[int]:
    """Arrow-key picker over a grid of cards. Returns the index, or ``None`` if cancelled.

    *render(i, selected)* draws card *i*. When *changed* is set (e.g. balances
    arrived in a background thread) the grid is redrawn. Without a terminal it
    falls back to a numbered prompt using *labels*.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return _plain_select(labels, title=title, default=default)

    cursor = max(0, min(default, count - 1))
    columns = _columns_for(count)
    lock = threading.Lock()
    done = threading.Event()

    def frame() -> RenderableType:
        hint = Text("  ←↑↓→ move · Enter select · q cancel", style="dim")
        return Group(
            Text(f"  {title}", style="bold"), hint, card_grid([render(i, i == cursor) for i in range(count)], columns)
        )

    with Live(frame(), console=console, auto_refresh=False, transient=True) as live:

        def watch() -> None:
            while not done.is_set():
                if changed is not None and changed.wait(0.2):
                    changed.clear()
                    with lock:
                        live.update(frame(), refresh=True)
                elif changed is None:
                    return

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            while True:
                key = _read_key(cbreak=os.name != "nt")
                if key in ("enter", "\r", "\n"):
                    break
                if key in ("q", "esc"):
                    cursor = -1
                    break
                step = {"left": -1, "right": 1, "up": -columns, "down": columns}.get(key, 0)
                if key in ("h", "a"):
                    step = -1
                elif key in ("l", "d"):
                    step = 1
                elif key in ("k", "w"):
                    step = -columns
                elif key in ("j", "s"):
                    step = columns
                if step:
                    cursor = (cursor + step) % count
                    with lock:
                        live.update(frame(), refresh=True)
        finally:
            done.set()

    if cursor < 0:
        console.print("  [yellow]Cancelled.[/yellow]")
        return None
    label, desc = labels[cursor]
    console.print(f"  [green]❯ {label}[/green]  [dim]{desc}[/dim]")
    return cursor


def pick_profile(*, include_auto: bool, title: str = "Select an account") -> Optional[Picked]:
    """Card picker over every configured profile; ``None`` if cancelled or there are none."""
    from m_gpux.core.profiles import load_profiles

    profiles = load_profiles()
    if not profiles:
        return None
    usages: dict[str, Usage] = {}
    loaded = threading.Event()
    changed = threading.Event()

    def fetch() -> None:
        try:
            usages.update(load_usages())
        except Exception:
            pass
        loaded.set()
        changed.set()

    # The plain no-terminal list shows no balances; only AUTO needs them there.
    if include_auto or (sys.stdin.isatty() and sys.stdout.isatty()):
        threading.Thread(target=fetch, daemon=True).start()

    offset = 1 if include_auto else 0

    def best() -> Optional[tuple[str, float]]:
        ok = [(n, u.left) for n, u in usages.items() if u.used >= 0 and u.left > 0]
        return max(ok, key=lambda x: x[1]) if ok else None

    def render(i: int, selected: bool) -> RenderableType:
        if include_auto and i == 0:
            return auto_card(best(), loading=not loaded.is_set(), selected=selected)
        name, active = profiles[i - offset]
        return profile_card(name, active, usages.get(name), loading=not loaded.is_set(), selected=selected)

    labels = ([("AUTO", "most credit / budget left")] if include_auto else []) + [
        (name, "active" if active else "") for name, active in profiles
    ]
    active_idx = next((i for i, (_, active) in enumerate(profiles) if active), 0)
    default = 0 if include_auto else active_idx
    idx = card_select(render, len(labels), title=title, labels=labels, default=default, changed=changed)
    if idx is None:
        return None
    if include_auto and idx == 0:
        loaded.wait(timeout=60)
        pick = best()
        return Picked(name=pick[0], auto=True, left=pick[1]) if pick else Picked(name="", auto=True)
    return Picked(name=profiles[idx - offset][0])
