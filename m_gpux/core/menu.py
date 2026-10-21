"""Interactive menu for the whole CLI.

``m-gpux`` with no arguments (in a terminal) and ``m-gpux menu`` open an
arrow-key menu: pick a workflow, then a command. Arguments a command requires
are filled in with pickers built from local state (profiles, presets,
sessions, API keys, images) or a short prompt, so nothing has to be typed from
memory. The chosen command then runs exactly as if it had been typed, and the
menu comes back when it finishes.
"""

from __future__ import annotations

from typing import Callable, Optional, Union

import click
from rich.prompt import FloatPrompt, Prompt

from m_gpux.core.console import console
from m_gpux.core.ui import arrow_select

# A step is a literal argv token or a picker returning the tokens to append
# (``None`` cancels the command and returns to the menu).
Step = Union[str, Callable[[], Optional[list[str]]]]

BACK = "← Back"


# ─── Pickers ──────────────────────────────────────────────────


def _choose(title: str, options: list[tuple[str, str]], values: Optional[list[str]] = None) -> Optional[str]:
    labels = [*options, (BACK, "")]
    idx = arrow_select(labels, title=title)
    if idx == len(options):
        return None
    return (values or [label for label, _ in options])[idx]


def _profile() -> Optional[list[str]]:
    from m_gpux.core.cards import pick_profile
    from m_gpux.core.profiles import load_profiles

    if not load_profiles():
        console.print("[yellow]No Modal profiles yet — add one with Accounts → Add.[/yellow]")
        return None
    picked = pick_profile(include_auto=False, title="Profile")
    return [picked.name] if picked else None


def _account_option() -> Optional[list[str]]:
    from m_gpux.core.profiles import get_all_profiles

    options = [("All accounts", "the default for every account without its own value")]
    options += [(name, "") for name in get_all_profiles()]
    values = ["*", *get_all_profiles()]
    choice = _choose("Which account?", options, values)
    if choice is None:
        return None
    return [] if choice == "*" else ["--account", choice]


def _preset() -> Optional[list[str]]:
    from m_gpux.core.state import list_presets

    presets = list_presets()
    if not presets:
        console.print("[yellow]No presets yet — create one with Presets → Create.[/yellow]")
        return None
    options = [(name, str(p.get("description") or p.get("action") or "")) for name, p in sorted(presets.items())]
    name = _choose("Preset", options)
    return [name] if name else None


def _session() -> Optional[list[str]]:
    from m_gpux.core.state import list_sessions

    sessions = list_sessions()
    if not sessions:
        console.print("[yellow]No tracked sessions yet — launch something from the GPU Hub first.[/yellow]")
        return None
    sessions = sorted(sessions, key=lambda s: str(s.get("created_at") or ""), reverse=True)
    options = [
        (
            str(s.get("id")),
            " · ".join(str(v) for v in (s.get("app_name"), s.get("gpu"), s.get("state"), s.get("profile")) if v),
        )
        for s in sessions
    ]
    session_id = _choose("Session", options)
    return [session_id] if session_id else None


def _api_key() -> Optional[list[str]]:
    from m_gpux.plugins.serve.plugin import _load_keys

    keys = _load_keys()
    if not keys:
        console.print("[yellow]No API keys yet — create one with Model serving → Create API key.[/yellow]")
        return None
    options = [(k["name"], "active" if k.get("active", True) else "revoked") for k in keys]
    name = _choose("API key", options)
    return [name] if name else None


def _image() -> Optional[list[str]]:
    from m_gpux.core.images import list_images

    images = list_images()
    if not images:
        console.print("[yellow]No images published with m-gpux yet.[/yellow]")
        return None
    options = [(name, ", ".join(meta.get("profiles", []))) for name, meta in sorted(images.items())]
    name = _choose("Image", options)
    return [name] if name else None


def _text(question: str, default: str = "") -> Callable[[], Optional[list[str]]]:
    def ask() -> Optional[list[str]]:
        value = Prompt.ask(f"[bold cyan]{question}[/bold cyan]", default=default or None) or ""
        value = value.strip()
        return [value] if value else None

    return ask


def _optional_text(flag: str, question: str) -> Callable[[], Optional[list[str]]]:
    def ask() -> Optional[list[str]]:
        value = (Prompt.ask(f"[bold cyan]{question}[/bold cyan] [dim](Enter to skip)[/dim]", default="") or "").strip()
        return [flag, value] if value else []

    return ask


def _amount() -> Optional[list[str]]:
    value = FloatPrompt.ask("[bold cyan]Monthly limit in USD[/bold cyan]", default=30.0)
    return [f"{value:g}"]


