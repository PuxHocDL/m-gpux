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
    from m_gpux.core.profiles import load_profiles

    profiles = load_profiles()
    if not profiles:
        console.print("[yellow]No Modal profiles yet — add one with Accounts → Add account.[/yellow]")
        return None
    name = _choose("Profile", [(name, "active" if active else "") for name, active in profiles])
    return [name] if name else None


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


def _gateway_task() -> Optional[list[str]]:
    from m_gpux.core.state import get_gateway_endpoint

    state = get_gateway_endpoint()
    tasks = state.get("tasks", []) if state else []
    if not tasks:
        console.print("[yellow]No gateway deployed yet — use Compute gateway → Deploy first.[/yellow]")
        return None
    name = _choose("Task", [(str(task), "") for task in tasks])
    return [name] if name else None


def _gateway_job() -> Optional[list[str]]:
    from m_gpux.core.state import list_gateway_jobs

    jobs = list_gateway_jobs()
    if not jobs:
        console.print("[yellow]No gateway jobs submitted from this machine yet.[/yellow]")
        return None
    options = [
        (str(j["id"]), " · ".join(str(v) for v in (j.get("task"), j.get("status"), j.get("submitted_at")) if v))
        for j in jobs
    ]
    job_id = _choose("Job", options)
    return [job_id] if job_id else None


def _project_task() -> Optional[list[str]]:
    from pathlib import Path

    from m_gpux.core.project import ProjectError, find_project, load_project

    path = find_project(Path.cwd())
    if path is None:
        console.print("[yellow]No mgpux.toml here — use Projects → Init first.[/yellow]")
        return None
    try:
        tasks = load_project(path)["tasks"]
    except ProjectError as exc:
        console.print(f"[red]{exc}[/red]")
        return None
    name = _choose("Task", [(n, t["command"]) for n, t in tasks.items()])
    return [name] if name else None


def _run_id() -> Optional[list[str]]:
    from m_gpux.core.state import STATE_DIR, _read_json

    paths = sorted((STATE_DIR / "runs").glob("*.json"), reverse=True)[:30]
    rows = [r for r in (_read_json(p, None) for p in paths) if isinstance(r, dict) and r.get("id")]
    if not rows:
        console.print("[yellow]No runs yet — use Projects → Up first.[/yellow]")
        return None
    options = [(r["id"], f"{r.get('kind')} {r.get('project')}/{r.get('task')} · {r.get('status')}") for r in rows]
    run_id = _choose("Run", options)
    return [run_id] if run_id else None


def _notify_channel() -> Optional[list[str]]:
    from m_gpux.core.notify import load_channels, masked

    channels = load_channels()
    if not channels:
        console.print("[yellow]No notification channels yet — use Notifications → Add channel.[/yellow]")
        return None
    name = _choose("Channel", [(c["name"], f"{c['type']} · {masked(c)}") for c in channels])
    return [name] if name else None


def _kaggle_account(allow_auto: bool = False) -> Callable[[], Optional[list[str]]]:
    def ask() -> Optional[list[str]]:
        from m_gpux.core.kaggle import accounts

        found = accounts()
        if not found:
            console.print("[yellow]No Kaggle accounts yet — use Kaggle & Colab → Add Kaggle account.[/yellow]")
            return None
        options = [("auto", "most GPU hours left with a free slot")] if allow_auto else []
        options += [(a.name, " · ".join(v for v in (a.team, a.note) if v)) for a in found]
        name = _choose("Kaggle account", options)
        return [name] if name else None

    return ask


def _colab_account(allow_auto: bool = False) -> Callable[[], Optional[list[str]]]:
    def ask() -> Optional[list[str]]:
        from m_gpux.core.colab import accounts

        options = [("auto", "most compute units left")] if allow_auto else []
        options += [(a["name"], "logged in" if a["logged_in"] else "not logged in") for a in accounts()]
        name = _choose("Colab account", options)
        return [name] if name else None

    return ask


