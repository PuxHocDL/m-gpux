"""``host`` plugin — deploy any web app on Modal as a long-lived service.

Modal's per-function timeout caps at ``86_400`` seconds (24 hours). Web
endpoints declared with ``@modal.web_server`` / ``@modal.asgi_app`` /
``@modal.wsgi_app`` are *services*: Modal recycles individual containers
behind the scenes, so the public URL stays online indefinitely once you
``modal deploy`` the app. Pair that with ``min_containers=1`` to keep at
least one warm replica alive 24/7 (no cold-start delay).

Three supported targets:

* **ASGI app** — point at a ``module:variable`` (e.g. ``app:app`` for FastAPI
  or ``main:application`` for Django). Uses ``@modal.asgi_app``.
* **WSGI app** — same idea, for Flask/Django legacy. Uses ``@modal.wsgi_app``.
* **Static directory** — serve a folder of HTML/JS via Python's
  ``http.server`` behind ``@modal.web_server``.

The plugin is intentionally thin: it generates ``modal_runner.py`` and hands
it to :func:`m_gpux.core.execute_modal_temp_script` for preview + run.
Choose ``deploy`` for a persistent URL or ``run`` for a one-off ephemeral
test.
"""

from __future__ import annotations

import os
import subprocess

import typer
from rich.panel import Panel
from rich.prompt import Prompt

from m_gpux.core.console import console
from m_gpux.core.gpus import AVAILABLE_CPUS, AVAILABLE_GPUS
from m_gpux.core.plugin import PluginBase
from m_gpux.core.profiles import activate_profile, select_profile
from m_gpux.core.runner import execute_modal_temp_script
from m_gpux.core.ui import arrow_select

app = typer.Typer(
    help=(
        "Host a web app on Modal. ASGI, WSGI or a static directory — your "
        "URL stays online for as long as the deployment exists."
    ),
    short_help="Web hosting",
    no_args_is_help=True,
)


# ─── Templates ────────────────────────────────────────────────

_DEFAULT_EXCLUDES = (
    ".venv,venv,__pycache__,.git,node_modules,.mypy_cache,"
    ".pytest_cache,*.egg-info,.tox,dist,build"
)

ASGI_TEMPLATE = '''\
import modal

app = modal.App("m-gpux-host-{slug}")
image = (
    modal.Image.debian_slim(python_version="3.12")
    {pip_section}
    .add_local_dir("{local_dir}", remote_path="/app", ignore={exclude_patterns})
)

@app.function(
    image=image,
    {compute_spec},
    timeout=86400,
    scaledown_window={scaledown},
    min_containers={min_containers},
)
@modal.concurrent(max_inputs={max_concurrent})
@modal.asgi_app()
def web():
    import sys, importlib
    sys.path.insert(0, "/app")
    module_name, _, attr = "{entry}".partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr or "app")
'''

WSGI_TEMPLATE = '''\
import modal

app = modal.App("m-gpux-host-{slug}")
image = (
    modal.Image.debian_slim(python_version="3.12")
    {pip_section}
    .add_local_dir("{local_dir}", remote_path="/app", ignore={exclude_patterns})
)

@app.function(
    image=image,
    {compute_spec},
    timeout=86400,
    scaledown_window={scaledown},
    min_containers={min_containers},
)
@modal.concurrent(max_inputs={max_concurrent})
@modal.wsgi_app()
def web():
    import sys, importlib
    sys.path.insert(0, "/app")
    module_name, _, attr = "{entry}".partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr or "app")
'''

STATIC_TEMPLATE = '''\
import modal
import subprocess

app = modal.App("m-gpux-host-{slug}")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .add_local_dir("{local_dir}", remote_path="/site", ignore={exclude_patterns})
)

PORT = 8000

@app.function(
    image=image,
    {compute_spec},
    timeout=86400,
    scaledown_window={scaledown},
    min_containers={min_containers},
)
@modal.concurrent(max_inputs={max_concurrent})
@modal.web_server(port=PORT, startup_timeout=60)
def web():
    subprocess.Popen(
        ["python", "-m", "http.server", str(PORT), "--directory", "/site"],
    )
'''


# ─── Helpers ──────────────────────────────────────────────────


def _slugify(name: str) -> str:
    safe = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    return safe[:32] or "site"


