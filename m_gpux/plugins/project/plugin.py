"""``project`` plugin — ``mgpux.toml``: ``init``, ``up``, ``sweep`` and ``runs``.

``m-gpux init`` writes a project file, ``m-gpux up TASK`` runs a task on Modal,
``m-gpux sweep TASK --grid lr=1e-4,3e-4`` fans a task out over a parameter grid
with ``Function.map``, and ``m-gpux runs`` lists the results. Every run is
recorded in ``~/.m-gpux/runs/<id>.json`` with per-job exit codes, timings,
reported metrics and an estimated cost.
"""

from __future__ import annotations

import json
import os
import secrets as pysecrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click
import typer
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table

from m_gpux.core.console import console
from m_gpux.core.notify import notify
from m_gpux.core.plugin import PluginBase
from m_gpux.core.project import (
    PROJECT_FILE,
    ProjectError,
    apply_params,
    estimate_cost,
    expand_grid,
    find_project,
    load_project,
    output_volume,
    parse_grid_args,
    pick_best,
    render_script,
    render_template,
)
from m_gpux.core.state import STATE_DIR, _read_json, _write_json, utc_now

RUNS_DIR = STATE_DIR / "runs"
EXTRA_ARGS = {"allow_extra_args": True, "ignore_unknown_options": True}

runs_app = typer.Typer(no_args_is_help=True, help="Results of `up` and `sweep` runs.")


def _fail(message: str) -> None:
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(1)


def _load(file: Optional[Path]) -> dict[str, Any]:
    path = file or find_project(Path.cwd())
    if path is None or not path.is_file():
        _fail(f"No {PROJECT_FILE} here or in a parent folder. Create one with: m-gpux init")
    try:
        return load_project(path)
    except ProjectError as exc:
        _fail(str(exc))
        raise  # unreachable; keeps type checkers happy