def _opt(flag: str, picker: Callable[[], Optional[list[str]]]) -> Callable[[], Optional[list[str]]]:
    """Turn a picker's value into ``flag value``."""

    def ask() -> Optional[list[str]]:
        picked = picker()
        return [flag, picked[0]] if picked else None

    return ask


def _words(question: str) -> Callable[[], Optional[list[str]]]:
    """Free-form arguments, split like a shell would."""

    def ask() -> Optional[list[str]]:
        import shlex

        value = (Prompt.ask(f"[bold cyan]{question}[/bold cyan]") or "").strip()
        try:
            return shlex.split(value, posix=True) or None
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return None

    return ask


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
        "Dashboard",
        "Local web console for accounts, compute and costs",
        [("Open dashboard", "Opens in your browser; Ctrl+C here stops it", ["ui"])],
    ),
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
        "Compute gateway",
        "Authenticated async API for predeclared jobs",
        [
            ("Init", "Starter manifest and worker in this folder", ["gateway", "init"]),
            ("Validate", "Check mgpux.gateway.toml offline", ["gateway", "validate"]),
            ("Deploy", "Deploy the gateway and save its URL and key", ["gateway", "deploy"]),
            (
                "Submit job",
                "Run a declared task",
                [
                    "gateway",
                    "submit",
                    _gateway_task,
                    _optional_text("--input", "JSON input object"),
                    _flag("Wait for the result?", "--wait"),
                ],
            ),
            (
                "Jobs",
                "Jobs submitted from this machine",
                ["gateway", "jobs", _flag("Refresh statuses from the gateway?", "--refresh")],
            ),
            ("Result", "A job's status or result", ["gateway", "result", _gateway_job]),
            ("Logs", "A job's recent logs", ["gateway", "logs", _gateway_job]),
            ("Cancel", "Cancel a running job", ["gateway", "cancel", _gateway_job]),
            ("Tasks", "Tasks the gateway exposes", ["gateway", "tasks"]),
            ("Show", "Endpoint details (key masked)", ["gateway", "show"]),
            ("Reveal key", "Print the full API key", ["gateway", "key"]),
            ("Open API docs", "Interactive /docs in the browser", ["gateway", "open"]),
        ],
    ),
    (
        "Projects & sweeps",
        "mgpux.toml tasks, parameter sweeps, run anywhere",
        [
            ("Init", "Create mgpux.toml in this folder", ["init"]),
            ("Up", "Run a task on Modal", ["up", _project_task]),
            (
                "Sweep",
                "Run a task over a parameter grid",
                ["sweep", _project_task, _opt("--grid", _text("Grid (e.g. lr=1e-4,3e-4)"))],
            ),
            (
                "Run anywhere",
                "Free Kaggle quota, then Colab, then Modal credit",
                ["run", _text("Script", "main.py"), _flag("Only show the plan?", "--plan")],
            ),
            ("Runs", "Recent up / sweep results", ["runs", "list"]),
            ("Run details", "Jobs, metrics and failures of one run", ["runs", "show", _run_id]),
        ],
    ),
    (
        "Secrets & sync",
        "Same Secrets and images on every workspace",
        [
            ("Secret status", "Which workspace has which Secret", ["secrets", "status"]),
            (
                "Sync secret",
                "Values from env / .env / hidden prompt to every workspace",
                ["secrets", "sync", _text("Secret name (e.g. hf)"), _words("Variable names (e.g. HF_TOKEN)")],
            ),
            (
                "Delete secret",
                "From one or more workspaces",
                ["secrets", "delete", _text("Secret name"), _optional_text("--to", "Profiles ('all' or a,b)")],
            ),
            ("Image status", "Which workspace has which published image", ["image", "status"]),
            ("Sync image", "Build an image where it is missing", ["image", "sync", _image]),
        ],
    ),
    (
        "Volumes",
        "Browse and move data in Modal Volumes",
        [
            ("List", "Volumes on every account", ["volume", "list", _flag("Every account?", "--all")]),
            ("Browse", "List a folder", ["volume", "ls", _text("Volume"), _text("Path", "/")]),
            ("Disk usage", "Size per top-level folder", ["volume", "du", _text("Volume")]),
            (
                "Download",
                "Volume → local",
                ["volume", "get", _text("Volume"), _text("Remote path"), _text("Local", ".")],
            ),
            ("Upload", "Local → volume", ["volume", "put", _text("Volume"), _text("Local path"), _text("Remote", "/")]),
            ("Delete file", "Inside a volume", ["volume", "rm", _text("Volume"), _text("Remote path")]),
            ("Delete volume", "A whole volume and its data", ["volume", "delete", _text("Volume")]),
        ],
    ),
    (
        "Notifications",
        "Discord, Slack, Telegram, ntfy or webhook alerts",
        [
            ("Add channel", "Webhook / bot, then a test message", ["notify", "add"]),
            ("Channels", "Configured channels (masked)", ["notify", "list"]),
            ("Test", "Send a test message", ["notify", "test"]),
            ("Events", "What a channel can subscribe to", ["notify", "events"]),
            ("Send", "A custom message", ["notify", "send", _text("Title")]),
            ("Watch", "Apps, credit and jobs until Ctrl+C", ["notify", "watch"]),
            ("Remove channel", "", ["notify", "remove", _notify_channel]),
        ],
    ),
    (
        "Kaggle & Colab",
        "GPU quota, kernels and runtimes on other clouds",
        [
            ("Kaggle accounts", "GPU / TPU hours left on every account", ["kaggle", "accounts"]),
            ("Kaggle status", "Running and queued kernels, free slots", ["kaggle", "status"]),
            ("Kaggle free slots", "Accounts that can start a GPU kernel now", ["kaggle", "free"]),
            (
                "Push kernel",
                "Push a kernel folder, optionally as another account",
                [
                    "kaggle",
                    "push",
                    _text("Kernel folder", "."),
                    _opt("--as", _kaggle_account(allow_auto=True)),
                    _flag("Wait and download the output?", "--wait"),
                ],
            ),
            (
                "Watch kernel",
                "Wait for a kernel, then download its output",
                ["kaggle", "watch", _text("Kernel (owner/slug)")],
            ),
            (
                "Run a kaggle command",
                "As any account",
                ["kaggle", "run", _kaggle_account(True), _words("kaggle arguments")],
            ),
            ("Add Kaggle account", "Register an API token", ["kaggle", "add", _text("API token (KGAT_…)")]),
            ("Remove Kaggle account", "Forget a token", ["kaggle", "remove", _kaggle_account()]),
            ("Colab accounts", "Compute units and runtimes per Google account", ["colab", "accounts"]),
            ("Colab sessions", "Live runtimes on every account", ["colab", "sessions"]),
            (
                "Colab run",
                "Run a script on a fresh VM, then release it",
                [
                    "colab",
                    "run",
                    _text("Script"),
                    _opt("--gpu", _pick("GPU", [(g, "") for g in ("T4", "L4", "G4", "A100", "H100")])),
                    _opt("--as", _colab_account(allow_auto=True)),
                ],
            ),
            (
                "Colab new runtime",
                "A named runtime to exec / upload against",
                [
                    "colab",
                    "new",
                    _opt("--session", _text("Runtime name")),
                    _opt("--as", _colab_account(allow_auto=True)),
                ],
            ),
            (
                "Colab stop",
                "Release a runtime",
                ["colab", "stop", _text("Runtime name"), _opt("--as", _colab_account())],
            ),
            ("Run a colab command", "As any account", ["colab", "as", _colab_account(True), _words("colab arguments")]),
            ("Colab login", "Add or re-login a Google account", ["colab", "login", _text("Account name", "main")]),
            ("Remove Colab account", "Delete an extra account's login", ["colab", "remove", _colab_account()]),
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