def _pick_compute() -> tuple[str, str]:
    """Interactive GPU/CPU picker. Returns ``(compute_spec, compute_label)``."""
    type_idx = arrow_select(
        [("CPU", "Recommended for typical web apps"), ("GPU", "If your app needs CUDA")],
        title="Compute Type",
        default=0,
    )
    if type_idx == 0:
        keys = list(AVAILABLE_CPUS.keys())
        opts = [(f"{c} cores", desc) for c, _, desc in (AVAILABLE_CPUS[k] for k in keys)]
        idx = arrow_select(opts, title="Select CPU", default=2)
        cores, mem, _ = AVAILABLE_CPUS[keys[idx]]
        return f"cpu={cores}, memory={mem}", f"CPU ({cores} cores, {mem} MB)"
    opts = [(v[0], v[1]) for v in AVAILABLE_GPUS.values()]
    idx = arrow_select(opts, title="Select GPU", default=1)
    gpu = list(AVAILABLE_GPUS.values())[idx][0]
    return f'gpu="{gpu}"', gpu


def _ask_pip_section() -> str:
    if os.path.exists("requirements.txt"):
        use_req = Prompt.ask(
            "[green]Found requirements.txt.[/green] Install dependencies from it?",
            choices=["y", "n"], default="y",
        )
        if use_req == "y":
            req = os.path.abspath("requirements.txt").replace("\\", "/")
            return f'.pip_install_from_requirements("{req}")'
    extras = Prompt.ask(
        "Comma-separated pip packages to install (blank to skip)",
        default="",
    ).strip()
    if not extras:
        return ""
    pkgs = [p.strip() for p in extras.split(",") if p.strip()]
    return ".pip_install(" + ", ".join(repr(p) for p in pkgs) + ")"


def _ask_exclude_patterns() -> list[str]:
    raw = Prompt.ask(
        "Comma-separated upload exclude patterns (glob)",
        default=_DEFAULT_EXCLUDES,
    )
    return [p.strip() for p in raw.split(",") if p.strip()]


def _ask_deploy_mode() -> str:
    """Return ``"deploy"`` or ``"run"``."""
    idx = arrow_select(
        [
            ("deploy", "Persistent — URL stays live until you stop the app"),
            ("run",    "Ephemeral — runs until you Ctrl+C, no public DNS"),
        ],
        title="Deployment mode",
        default=0,
    )
    return ("deploy", "run")[idx]


def _ask_keep_warm() -> int:
    idx = arrow_select(
        [
            ("Auto-scale to 0", "Cheapest. ~5–15s cold start when idle."),
            ("Keep 1 warm",     "No cold starts. Costs continuously."),
        ],
        title="Warm replicas (min_containers)",
        default=0,
    )
    return idx  # 0 → auto-scale, 1 → keep one warm


def _build_script(kind: str, **vars) -> str:
    tpl = {"asgi": ASGI_TEMPLATE, "wsgi": WSGI_TEMPLATE, "static": STATIC_TEMPLATE}[kind]
    out = tpl
    for k, v in vars.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _deploy_or_run(script: str, mode: str, description: str) -> None:
    if mode == "run":
        execute_modal_temp_script(script, description)
        return
    runner_file = "modal_runner.py"
    with open(runner_file, "w", encoding="utf-8") as f:
        f.write(script)
    console.print(f"[dim]Wrote {runner_file}. Edit before deploying if needed.[/dim]")
    if os.environ.get("MGPUX_VERBOSE", "").strip() in ("1", "true", "yes"):
        from rich.syntax import Syntax
        console.print(Syntax(script, "python", theme="monokai", line_numbers=True))
    choice = Prompt.ask(
        "[bold cyan][Enter][/bold cyan] deploy  •  [bold cyan]c[/bold cyan] cancel",
        default="",
    ).strip().lower()
    if choice in ("c", "cancel"):
        console.print("[yellow]Cancelled.[/yellow]")
        return
    console.print(f"[bold green]Deploying {description}…[/bold green]")
    try:
        subprocess.run(["modal", "deploy", runner_file])
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    console.print(
        "[green]Done.[/green] URL is shown above. Stop the app any time with "
        "[bold yellow]m-gpux stop[/bold yellow]."
    )


# ─── Commands ─────────────────────────────────────────────────


def _common_setup(name_hint: str) -> tuple[str, str, str]:
    profile = select_profile()
    if profile is None:
        raise typer.Exit(1)
    activate_profile(profile)

    name = Prompt.ask("App name", default=name_hint)
    slug = _slugify(name)
    compute_spec, compute_label = _pick_compute()
    return slug, compute_spec, compute_label


