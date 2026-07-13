"""Interactive arrow-key menu selector for terminal UI."""

import sys
import os
from typing import List, Optional, Tuple
from rich.console import Console

_console = Console()


def _read_key() -> str:
    """Read a single keypress. Returns 'up', 'down', 'enter', or the character."""
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):  # special key prefix on Windows
            ch2 = msvcrt.getwch()
            if ch2 == "H":
                return "up"
            elif ch2 == "P":
                return "down"
            elif ch2 == "K":
                return "left"
            elif ch2 == "M":
                return "right"
            return ""
        elif ch == "\r":
            return "enter"
        elif ch == "\x1b":
            return "esc"
        elif ch == "\x03":
            raise KeyboardInterrupt
        return ch
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        return "up"
                    elif ch3 == "B":
                        return "down"
                    elif ch3 == "D":
                        return "left"
                    elif ch3 == "C":
                        return "right"
                return "esc"
            elif ch in ("\r", "\n"):
                return "enter"
            elif ch == "\x03":
                raise KeyboardInterrupt
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _plain_select(
    options: List[Tuple[str, str]],
    title: str = "Select an option",
    default: int = 0,
) -> int:
    """Non-tty fallback for arrow_select: numbered prompt read from stdin.

    Used when no real console is attached (piped/redirected stdout), e.g.
    when driving m-gpux from a script or CI. Accepts a 1-based number or
    the option label (case-insensitive) on stdin; empty/EOF/invalid input
    falls back to `default`.
    """
    _console.print(f"  [bold]{title}[/bold]  [dim](non-interactive: enter a number or press Enter for default)[/dim]")
    for i, (label, desc) in enumerate(options):
        marker = "*" if i == default else " "
        if desc:
            _console.print(f"  {marker} {i + 1}) {label:<18} {desc}")
        else:
            _console.print(f"  {marker} {i + 1}) {label}")

    try:
        raw = input("  > ").strip()
    except EOFError:
        raw = ""

    if not raw:
        chosen = default
    elif raw.isdigit() and 1 <= int(raw) <= len(options):
        chosen = int(raw) - 1
    else:
        matches = [i for i, (label, _) in enumerate(options) if label.lower() == raw.lower()]
        chosen = matches[0] if matches else default

    label, desc = options[chosen]
    if desc:
        _console.print(f"  [green]✓ {label}[/green]  [dim]{desc}[/dim]")
    else:
        _console.print(f"  [green]✓ {label}[/green]")
    return chosen


def arrow_select(
    options: List[Tuple[str, str]],
    title: str = "Select an option",
    default: int = 0,
    pointer: str = "❯",
    highlight_style: str = "bold cyan",
) -> int:
    """
    Show an interactive arrow-key menu. Returns the selected index.

    Args:
        options: List of (label, description) tuples.
        title: Header text shown above the menu.
        default: Default selected index (0-based).
        pointer: Character shown next to the selected item.
        highlight_style: Rich style for the selected row.

    Returns:
        Selected index (0-based).
    """
    cursor = max(0, min(default, len(options) - 1))

    try:
        term_lines = os.get_terminal_size().lines
    except OSError:
        return _plain_select(options, title=title, default=cursor)

    # Calculate visible window for long lists
    max_visible = min(len(options), term_lines - 4)

    def _render():
        """Render the menu to terminal."""
        lines = []
        # Scrolling window
        if len(options) <= max_visible:
            start, end = 0, len(options)
        else:
            half = max_visible // 2
            start = max(0, cursor - half)
            end = start + max_visible
            if end > len(options):
                end = len(options)
                start = end - max_visible

        for i in range(start, end):
            label, desc = options[i]
            if i == cursor:
                if desc:
                    lines.append(f"  [{highlight_style}]{pointer} {label:<18} {desc}[/{highlight_style}]")
                else:
                    lines.append(f"  [{highlight_style}]{pointer} {label}[/{highlight_style}]")
            else:
                if desc:
                    lines.append(f"  [dim]  {label:<18} {desc}[/dim]")
                else:
                    lines.append(f"  [dim]  {label}[/dim]")

        if len(options) > max_visible:
            if start > 0:
                lines.insert(0, "  [dim]  ↑ more above[/dim]")
            if end < len(options):
                lines.append("  [dim]  ↓ more below[/dim]")

        # Clear previous render and draw
        # Move up to overwrite: title + options + possible scroll indicators
        output = "\n".join(lines)
        return output

    _console.print(f"  [bold]{title}[/bold]  [dim](↑↓ navigate, Enter to select)[/dim]")

    # Initial render
    rendered = _render()
    _console.print(rendered)
    prev_line_count = rendered.count("\n") + 1

    while True:
        key = _read_key()
        if key == "up":
            cursor = (cursor - 1) % len(options)
        elif key == "down":
            cursor = (cursor + 1) % len(options)
        elif key == "enter":
            # Final render with selection
            sys.stdout.write(f"\033[{prev_line_count}A\033[J")
            sys.stdout.flush()
            label, desc = options[cursor]
            if desc:
                _console.print(f"  [green]{pointer} {label}[/green]  [dim]{desc}[/dim]")
            else:
                _console.print(f"  [green]{pointer} {label}[/green]")
            return cursor
        elif key == "esc":
            # ESC = confirm current selection
            sys.stdout.write(f"\033[{prev_line_count}A\033[J")
            sys.stdout.flush()
            label, desc = options[cursor]
            if desc:
                _console.print(f"  [green]{pointer} {label}[/green]  [dim]{desc}[/dim]")
            else:
                _console.print(f"  [green]{pointer} {label}[/green]")
            return cursor
        else:
            continue

        # Re-render
        sys.stdout.write(f"\033[{prev_line_count}A\033[J")
        sys.stdout.flush()
        rendered = _render()
        _console.print(rendered)
        prev_line_count = rendered.count("\n") + 1
