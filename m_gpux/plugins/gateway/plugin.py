"""CLI commands for deploying and calling the m-gpux Compute Gateway."""

from __future__ import annotations

import json
import re
import secrets
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, NoReturn

import typer
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from m_gpux.core.console import console
from m_gpux.core.modal_cli import DEPLOY_STRATEGIES, deploy_cmd, modal_env
from m_gpux.core.plugin import PluginBase
from m_gpux.core.profiles import load_config, select_profile
from m_gpux.core.state import (
    get_gateway_endpoint,
    list_gateway_jobs,
    save_gateway_endpoint,
    save_gateway_job,
)
from m_gpux.plugins.gateway.client import TERMINAL_STATES, GatewayHTTPError, gateway_request, wait_for_job
from m_gpux.plugins.gateway.config import DEFAULT_MANIFEST, GatewayConfig, GatewayConfigError, load_gateway_config
from m_gpux.plugins.gateway.renderer import render_gateway_app

app = typer.Typer(
    help="Expose safe, predeclared Modal compute tasks through an authenticated async API.",
    short_help="Async compute API gateway",
    no_args_is_help=True,
)

MANIFEST_TEMPLATE = '''[gateway]
name = "m-gpux-compute-gateway"
source = "."
python_version = "3.12"
max_input_bytes = 1048576
max_output_bytes = 1048576
exclude = [".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build"]

[tasks.echo]
description = "Verify the gateway with a cheap CPU JSON echo task."
command = ["python", "mgpux_worker.py"]
packages = []
cpu = 0.25
memory = 256
timeout = 60
retries = 1
max_containers = 10
scaledown_window = 30

# Add a GPU task by declaring it here; API callers can only select declared tasks.
# [tasks.inference]
# description = "Run the project's inference entry point."
# command = ["python", "inference.py"]
# packages = ["torch", "transformers"]
# gpu = ["L4", "A10G"]
# timeout = 900
# max_containers = 5
'''

WORKER_TEMPLATE = '''"""Starter Compute Gateway task: read a JSON object from stdin and emit JSON."""

import json
import sys

payload = json.load(sys.stdin)
json.dump({"ok": True, "echo": payload}, sys.stdout)
'''


def _fail(message: str, code: int = 1) -> NoReturn:
    console.print(f"[bold red]{message}[/bold red]")
    raise typer.Exit(code)


def _load(path: str) -> GatewayConfig:
    try:
        return load_gateway_config(path)
    except GatewayConfigError as exc:
        _fail(str(exc))


def _resolve_profile(requested: str | None) -> tuple[str, Any]:
    profile = requested or select_profile()
    if not profile:
        _fail("No Modal profile selected.")
    document = load_config()
    configured = next((name for name in document if name.casefold() == profile.casefold()), None)
    if configured is None:
        _fail(f"Modal profile {profile!r} was not found in ~/.modal.toml")
    values = document[configured]
    if not values.get("token_id") or not values.get("token_secret"):
        _fail(f"Modal profile {configured!r} has no usable token credentials")
    return configured, values


def _modal_client(profile_values: Any):
    import modal

    return modal.Client.from_credentials(str(profile_values["token_id"]), str(profile_values["token_secret"]))


def _delete_secret(name: str | None, client: Any) -> None:
    if not name:
        return
    import modal

    try:
        modal.Secret.objects.delete(name, allow_missing=True, client=client)
    except Exception as exc:
        console.print(f"[yellow]Could not remove old Modal Secret {name!r}: {exc}[/yellow]")


def _deploy_and_capture_url(command: list[str], profile: str) -> tuple[int, str | None]:
    endpoint_re = re.compile(r"https://[A-Za-z0-9.-]+\.modal\.(?:run|direct)")
    endpoint = None
    environment = modal_env(profile)
    environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    if process.stdout is None:
        process.wait()
        raise OSError("Modal CLI output pipe was not created")
    for line in process.stdout:
        print(line, end="", flush=True)
        match = endpoint_re.search(line)
        if match:
            endpoint = match.group(0)
    return process.wait(), endpoint