@app.command("asgi", help="Host a FastAPI / Starlette / any ASGI app.")
def host_asgi(
    entry: str = typer.Option(
        None,
        "--entry",
        "-e",
        help="Python entry point, e.g. 'main:app' for `app = FastAPI()` in main.py",
    ),
):
    """Deploy an ASGI web app."""
    slug, compute_spec, compute_label = _common_setup("my-app")
    if entry is None:
        entry = Prompt.ask("ASGI entry (module:variable)", default="main:app")
    pip_section = _ask_pip_section()
    excludes = _ask_exclude_patterns()
    keep_warm = _ask_keep_warm()
    mode = _ask_deploy_mode()

    script = _build_script(
        "asgi",
        slug=slug,
        compute_spec=compute_spec,
        scaledown=300,
        min_containers=keep_warm,
        max_concurrent=100,
        entry=entry,
        pip_section=pip_section,
        local_dir=os.path.abspath(".").replace("\\", "/"),
        exclude_patterns=repr(excludes),
    )
    _deploy_or_run(script, mode, f"ASGI app '{slug}' on {compute_label}")


@app.command("wsgi", help="Host a Flask / Django / any WSGI app.")
def host_wsgi(
    entry: str = typer.Option(None, "--entry", "-e", help="WSGI entry, e.g. 'app:app'"),
):
    """Deploy a WSGI web app."""
    slug, compute_spec, compute_label = _common_setup("my-app")
    if entry is None:
        entry = Prompt.ask("WSGI entry (module:variable)", default="app:app")
    pip_section = _ask_pip_section()
    excludes = _ask_exclude_patterns()
    keep_warm = _ask_keep_warm()
    mode = _ask_deploy_mode()

    script = _build_script(
        "wsgi",
        slug=slug,
        compute_spec=compute_spec,
        scaledown=300,
        min_containers=keep_warm,
        max_concurrent=100,
        entry=entry,
        pip_section=pip_section,
        local_dir=os.path.abspath(".").replace("\\", "/"),
        exclude_patterns=repr(excludes),
    )
    _deploy_or_run(script, mode, f"WSGI app '{slug}' on {compute_label}")


@app.command("static", help="Host a static site (HTML/JS/CSS) from a directory.")
def host_static(
    directory: str = typer.Option(
        None, "--dir", "-d", help="Directory to serve (defaults to current)"
    ),
):
    """Deploy a directory as a static website."""
    slug, compute_spec, compute_label = _common_setup("my-site")
    target = directory or "."
    if not os.path.isdir(target):
        console.print(f"[red]{target} is not a directory.[/red]")
        raise typer.Exit(1)

    excludes = _ask_exclude_patterns()
    keep_warm = _ask_keep_warm()
    mode = _ask_deploy_mode()

    script = _build_script(
        "static",
        slug=slug,
        compute_spec=compute_spec,
        scaledown=300,
        min_containers=keep_warm,
        max_concurrent=100,
        local_dir=os.path.abspath(target).replace("\\", "/"),
        exclude_patterns=repr(excludes),
    )
    _deploy_or_run(script, mode, f"Static site '{slug}' on {compute_label}")


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context):
    if ctx.invoked_subcommand is not None:
        return
    console.print(Panel.fit(
        "[bold magenta]m-gpux host[/bold magenta]\n"
        "Deploy a web app on Modal as a long-lived service.\n\n"
        "[cyan]asgi[/cyan]   FastAPI / Starlette\n"
        "[cyan]wsgi[/cyan]   Flask / Django (WSGI)\n"
        "[cyan]static[/cyan] HTML/JS/CSS directory\n\n"
        "[dim]Modal recycles containers behind the scenes; with [bold]Keep 1 warm[/bold] "
        "your URL stays cold-start-free 24/7.[/dim]",
        border_style="cyan",
    ))


# ─── Plugin registration ──────────────────────────────────────


class HostPlugin(PluginBase):
    name = "host"
    help = "Host web apps (ASGI / WSGI / static) on Modal as long-lived URLs."
    rich_help_panel = "Compute Engine"

    def register(self, root_app):
        root_app.add_typer(
            app,
            name=self.name,
            help=self.help,
            rich_help_panel=self.rich_help_panel,
        )