def _pick(title: str, options: list[tuple[str, str]]) -> Callable[[], Optional[list[str]]]:
    def ask() -> Optional[list[str]]:
        value = _choose(title, options)
        return [value] if value else None

    return ask


def _flag(question: str, flag: str) -> Callable[[], Optional[list[str]]]:
    def ask() -> Optional[list[str]]:
        choice = _choose(question, [("No", ""), ("Yes", flag)])
        if choice is None:
            return None
        return [flag] if choice == "Yes" else []

    return ask


# ─── Menu tree ────────────────────────────────────────────────

# (label, description, argv steps)
Item = tuple[str, str, list[Step]]

MENU: list[tuple[str, str, list[Item]]] = [
    (
        "GPU Hub",
        "Jupyter, scripts, browser shell or vLLM on any GPU",
        [
            ("Open GPU Hub", "Pick compute, runtime and workload", ["hub"]),
            ("Probe hardware", "Report GPU, CPU, memory and disk of a container", ["load", "probe"]),
        ],
    ),
    (
        "Dev boxes",
        "SSH / VS Code boxes that pause and resume",
        [
            ("Create / start", "Dev box for the current folder", ["dev", "up"]),
            ("List", "Dev boxes and their state", ["dev", "list"]),
            ("Open in VS Code", "Remote-SSH into /workspace", ["dev", "code"]),
            ("SSH", "Open an SSH session", ["dev", "ssh"]),
            ("Shell", "Terminal in the box (SSH on Windows)", ["dev", "shell"]),
            ("Pause", "Snapshot everything and stop billing", ["dev", "pause"]),
            ("Resume", "Boot from the last snapshot", ["dev", "resume"]),
            (
                "Sync files",
                "Push to or pull from /workspace",
                [
                    "dev",
                    "sync",
                    _pick("Direction", [("push", "local → box"), ("pull", "box → local")]),
                ],
            ),
            ("Delete", "Stop the box and forget its snapshot", ["dev", "down"]),
            ("Web terminal", "Classic browser terminal (ttyd)", ["dev", "web"]),
        ],
    ),
    (
        "Sessions",
        "Tracked Hub and dev launches",
        [
            ("List", "Every tracked session", ["sessions", "list"]),
            ("Show", "One session's details", ["sessions", "show", _session]),
            ("Open URL", "Reopen its URL in the browser", ["sessions", "open", _session]),
            ("Logs", "Stream its Modal logs", ["sessions", "logs", _session]),
            ("Pull workspace", "Download its workspace Volume", ["sessions", "pull", _session]),
            ("Stop", "Stop its Modal app", ["sessions", "stop", _session]),
            ("Forget", "Remove it from the local list", ["sessions", "forget", _session]),
            ("Stop all apps", "Stop running m-gpux apps and release GPUs", ["stop"]),
        ],
    ),
    (
        "Presets",
        "Saved workloads you can replay",
        [
            ("Run", "Replay a preset here", ["preset", "run", _preset]),
            ("List", "Saved presets", ["preset", "list"]),
            ("Show", "One preset's settings", ["preset", "show", _preset]),
            ("Create", "Save a new preset", ["preset", "create"]),
            ("Delete", "Remove a preset", ["preset", "delete", _preset]),
        ],
    ),
    (
        "Web hosting",
        "Persistent URLs for web apps",
        [
            ("ASGI app", "FastAPI / Starlette", ["host", "asgi"]),
            ("WSGI app", "Flask / Django", ["host", "wsgi"]),
            ("Static site", "A folder of HTML, JS and CSS", ["host", "static"]),
        ],
    ),
    (
        "Model serving",
        "OpenAI-compatible LLM endpoint",
        [
            ("Deploy", "Serve a Hugging Face model with vLLM", ["serve", "deploy"]),
            ("Warm up", "Trigger the cold start now", ["serve", "warmup"]),
            ("Dashboard", "Live metrics in the terminal", ["serve", "dashboard"]),
            ("Logs", "Stream server logs", ["serve", "logs"]),
            ("Restart", "Fresh containers, same code", ["serve", "restart"]),
            ("Stop", "Stop the API server", ["serve", "stop"]),
            ("List API keys", "", ["serve", "keys", "list"]),
            ("Create API key", "", ["serve", "keys", "create"]),
            ("Show API key", "Reveal a full key", ["serve", "keys", "show", _api_key]),
            ("Revoke API key", "", ["serve", "keys", "revoke", _api_key]),
        ],
    ),
    (
        "Docker Compose",
        "Run docker-compose.yml on Modal",
        [
            ("Check", "Analyze the compose file", ["compose", "check"]),
            ("Up (subprocess)", "All services in one Modal app", ["compose", "up"]),
            ("Sync", "Watch and sync local changes", ["compose", "sync"]),
            ("VM check", "Analyze for VM mode", ["compose", "vm", "check"]),
            ("VM up", "One GPU container runs the stack", ["compose", "vm", "up"]),
            ("Sandbox check", "Analyze for Sandbox mode", ["compose", "sandbox", "check"]),
            ("Sandbox up", "One Sandbox per service", ["compose", "sandbox", "up"]),
            ("Sandbox ps", "Running Sandbox services", ["compose", "sandbox", "ps"]),
            ("Sandbox logs", "Stream service logs", ["compose", "sandbox", "logs"]),
            (
                "Sandbox exec",
                "Run a command in a service",
                ["compose", "sandbox", "exec", _text("Service name"), _text("Command", "bash")],
            ),
            ("Sandbox down", "Stop all Sandbox services", ["compose", "sandbox", "down"]),
        ],
    ),
    (
        "Billing & budgets",
        "Spend, prices and monthly limits",
        [
            ("Usage", "Cost per account for a period", ["billing", "usage", _flag("Every account?", "--all")]),
            ("Summary", "Metered vs. billed this cycle", ["billing", "summary"]),
            ("Rates", "Price per GPU, CPU core and GiB", ["billing", "rates"]),
            ("Open dashboard", "Modal usage page in the browser", ["billing", "open"]),
            ("Show budgets", "Spend vs. budget this month", ["budget", "show"]),
            ("Set budget", "Monthly limit for one or all accounts", ["budget", "set", _amount, _account_option]),
            ("Check budgets", "Report accounts over budget", ["budget", "check"]),
            ("Watch budgets", "Keep enforcing until Ctrl+C", ["budget", "watch"]),
            ("Clear budget", "Remove a limit", ["budget", "clear", _account_option]),
        ],
    ),
    (
        "Images",
        "Prebuilt environments for fast starts",
        [
            (
                "Build",
                "Build and publish a reusable image",
                [
                    "image",
                    "build",
                    _text("Image name (e.g. torch or torch:2.8)"),
                    _optional_text("--pip", "Extra pip packages, comma-separated"),
                ],
            ),
            ("List", "Images published with m-gpux", ["image", "list"]),
            ("Forget", "Drop one from m-gpux's list", ["image", "forget", _image]),
        ],
    ),
    (
        "Accounts",
        "Modal profiles",
        [
            ("List", "Profiles and the active one", ["account", "list"]),
            ("Add", "Save a Modal token as a profile", ["account", "add"]),
            ("Switch", "Make a profile active", ["account", "switch", _profile]),
            ("Remove", "Delete a profile", ["account", "remove", _profile]),
        ],
    ),
    ("Info", "Version and system capabilities", [("Info", "", ["info"])]),
]