def _saved_gateway() -> dict[str, Any]:
    state = get_gateway_endpoint()
    if state is None:
        _fail("No deployed gateway is saved. Run `m-gpux gateway deploy` first.")
    return state


def _print_json(value: Any) -> None:
    console.print_json(json.dumps(value, ensure_ascii=False, default=str))


def _parse_input(raw: str, input_file: Path | None) -> dict[str, Any]:
    if input_file is not None:
        try:
            raw = input_file.read_text(encoding="utf-8")
        except OSError as exc:
            _fail(f"Could not read {input_file}: {exc}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        _fail(f"Input is not valid JSON: {exc}")
    if not isinstance(value, dict):
        _fail("Input must be a JSON object.")
    return value


@app.command("init")
def init_gateway(
    directory: Path = typer.Argument(Path("."), help="Directory in which to create the starter files."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing starter files."),
) -> None:
    """Create a safe CPU echo gateway manifest and worker."""
    directory = directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        directory / DEFAULT_MANIFEST: MANIFEST_TEMPLATE,
        directory / "mgpux_worker.py": WORKER_TEMPLATE,
    }
    existing = [path.name for path in files if path.exists() and not force]
    if existing:
        _fail(f"Refusing to overwrite: {', '.join(existing)}. Pass --force to replace them.")
    for path, content in files.items():
        path.write_text(content, encoding="utf-8", newline="\n")
    console.print(f"[green]Created {DEFAULT_MANIFEST} and mgpux_worker.py in {directory}[/green]")
    console.print("[dim]Next: m-gpux gateway validate && m-gpux gateway deploy[/dim]")


@app.command("validate")
def validate_gateway(
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", "-f", help="Gateway TOML manifest."),
) -> None:
    """Validate the manifest without contacting Modal."""
    config = _load(manifest)
    table = Table(title=f"Compute Gateway: {config.name}")
    table.add_column("Task", style="bold green")
    table.add_column("Compute")
    table.add_column("Command")
    table.add_column("Timeout")
    for task in config.tasks:
        compute = f"GPU {task.gpu}" if task.gpu else f"CPU {task.cpu or 'default'}"
        table.add_row(task.name, compute, " ".join(task.command), f"{task.timeout}s")
    console.print(table)
    console.print(f"[green]Valid.[/green] Source: {config.source}")


@app.command("deploy")
def deploy_gateway(
    manifest: str = typer.Option(DEFAULT_MANIFEST, "--manifest", "-f", help="Gateway TOML manifest."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Modal profile; prompts when omitted."),
    strategy: str = typer.Option("rolling", "--strategy", help="rolling or recreate"),
) -> None:
    """Generate and deploy the authenticated Modal gateway."""
    if strategy not in DEPLOY_STRATEGIES:
        _fail(f"--strategy must be one of: {', '.join(DEPLOY_STRATEGIES)}")
    config = _load(manifest)
    profile_name, profile_values = _resolve_profile(profile)
    client = _modal_client(profile_values)
    api_key = "mgx_" + secrets.token_urlsafe(32)
    secret_name = "m-gpux-gateway-auth-" + secrets.token_hex(6)
    runner_path = config.manifest_path.parent / "modal_gateway.py"

    import modal

    console.print(f"[cyan]Creating an isolated auth secret on profile {profile_name}...[/cyan]")
    try:
        modal.Secret.objects.create(
            secret_name,
            {"MGPUX_GATEWAY_API_KEY": api_key},
            allow_existing=False,
            client=client,
        )
        source = render_gateway_app(config, secret_name)
        runner_path.write_text(source, encoding="utf-8", newline="\n")
        compile(source, str(runner_path), "exec")
        console.print(f"[cyan]Deploying {config.name} ({len(config.tasks)} task(s))...[/cyan]")
        return_code, endpoint = _deploy_and_capture_url(deploy_cmd(str(runner_path), strategy), profile_name)
        if return_code != 0:
            _delete_secret(secret_name, client)
            _fail(f"modal deploy failed with exit code {return_code}", return_code)
    except typer.Exit:
        raise
    except Exception as exc:
        _delete_secret(secret_name, client)
        _fail(f"Gateway deployment failed: {exc}")

    if not endpoint:
        try:
            endpoint = modal.Function.from_name(config.name, "gateway", client=client).get_web_url()
        except Exception:
            endpoint = None
    if not endpoint:
        _delete_secret(secret_name, client)
        _fail("Deployment succeeded, but the gateway URL could not be resolved. The previous local config was preserved.")

    previous = get_gateway_endpoint()
    save_gateway_endpoint(
        endpoint,
        api_key,
        app_name=config.name,
        secret_name=secret_name,
        profile=profile_name,
        manifest=str(config.manifest_path),
        tasks=[task.name for task in config.tasks],
    )
    if previous and previous.get("secret_name") != secret_name and previous.get("profile") == profile_name:
        _delete_secret(str(previous.get("secret_name", "")), client)
    masked = api_key[:8] + "..." + api_key[-4:]
    console.print(
        Panel(
            f"[bold green]Compute Gateway is live[/bold green]\n\n"
            f"URL: [cyan]{endpoint}[/cyan]\n"
            f"Docs: [cyan]{endpoint}/docs[/cyan]\n"
            f"API key: [yellow]{masked}[/yellow] (saved locally)\n\n"
            "Try: [bold]m-gpux gateway submit echo --input '{\"hello\": \"Modal\"}' --wait[/bold]",
            border_style="green",
        )
    )


@app.command("show")
def show_gateway() -> None:
    """Show the saved endpoint without revealing its API key."""
    state = _saved_gateway()
    table = Table(title="Compute Gateway")
    table.add_column("Field", style="green")
    table.add_column("Value")
    for key in ("url", "app_name", "profile", "manifest", "updated_at"):
        table.add_row(key, str(state.get(key, "")))
    table.add_row("tasks", ", ".join(state.get("tasks", [])))
    api_key = str(state["api_key"])
    table.add_row("api_key", api_key[:8] + "..." + api_key[-4:])
    console.print(table)


@app.command("key")
def show_key() -> None:
    """Reveal the locally saved gateway API key."""
    console.print(str(_saved_gateway()["api_key"]))


@app.command("open")
def open_gateway_docs() -> None:
    """Open the deployed interactive OpenAPI documentation."""
    url = str(_saved_gateway()["url"]).rstrip("/") + "/docs"
    webbrowser.open(url)
    console.print(f"[green]Opened {url}[/green]")


@app.command("tasks")
def list_gateway_tasks() -> None:
    """List tasks advertised by the deployed gateway."""
    state = _saved_gateway()
    try:
        _print_json(gateway_request(state["url"], state["api_key"], "/v1/tasks"))
    except GatewayHTTPError as exc:
        _fail(str(exc))


@app.command("submit")
def submit_job(
    task: str = typer.Argument(..., help="Declared task name."),
    input_json: str = typer.Option("{}", "--input", help="JSON object passed to the task on stdin."),
    input_file: Path | None = typer.Option(None, "--input-file", help="Read the JSON object from a file."),
    wait: bool = typer.Option(False, "--wait/--no-wait", help="Wait for the final result."),
    timeout: float = typer.Option(900.0, "--timeout", min=1.0, help="Client wait timeout in seconds."),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key", help="Safely retry a submission."),
) -> None:
    """Submit an asynchronous job, optionally waiting for its result."""
    state = _saved_gateway()
    payload = _parse_input(input_json, input_file)
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    try:
        submitted = gateway_request(
            state["url"],
            state["api_key"],
            "/v1/jobs",
            method="POST",
            payload={"task": task, "input": payload},
            headers=headers,
            timeout=min(timeout, 60.0),
        )
        if isinstance(submitted, dict):
            save_gateway_job(submitted)
        if wait:
            submitted = wait_for_job(state["url"], state["api_key"], submitted["id"], timeout=timeout)
            save_gateway_job(submitted)
        _print_json(submitted)
    except (GatewayHTTPError, TimeoutError, KeyError) as exc:
        _fail(str(exc))


@app.command("result")
def job_result(
    job_id: str = typer.Argument(..., help="Modal FunctionCall job ID."),
    wait: bool = typer.Option(False, "--wait/--no-wait", help="Wait until the job finishes."),
    timeout: float = typer.Option(900.0, "--timeout", min=1.0, help="Client wait timeout in seconds."),
) -> None:
    """Get a job's current state or wait for its final result."""
    state = _saved_gateway()
    try:
        result = (
            wait_for_job(state["url"], state["api_key"], job_id, timeout=timeout)
            if wait
            else gateway_request(state["url"], state["api_key"], f"/v1/jobs/{job_id}")
        )
        if isinstance(result, dict):
            save_gateway_job(result)
        _print_json(result)
    except (GatewayHTTPError, TimeoutError) as exc:
        _fail(str(exc))


@app.command("logs")
def job_logs(
    job_id: str = typer.Argument(..., help="Modal FunctionCall job ID."),
    limit: int = typer.Option(100, "--limit", min=1, max=1000),
) -> None:
    """Fetch recent stdout, stderr, and system logs for a job."""
    state = _saved_gateway()
    try:
        result = gateway_request(state["url"], state["api_key"], f"/v1/jobs/{job_id}/logs?limit={limit}")
        for entry in result.get("logs", []):
            message = str(entry.get("message", "")).rstrip("\n")
            if not message.strip():
                continue
            # Text (not markup): "[stdout]" and task output must print verbatim.
            line = Text(str(entry.get("timestamp", "")), style="dim")
            line.append(f" [{entry.get('source', 'log')}] ", style="cyan")
            line.append(message)
            console.print(line)
    except (GatewayHTTPError, AttributeError) as exc:
        _fail(str(exc))


@app.command("cancel")
def cancel_job(job_id: str = typer.Argument(..., help="Modal FunctionCall job ID.")) -> None:
    """Cancel a submitted job."""
    state = _saved_gateway()
    try:
        result = gateway_request(state["url"], state["api_key"], f"/v1/jobs/{job_id}", method="DELETE")
        if isinstance(result, dict):
            save_gateway_job(result)
        _print_json(result)
    except GatewayHTTPError as exc:
        _fail(str(exc))


@app.command("jobs")
def jobs_command(
    refresh: bool = typer.Option(False, "--refresh/--no-refresh", help="Refresh each saved job from the gateway."),
) -> None:
    """Show up to 100 jobs submitted from this machine."""
    state = _saved_gateway()
    jobs = list_gateway_jobs()
    if refresh:
        for job in jobs:
            if job.get("status") in TERMINAL_STATES:
                continue
            try:
                current = gateway_request(state["url"], state["api_key"], f"/v1/jobs/{job['id']}")
            except GatewayHTTPError as exc:
                if exc.status == 404:
                    # The gateway forgot the job (idle for 7+ days).
                    save_gateway_job({**job, "status": "expired"})
                continue
            if isinstance(current, dict):
                save_gateway_job(current)
        jobs = list_gateway_jobs()
    if not jobs:
        console.print("[yellow]No locally submitted gateway jobs yet.[/yellow]")
        return
    table = Table(title="Compute Gateway Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("Submitted")
    for job in jobs:
        status = str(job.get("status", "unknown"))
        style = {"succeeded": "green", "failed": "red", "cancelled": "yellow", "expired": "dim"}.get(status, "cyan")
        table.add_row(
            str(job.get("id", "")),
            str(job.get("task", "")),
            f"[{style}]{status}[/{style}]",
            str(job.get("submitted_at", "")),
        )
    console.print(table)


class GatewayPlugin(PluginBase):
    name = "gateway"
    help = "Deploy and call an authenticated asynchronous Modal compute API."
    short_help = "Compute API Gateway"
    rich_help_panel = "Deploy"

    def register(self, root_app: typer.Typer) -> None:
        root_app.add_typer(
            app,
            name=self.name,
            help=self.help,
            short_help=self.short_help,
            rich_help_panel=self.rich_help_panel,
        )