def resolve_account(explicit: Optional[str], from_project: Optional[str]) -> Optional[str]:
    """Profile to run as; ``None`` means ambient credentials (``MODAL_TOKEN_ID`` in CI)."""
    from m_gpux.core.profiles import get_all_profiles, get_best_profile, load_profiles

    choice = (explicit or from_project or "").strip()
    profiles = get_all_profiles()
    ambient = bool(os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET"))
    if choice == "env" or (not profiles and ambient and choice in ("", "auto")):
        if not ambient:
            _fail("--account env needs MODAL_TOKEN_ID and MODAL_TOKEN_SECRET in the environment.")
        return None
    if not profiles:
        _fail("No Modal profiles configured. Run `m-gpux account add`, or set MODAL_TOKEN_ID / MODAL_TOKEN_SECRET.")
    if choice == "auto":
        with console.status("Picking the account with the most credit left..."):
            best, left = get_best_profile()
        if not best:
            _fail("No account has spendable credit left this month.")
        console.print(f"[dim]AUTO account:[/dim] [bold]{best}[/bold] [dim](${left:.2f} left)[/dim]")
        return best
    if choice:
        if choice not in profiles:
            _fail(f"Unknown profile '{choice}'. Known: {', '.join(profiles)}")
        return choice
    return next((name for name, active in load_profiles() if active), profiles[0])


def _pick_task(project: dict[str, Any], name: Optional[str]) -> dict[str, Any]:
    tasks = project["tasks"]
    if name:
        if name not in tasks:
            _fail(f"No task '{name}'. Tasks: {', '.join(tasks)}")
        return tasks[name]
    if len(tasks) == 1:
        return next(iter(tasks.values()))
    from m_gpux.core.ui import arrow_select

    names = list(tasks)
    idx = arrow_select([(n, tasks[n]["command"]) for n in names], title="Task")
    return tasks[names[idx]]


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + pysecrets.token_hex(2)


def run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def _gpu_label(task: dict[str, Any]) -> str:
    if task["gpus"]:
        return " → ".join(task["gpus"])
    return f"CPU {task['cpu']:g} cores" + (f" / {task['memory']} MB" if task["memory"] else "")


def _money(value: float) -> str:
    return "<$0.001" if value < 0.001 else f"${value:.3f}" if value < 1 else f"${value:.2f}"


def _metrics_text(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    parts = [f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}" for k, v in list(result.items())[:4]]
    return ", ".join(parts)


def _results_table(record: dict[str, Any]) -> Table:
    table = Table(title=f"Run {record['id']} · {record.get('task')} · {record.get('status')}")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Params")
    table.add_column("Exit", justify="right")
    table.add_column("Time", justify="right")
    table.add_column("Result")
    best = record.get("best") or {}
    for r in record.get("results", []):
        code = r.get("exit_code")
        style = "green" if code == 0 else "red"
        marker = " [bold yellow]★[/bold yellow]" if best and r.get("index") == best.get("index") else ""
        table.add_row(
            str(r.get("index", "")),
            ", ".join(f"{k}={v}" for k, v in (r.get("params") or {}).items()) or "—",
            f"[{style}]{code}[/{style}]",
            f"{r.get('seconds', '?')}s",
            (_metrics_text(r.get("result")) or r.get("error", ""))[:80] + marker,
        )
    return table


def execute_run(
    project: dict[str, Any],
    task: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    kind: str,
    account: Optional[str],
    max_parallel: Optional[int] = None,
    metric: Optional[str] = None,
    mode: str = "min",
    yes: bool = False,
    dry_run: bool = False,
    download: bool = False,
) -> dict[str, Any]:
    """Render, run and record one ``up`` or ``sweep``; returns the run record."""
    run_id = new_run_id()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = run_path(run_id)
    script = render_script(project, task, jobs, run_id, path.as_posix(), max_parallel=max_parallel, kind=kind)
    if dry_run:
        console.print(Syntax(script, "python", theme="monokai", line_numbers=True))
        console.print(f"[dim]{len(jobs)} job(s); nothing was run (--dry-run).[/dim]")
        return {}

    record: dict[str, Any] = {
        "id": run_id,
        "kind": kind,
        "project": project["name"],
        "root": project["root"],
        "task": task["name"],
        "account": account or "env",
        "gpu": _gpu_label(task),
        "jobs": len(jobs),
        "metric": metric,
        "mode": mode,
        "status": "running",
        "started_at": utc_now(),
        "output_volume": output_volume(project),
        "results": [],
    }
    _write_json(path, record)
    failed_to_run = False
    try:
        from m_gpux.core.runner import execute_modal_temp_script

        execute_modal_temp_script(
            script,
            f"{kind} {project['name']}/{task['name']} ({len(jobs)} job{'s' if len(jobs) != 1 else ''})",
            profile=account,
            assume_yes=yes,
        )
    except click.exceptions.Exit as exc:
        failed_to_run = exc.exit_code != 0
    except KeyboardInterrupt:
        failed_to_run = True

    written = _read_json(path, {})
    results = written.get("results", []) if isinstance(written, dict) else []
    seconds = sum(float(r.get("seconds") or 0) for r in results)
    ok = bool(results) and all(r.get("exit_code") == 0 for r in results)
    record.update(
        results=results,
        finished_at=utc_now(),
        status="done" if ok else ("cancelled" if not results and not failed_to_run else "failed"),
        compute_seconds=round(seconds, 1),
        cost_estimate=estimate_cost(task, seconds),
    )
    best = pick_best(results, metric, mode)
    if best:
        record["best"] = {"index": best["index"], "params": best["params"], "result": best["result"]}
    _write_json(path, record)

    if results:
        console.print(_results_table(record))
    cost = record.get("cost_estimate")
    console.print(
        f"[dim]Compute {seconds:.0f}s"
        + (f" · ~{_money(cost)}" if cost is not None else "")
        + f" · outputs in volume [bold]{record['output_volume']}[/bold] under /{run_id}[/dim]"
    )
    if download and results:
        _download(record, account)
    _notify_run(record)
    return record


def _download(record: dict[str, Any], account: Optional[str]) -> None:
    from m_gpux.core.modal_cli import modal_cmd, modal_env

    dest = Path(record["root"]) / "outputs"
    dest.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]Downloading outputs to {dest}...[/cyan]")
    result = subprocess.run(
        modal_cmd("volume", "get", record["output_volume"], f"/{record['id']}", str(dest)),
        env=modal_env(account),
    )
    if result.returncode != 0:
        console.print("[yellow]Download failed; try: m-gpux volume get ...[/yellow]")


def _notify_run(record: dict[str, Any]) -> None:
    results = record.get("results", [])
    failed = sum(1 for r in results if r.get("exit_code") != 0)
    where = f"{record['project']}/{record['task']} on {record['gpu']} ({record['account']})"
    cost = record.get("cost_estimate")
    cost_text = f" · ~{_money(cost)}" if cost is not None else ""
    if record["kind"] == "sweep":
        best = record.get("best")
        best_text = f"\nBest: {best['params']} → {_metrics_text(best['result'])}" if best else ""
        notify(
            "sweep.done",
            f"Sweep {record['id']} finished: {len(results) - failed}/{record['jobs']} ok",
            f"{where}{cost_text}{best_text}",
            level="success" if not failed and results else "warning",
        )
        return
    ok = record["status"] == "done"
    tail = "" if ok or not results else "\n" + str(results[0].get("tail", ""))[-600:]
    notify(
        "run.done" if ok else "run.failed",
        f"{record['task']} {'finished' if ok else 'failed'} ({record['compute_seconds']:.0f}s)",
        f"{where}{cost_text}{tail}",
        level="success" if ok else "error",
    )


# ─── Commands ───────────────────────────────────────────────────


def init_command(
    command: Optional[str] = typer.Option(None, "--command", "-c", help="What the first task runs."),
    gpu: str = typer.Option("L4", "--gpu", help="Default GPU ('none' for CPU)."),
    github_action: bool = typer.Option(False, "--github-action", help="Also write a GitHub Actions workflow."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing mgpux.toml."),
) -> None:
    """Create mgpux.toml for this folder."""
    from m_gpux import __version__

    root = Path.cwd()
    target = root / PROJECT_FILE
    if target.exists() and not force:
        _fail(f"{PROJECT_FILE} already exists (use --force to overwrite).")
    script = next((n for n in ("train.py", "main.py", "app.py", "run.py") if (root / n).is_file()), None)
    if script is None:
        script = next((p.name for p in sorted(root.glob("*.py"))), "main.py")
    task = "train" if script == "train.py" else "main"
    name = "".join(ch if ch.isalnum() else "-" for ch in root.name.lower()).strip("-")[:40] or "project"
    text = render_template(
        name, command or f"python {script}", requirements=(root / "requirements.txt").is_file(), gpu=gpu, task=task
    )
    target.write_text(text, encoding="utf-8", newline="\n")
    console.print(f"[green]Wrote {target}[/green]")
    try:
        load_project(target)
    except ProjectError as exc:
        console.print(f"[yellow]Check the file: {exc}[/yellow]")
    if github_action:
        workflow = root / ".github" / "workflows" / "m-gpux.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(WORKFLOW.format(task=task, version=__version__), encoding="utf-8", newline="\n")
        console.print(
            f"[green]Wrote {workflow}[/green] [dim]Add MODAL_TOKEN_ID and MODAL_TOKEN_SECRET as repository secrets.[/dim]"
        )
    console.print(f"[dim]Next: m-gpux up {task}   ·   m-gpux sweep {task} --grid lr=1e-4,3e-4[/dim]")


def up_command(
    ctx: typer.Context,
    task_name: Optional[str] = typer.Argument(
        None, metavar="TASK", help="Task from mgpux.toml (default: the only one)."
    ),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile, 'auto' or 'env' (CI tokens)."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help=f"Path to {PROJECT_FILE}."),
    download: bool = typer.Option(False, "--download", help="Download the run's outputs to ./outputs when done."),
    yes: bool = typer.Option(False, "--yes", "-y", help="No prompts (CI)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the generated Modal app and stop."),
) -> None:
    """Run a task from mgpux.toml on Modal. Arguments after `--` are appended to its command."""
    project = _load(file)
    task = _pick_task(project, task_name)
    command = " ".join([task["command"], *ctx.args]) if ctx.args else task["command"]
    profile = None if dry_run else resolve_account(account, project["account"])
    console.print(
        Panel.fit(
            f"[bold]{project['name']}/{task['name']}[/bold]\n[dim]$[/dim] {command}\n"
            f"[dim]compute[/dim] {_gpu_label(task)}   [dim]timeout[/dim] {task['timeout'] // 60}m",
            title="m-gpux up",
            border_style="cyan",
        )
    )
    record = execute_run(
        project,
        task,
        [{"command": command, "params": {}}],
        kind="up",
        account=profile,
        yes=yes,
        dry_run=dry_run,
        download=download,
    )
    if record and record["status"] != "done":
        raise typer.Exit(1)


def sweep_command(
    name: str = typer.Argument(..., help="A [sweeps.*] name or a task name."),
    grid: Optional[list[str]] = typer.Option(None, "--grid", "-g", help="name=v1,v2 (repeatable)."),
    max_parallel: Optional[int] = typer.Option(None, "--max-parallel", "-p", help="Containers at once."),
    metric: Optional[str] = typer.Option(None, "--metric", help="Result key that ranks runs (e.g. loss)."),
    mode: Optional[str] = typer.Option(None, "--mode", help="min (default) or max."),
    max_runs: int = typer.Option(64, "--max-runs", help="Refuse grids larger than this."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Profile, 'auto' or 'env'."),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help=f"Path to {PROJECT_FILE}."),
    yes: bool = typer.Option(False, "--yes", "-y", help="No prompts."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the runs and the generated app, run nothing."),
) -> None:
    """Run a task once per combination of a parameter grid, in parallel.

    Parameters fill {name} placeholders in the command, or are appended as
    --name value. Each job also gets MGPUX_PARAM_<NAME> environment variables.
    Report metrics by printing `MGPUX_RESULT {"loss": 0.1}`.
    """
    project = _load(file)
    sweep = project["sweeps"].get(name)
    task = project["tasks"].get(sweep["task"] if sweep else name)
    if task is None:
        _fail(f"'{name}' is neither a sweep nor a task. Tasks: {', '.join(project['tasks'])}")
    try:
        merged = dict(sweep["grid"]) if sweep else {}
        merged.update(parse_grid_args(list(grid or [])) if grid else {})
        if not merged:
            _fail("Give a grid, e.g. --grid lr=1e-4,3e-4 --grid batch=16,32")
        combos = expand_grid(merged, limit=max_runs)
    except ProjectError as exc:
        _fail(str(exc))
        return
    metric = metric or (sweep or {}).get("metric")
    mode = (mode or (sweep or {}).get("mode") or "min").lower()
    if mode not in ("min", "max"):
        _fail("--mode must be min or max.")
    parallel = max_parallel or (sweep or {}).get("max_parallel") or task["max_parallel"]
    jobs = [{"command": apply_params(task["command"], params), "params": params} for params in combos]

    table = Table(title=f"Sweep {project['name']}/{task['name']} — {len(jobs)} runs, {parallel} at a time")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Command")
    for i, job in enumerate(jobs[:12]):
        table.add_row(str(i), job["command"])
    if len(jobs) > 12:
        table.add_row("…", f"{len(jobs) - 12} more")
    console.print(table)
    from m_gpux.core.pricing import fmt_hourly, gpu_hourly

    hourly = gpu_hourly(task["gpus"][0]) if task["gpus"] else None
    if hourly is not None:
        console.print(f"[dim]{_gpu_label(task)} at {fmt_hourly(hourly)} each, up to {parallel} at once.[/dim]")
    profile = None if dry_run else resolve_account(account, project["account"])
    if not (yes or dry_run) and not Confirm.ask(f"Launch {len(jobs)} runs?", default=True):
        raise typer.Exit(0)
    record = execute_run(
        project,
        task,
        jobs,
        kind="sweep",
        account=profile,
        max_parallel=parallel,
        metric=metric,
        mode=mode,
        yes=True,
        dry_run=dry_run,
    )
    if record.get("best"):
        best = record["best"]
        console.print(f"[bold yellow]★ Best[/bold yellow] {best['params']} → {_metrics_text(best['result'])}")
    if record and record["status"] != "done":
        raise typer.Exit(1)


def _gather(where: str, gpu: Optional[str], hours: float) -> list[dict[str, Any]]:
    """Ask each platform in scope what it can do right now; a missing CLI just drops that platform."""
    from m_gpux.core import router

    kaggle_rows = colab_rows = balances = None
    with console.status("Checking Kaggle, Colab and Modal capacity..."):
        if where in ("auto", "kaggle"):
            from m_gpux.core import kaggle

            if kaggle.executable() and kaggle.accounts():
                kaggle_rows = kaggle.overview()
        if where in ("auto", "colab"):
            from m_gpux.core import colab

            if colab.executable() and colab.account_names():
                colab_rows = colab.overview()
        if where in ("auto", "modal"):
            from m_gpux.core.profiles import get_all_balances

            balances = get_all_balances()
    return router.plan(gpu, hours, where=where, kaggle_rows=kaggle_rows, colab_rows=colab_rows, modal_balances=balances)


def _plan_table(candidates: list[dict[str, Any]], chosen: Optional[dict[str, Any]]) -> Table:
    table = Table(title="Where to run")
    table.add_column("", width=1)
    table.add_column("Platform")
    table.add_column("Account", style="cyan")
    table.add_column("GPU")
    table.add_column("Status")
    for c in candidates:
        mark = "[bold green]▶[/bold green]" if c is chosen else ""
        status = f"[green]{c['note']}[/green]" if c["ok"] else f"[dim]{c['note']}[/dim]"
        table.add_row(mark, c["platform"], c["account"], c["gpu"], status)
    return table


def _slug(text: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "script"


def _run_on_kaggle(account: str, script: Path, gpu: Optional[str]) -> None:
    import shutil
    import tempfile

    from m_gpux.core import kaggle, router

    acc = kaggle.get_account(account)
    slug = f"mgpux-{_slug(script.stem)}"
    with tempfile.TemporaryDirectory(prefix="mgpux-run-") as tmp:
        folder = Path(tmp) / slug
        folder.mkdir()
        shutil.copy2(script, folder / script.name)
        meta = router.kaggle_metadata(acc.name, slug, script.name, gpu)
        (folder / "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        try:
            pushed = kaggle.push_kernel(acc, folder)
        except kaggle.KaggleError as exc:
            _fail(f"Kaggle push failed: {exc}")
            return
    console.print(f"[green]Pushed to Kaggle as {pushed['ref']}[/green] (version {pushed.get('version') or '?'})")
    console.print(f"[dim]Follow it: m-gpux kaggle watch {pushed['ref']}[/dim]")


def _run_on_colab(account: str, script: Path, gpu: Optional[str], args: list[str]) -> None:
    from m_gpux.core import colab

    try:
        result = colab.run(account, ["run", "--gpu", gpu or "T4", str(script), *args], interactive=True, timeout=None)
    except colab.ColabError as exc:
        _fail(str(exc))
        return
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _run_on_modal(account: str, script: Path, gpu: Optional[str], hours: float, args: list[str], yes: bool) -> None:
    import shlex

    from m_gpux.core.project import resolve_task

    root = script.parent.resolve()
    command = " ".join(["python", shlex.quote(script.name), *(shlex.quote(a) for a in args)])
    raw: dict[str, Any] = {"command": command, "gpu": gpu or "T4", "timeout": int(min(max(hours, 0.1), 24) * 3600)}
    if (root / "requirements.txt").is_file():
        raw["requirements"] = "requirements.txt"
    try:
        task = resolve_task(raw, "run", root)
    except ProjectError as exc:
        _fail(str(exc))
        return
    project = {"name": _slug(root.name), "root": root.as_posix(), "account": None, "tasks": {"run": task}, "sweeps": {}}
    record = execute_run(project, task, [{"command": command, "params": {}}], kind="run", account=account, yes=yes)
    if record and record["status"] != "done":
        raise typer.Exit(1)


def run_command(
    ctx: typer.Context,
    script: Path = typer.Argument(..., help="Python script to run. Arguments after `--` go to it."),
    gpu: Optional[str] = typer.Option(None, "--gpu", help="T4, P100, L4, A100, H100... (default: cheapest fit)."),
    hours: float = typer.Option(1.0, "--hours", help="Expected run time, used to check quota and credit."),
    where: str = typer.Option("auto", "--where", "-w", help="auto, kaggle, colab or modal."),
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Force one account on the chosen platform."),
    plan_only: bool = typer.Option(False, "--plan", help="Show the plan and stop."),
    yes: bool = typer.Option(False, "--yes", "-y", help="No prompts."),
) -> None:
    """Run a script wherever there is capacity: free Kaggle quota, Colab, then Modal credit."""
    if where not in ("auto", "kaggle", "colab", "modal"):
        _fail("--where must be auto, kaggle, colab or modal.")
    if not script.is_file():
        _fail(f"{script} does not exist.")
    candidates = _gather(where, gpu, hours)
    usable = [c for c in candidates if c["ok"] and (account is None or c["account"] == account)]
    chosen = usable[0] if usable else None
    if candidates:
        console.print(_plan_table(candidates, chosen))
    if chosen is None:
        _fail("Nothing can take this job right now (see the table above).")
        return
    if plan_only:
        return
    console.print(f"[bold]→ {chosen['platform']}[/bold] as [cyan]{chosen['account']}[/cyan] on {chosen['gpu']}")
    if not yes and not Confirm.ask("Run it there?", default=True):
        raise typer.Exit(0)
    if chosen["platform"] == "kaggle":
        if ctx.args:
            console.print("[yellow]Kaggle scripts take no command-line arguments; ignoring them.[/yellow]")
        _run_on_kaggle(chosen["account"], script, gpu)
    elif chosen["platform"] == "colab":
        _run_on_colab(chosen["account"], script, chosen["gpu"], list(ctx.args))
    else:
        _run_on_modal(chosen["account"], script, chosen["gpu"], hours, list(ctx.args), yes)


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    if not RUNS_DIR.is_dir():
        return []
    records = []
    for path in sorted(RUNS_DIR.glob("*.json"), reverse=True)[:limit]:
        data = _read_json(path, None)
        if isinstance(data, dict) and data.get("id"):
            records.append(data)
    return records


@runs_app.command("list")
def runs_list(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """Recent `up` and `sweep` runs."""
    records = list_runs(limit)
    if not records:
        console.print("[yellow]No runs yet. Try: m-gpux up[/yellow]")
        return
    table = Table(title="Runs")
    table.add_column("ID", style="cyan")
    table.add_column("Kind")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("Jobs", justify="right")
    table.add_column("Compute", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Best")
    for r in records:
        status = r.get("status", "?")
        style = {"done": "green", "failed": "red", "running": "cyan"}.get(status, "yellow")
        cost = r.get("cost_estimate")
        best = r.get("best")
        table.add_row(
            r["id"],
            r.get("kind", ""),
            f"{r.get('project')}/{r.get('task')}",
            f"[{style}]{status}[/{style}]",
            str(r.get("jobs", "")),
            f"{r.get('compute_seconds', 0):.0f}s",
            _money(cost) if isinstance(cost, (int, float)) else "—",
            _metrics_text(best["result"]) if best else "",
        )
    console.print(table)


@runs_app.command("show")
def runs_show(
    run_id: str = typer.Argument(..., help="Run ID from `m-gpux runs list`."),
    as_json: bool = typer.Option(False, "--json", help="Print the raw record."),
) -> None:
    """One run's jobs, metrics and failures."""
    record = _read_json(run_path(run_id), None) if run_id.replace("-", "").isalnum() else None
    if not isinstance(record, dict):
        _fail(f"No run '{run_id}'.")
    if as_json:
        console.print_json(json.dumps(record))
        return
    console.print(_results_table(record))
    for r in record.get("results", []):
        if r.get("exit_code") != 0 and r.get("tail"):
            console.print(
                Panel(str(r["tail"])[-1500:], title=f"job {r.get('index')} output (tail)", border_style="red")
            )
    console.print(
        f"[dim]Outputs: m-gpux volume get {record.get('output_volume')} /{record['id']} ./outputs"
        + (f" --account {record['account']}" if record.get("account") not in (None, "env") else "")
        + "[/dim]"
    )


WORKFLOW = """name: m-gpux

on:
  workflow_dispatch:
    inputs:
      task:
        description: Task from mgpux.toml
        default: {task}

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 360
    steps:
      - uses: actions/checkout@v4
      - uses: PuxHocDL/m-gpux@v{version}
        with:
          task: ${{{{ inputs.task }}}}
          modal-token-id: ${{{{ secrets.MODAL_TOKEN_ID }}}}
          modal-token-secret: ${{{{ secrets.MODAL_TOKEN_SECRET }}}}
"""


class ProjectPlugin(PluginBase):
    name = "project"
    help = "mgpux.toml projects: init, up, sweep and run history."
    rich_help_panel = "Compute Engine"

    def register(self, root_app):
        root_app.command("init", help="Create mgpux.toml for this folder.", rich_help_panel="Start here")(init_command)
        root_app.command(
            "up",
            help="Run a task from mgpux.toml on Modal.",
            context_settings=EXTRA_ARGS,
            rich_help_panel=self.rich_help_panel,
        )(up_command)
        root_app.command("sweep", help="Run a task over a parameter grid.", rich_help_panel=self.rich_help_panel)(
            sweep_command
        )
        root_app.command(
            "run",
            help="Run a script wherever there is capacity: Kaggle, Colab or Modal.",
            context_settings=EXTRA_ARGS,
            rich_help_panel=self.rich_help_panel,
        )(run_command)
        root_app.add_typer(runs_app, name="runs", rich_help_panel=self.rich_help_panel)