def _resolve(steps: list[Step]) -> Optional[list[str]]:
    argv: list[str] = []
    for step in steps:
        if isinstance(step, str):
            argv.append(step)
            continue
        tokens = step()
        if tokens is None:
            return None
        argv.extend(tokens)
    return argv


def _run(root: click.Command, argv: list[str]) -> None:
    console.print(f"\n[dim]$ m-gpux {' '.join(argv)}[/dim]\n")
    try:
        root.main(args=argv, prog_name="m-gpux", standalone_mode=False)
    except click.exceptions.Exit:
        pass
    except click.Abort:
        console.print("\n[yellow]Cancelled.[/yellow]")
    except click.ClickException as exc:
        exc.show()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    except SystemExit:
        pass


def _active_profile() -> str:
    try:
        from m_gpux.core.profiles import load_profiles

        return next((name for name, active in load_profiles() if active), "none")
    except Exception:
        return "unknown"


def run_menu(root: click.Command) -> None:
    """Loop over group → command menus until the user quits."""
    while True:
        console.print(f"\n[dim]Active account:[/dim] [bold]{_active_profile()}[/bold]")
        groups = [(title, desc) for title, desc, _ in MENU] + [("Quit", "")]
        try:
            group_idx = arrow_select(groups, title="What do you want to do?")
        except KeyboardInterrupt:
            return
        if group_idx == len(MENU):
            return
        _, _, items = MENU[group_idx]
        if len(items) == 1:
            item_idx = 0
        else:
            try:
                item_idx = arrow_select(
                    [(label, desc) for label, desc, _ in items] + [(BACK, "")], title=MENU[group_idx][0]
                )
            except KeyboardInterrupt:
                continue
            if item_idx == len(items):
                continue
        try:
            argv = _resolve(items[item_idx][2])
        except KeyboardInterrupt:
            continue
        if argv is None:
            continue
        _run(root, argv)
        try:
            Prompt.ask("\n[dim]Press Enter to return to the menu[/dim]", default="", show_default=False)
        except (KeyboardInterrupt, EOFError):
            return
