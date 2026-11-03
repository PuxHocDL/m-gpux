"""``mgpux.toml`` project files: one declarative file per repo.

A project file names the tasks a repo runs on Modal (command, GPU, image,
secrets, volumes...), so anyone who clones it runs ``m-gpux up train`` instead
of re-answering the Hub wizard. ``m-gpux sweep`` reuses the same task with a
parameter grid, fanned out with ``Function.map``.

Everything here is pure (parse → validate → render) so it is unit-tested; the
``project`` plugin does the I/O.

Layout::

    [project]
    name = "demo"
    account = "auto"          # a profile name, "auto" (most credit) or omit for the active one

    [defaults]                # applied to every task
    python = "3.12"
    gpu = "L4"                # "H100", ["H100", "A100-80GB"] (fallback order) or "none"
    requirements = "requirements.txt"

    [tasks.train]
    command = "python train.py --epochs 3"

    [sweeps.lr]
    task = "train"
    grid = { lr = [1e-4, 3e-4], batch = [16, 32] }
"""

from __future__ import annotations

import itertools
import json
import re
import shlex
from pathlib import Path
from typing import Any, Optional

PROJECT_FILE = "mgpux.toml"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
TASK_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
PARAM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PYTHON_RE = re.compile(r"^3\.(1[0-9]|9)$")
VOLUME_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_SWEEP_RUNS = 256

DEFAULT_EXCLUDE = [
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "*.pyc",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ipynb_checkpoints",
    "outputs",
    "modal_runner.py",
]

TASK_KEYS = {
    "command": "Shell command run in /workspace",
    "gpu": 'GPU type, a fallback list ["H100", "A100-80GB"], or "none" for CPU only',
    "gpu_count": "GPUs per container (1-8)",
    "cpu": "CPU cores",
    "memory": "Memory in MB",
    "timeout": "Max run time: seconds or 30m / 2h (10s-24h)",
    "python": "Python version for the image (3.10-3.14)",
    "image": "A published image (m-gpux image build) instead of debian_slim",
    "requirements": "requirements.txt path, relative to the project",
    "pip": "Extra pip packages",
    "apt": "Extra apt packages",
    "env": "Environment variables (not secret)",
    "secrets": "Modal Secret names (m-gpux secrets sync)",
    "volumes": 'Extra volumes: { "/data" = "my-dataset" }',
    "hf_cache": "Mount the shared Hugging Face cache volume (default true)",
    "exclude": "Patterns not uploaded to /workspace",
    "max_parallel": "Containers at once for sweeps (default 4)",
    "retries": "Retries per job on container failure (0-5)",
}


class ProjectError(ValueError):
    """The project file is missing or invalid."""


# ─── Parsing ────────────────────────────────────────────────────


def find_project(start: Path) -> Optional[Path]:
    """The nearest ``mgpux.toml`` in *start* or a parent directory."""
    start = start.resolve()
    for folder in [start, *start.parents]:
        candidate = folder / PROJECT_FILE
        if candidate.is_file():
            return candidate
    return None


def load_project(path: Path) -> dict[str, Any]:
    import tomlkit

    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8")).unwrap()
    except Exception as exc:  # tomlkit raises several parse error types
        raise ProjectError(f"{path.name}: {exc}") from exc
    return validate_project(doc, path.parent)


def parse_timeout(value: Any) -> int:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = int(value)
    else:
        text = str(value).strip().lower()
        units = {"s": 1, "m": 60, "h": 3600}
        try:
            seconds = int(float(text[:-1]) * units[text[-1]]) if text and text[-1] in units else int(float(text))
        except (ValueError, KeyError) as exc:
            raise ProjectError(f"timeout '{value}' is not seconds or a duration like 30m / 2h.") from exc
    if not 10 <= seconds <= 86400:
        raise ProjectError("timeout must be between 10s and 24h (Modal's limits).")
    return seconds


def _str_list(value: Any, key: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ProjectError(f"'{key}' must be a list of strings.")
    return [v.strip() for v in value]


def _gpu_list(value: Any) -> list[str]:
    from m_gpux.core.gpus import GPU_MAX_COUNT

    if value in (None, "", "none", "cpu", False):
        return []
    gpus = _str_list(value, "gpu")
    unknown = [g for g in gpus if g not in GPU_MAX_COUNT]
    if unknown:
        raise ProjectError(f"Unknown GPU(s): {', '.join(unknown)}. Known: {', '.join(GPU_MAX_COUNT)}.")
    return gpus


def resolve_task(raw: dict[str, Any], name: str, root: Path) -> dict[str, Any]:
    """Validate one merged task table and normalise its values."""
    unknown = sorted(set(raw) - set(TASK_KEYS))
    if unknown:
        raise ProjectError(f"task '{name}': unknown key(s) {', '.join(unknown)}.")
    command = raw.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ProjectError(f"task '{name}': 'command' is required.")
    gpus = _gpu_list(raw.get("gpu"))
    count = int(raw.get("gpu_count", 1))
    if not 1 <= count <= 8:
        raise ProjectError(f"task '{name}': gpu_count must be 1-8.")
    python = str(raw.get("python", "3.12"))
    if not PYTHON_RE.match(python):
        raise ProjectError(f"task '{name}': python must look like 3.12.")
    requirements = raw.get("requirements")
    if requirements is not None:
        req_path = (root / str(requirements)).resolve()
        if not req_path.is_file():
            raise ProjectError(f"task '{name}': {requirements} not found.")
        requirements = req_path.as_posix()
    env = raw.get("env") or {}
    if not isinstance(env, dict) or not all(PARAM_RE.match(str(k)) for k in env):
        raise ProjectError(f"task '{name}': env must be a table of NAME = value.")
    volumes = raw.get("volumes") or {}
    if not isinstance(volumes, dict):
        raise ProjectError(f'task \'{name}\': volumes must be a table of "/path" = "volume-name".')
    for mount, vol in volumes.items():
        if not str(mount).startswith("/") or str(mount).rstrip("/") in ("", "/workspace", "/outputs"):
            raise ProjectError(
                f"task '{name}': volume mount '{mount}' must be an absolute path other than /workspace and /outputs."
            )
        if not VOLUME_NAME_RE.match(str(vol)):
            raise ProjectError(f"task '{name}': '{vol}' is not a valid volume name.")
    cpu = raw.get("cpu")
    memory = raw.get("memory")
    max_parallel = int(raw.get("max_parallel", 4))
    retries = int(raw.get("retries", 0))
    if not 1 <= max_parallel <= 100:
        raise ProjectError(f"task '{name}': max_parallel must be 1-100.")
    if not 0 <= retries <= 5:
        raise ProjectError(f"task '{name}': retries must be 0-5.")
    image = raw.get("image")
    if image is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*(:[A-Za-z0-9._-]+)?", str(image)):
        raise ProjectError(f"task '{name}': '{image}' is not a valid image name.")
    return {
        "name": name,
        "command": command.strip(),
        "gpus": [g if count == 1 else f"{g}:{count}" for g in gpus],
        "cpu": float(cpu) if cpu is not None else (None if gpus else 2.0),
        "memory": int(memory) if memory is not None else None,
        "timeout": parse_timeout(raw.get("timeout", "1h")),
        "python": python,
        "image": str(image) if image else None,
        "requirements": requirements,
        "pip": _str_list(raw.get("pip"), "pip"),
        "apt": _str_list(raw.get("apt"), "apt"),
        "env": {str(k): str(v) for k, v in env.items()},
        "secrets": _str_list(raw.get("secrets"), "secrets"),
        "volumes": {str(k).rstrip("/"): str(v) for k, v in volumes.items()},
        "hf_cache": bool(raw.get("hf_cache", True)),
        "exclude": _str_list(raw.get("exclude"), "exclude") or list(DEFAULT_EXCLUDE),
        "max_parallel": max_parallel,
        "retries": retries,
    }


def validate_project(doc: dict[str, Any], root: Path) -> dict[str, Any]:
    allowed = {"project", "defaults", "tasks", "sweeps"}
    unknown = sorted(set(doc) - allowed)
    if unknown:
        raise ProjectError(
            f"Unknown top-level key(s): {', '.join(unknown)}. Use [project], [defaults], [tasks.*], [sweeps.*]."
        )
    meta = doc.get("project") or {}
    name = str(meta.get("name") or root.name).lower()
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")[:40] or "project"
    if not NAME_RE.match(name):
        raise ProjectError("[project] name must use lowercase letters, digits and '-'.")
    defaults = doc.get("defaults") or {}
    tasks_raw = doc.get("tasks") or {}
    if not isinstance(tasks_raw, dict) or not tasks_raw:
        raise ProjectError('Declare at least one task, e.g. [tasks.train] with command = "python train.py".')
    tasks = {}
    for task_name, table in tasks_raw.items():
        if not TASK_NAME_RE.match(task_name):
            raise ProjectError(f"Task name '{task_name}' must use letters, digits, '_' and '-'.")
        if not isinstance(table, dict):
            raise ProjectError(f"[tasks.{task_name}] must be a table.")
        tasks[task_name] = resolve_task({**defaults, **table}, task_name, root)
    sweeps = {}
    for sweep_name, table in (doc.get("sweeps") or {}).items():
        task = str(table.get("task", ""))
        if task not in tasks:
            raise ProjectError(f"[sweeps.{sweep_name}] task '{task}' is not declared.")
        sweeps[sweep_name] = {
            "task": task,
            "grid": validate_grid(table.get("grid") or {}),
            "max_parallel": int(table.get("max_parallel", tasks[task]["max_parallel"])),
            "metric": table.get("metric"),
            "mode": str(table.get("mode", "min")),
        }
    return {
        "name": name,
        "root": root.resolve().as_posix(),
        "account": str(meta["account"]) if meta.get("account") else None,
        "tasks": tasks,
        "sweeps": sweeps,
    }


# ─── Sweeps ─────────────────────────────────────────────────────


def validate_grid(grid: Any) -> dict[str, list[Any]]:
    if not isinstance(grid, dict) or not grid:
        raise ProjectError("A sweep needs a grid, e.g. grid = { lr = [1e-4, 3e-4] }.")
    clean = {}
    for key, values in grid.items():
        if not PARAM_RE.match(str(key)):
            raise ProjectError(f"Grid parameter '{key}' must be a valid identifier.")
        values = values if isinstance(values, list) else [values]
        if not values:
            raise ProjectError(f"Grid parameter '{key}' has no values.")
        clean[str(key)] = values
    return clean


def parse_grid_args(items: list[str]) -> dict[str, list[Any]]:
    """``["lr=1e-4,3e-4", "bs=16,32"]`` → ``{"lr": [...], "bs": [...]}`` (numbers stay numbers)."""
    grid: dict[str, list[Any]] = {}
    for item in items:
        key, sep, values = item.partition("=")
        if not sep or not values.strip():
            raise ProjectError(f"--grid '{item}' must look like name=v1,v2.")
        grid[key.strip()] = [_coerce(v.strip()) for v in values.split(",") if v.strip()]
    return validate_grid(grid)


def _coerce(text: str) -> Any:
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def expand_grid(grid: dict[str, list[Any]], limit: int = MAX_SWEEP_RUNS) -> list[dict[str, Any]]:
    keys = list(grid)
    total = 1
    for values in grid.values():
        total *= len(values)
    if total > limit:
        raise ProjectError(f"The grid makes {total} runs (limit {limit}). Narrow it or pass --max-runs.")
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*(grid[k] for k in keys))]


def apply_params(command: str, params: dict[str, Any]) -> str:
    """Fill ``{name}`` placeholders; parameters without one are appended as ``--name value``."""
    used: set[str] = set()

    def fill(match: re.Match) -> str:
        key = match.group(1)
        if key not in params:
            return match.group(0)
        used.add(key)
        return shlex.quote(str(params[key]))

    out = re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", fill, command)
    extra = [f"--{k} {shlex.quote(str(v))}" for k, v in params.items() if k not in used]
    return " ".join([out, *extra])


def pick_best(results: list[dict[str, Any]], metric: Optional[str], mode: str = "min") -> Optional[dict[str, Any]]:
    """The successful run with the lowest (or highest) ``result[metric]``."""
    if not metric:
        return None
    scored = [
        r
        for r in results
        if r.get("exit_code") == 0
        and isinstance(r.get("result"), dict)
        and isinstance(r["result"].get(metric), (int, float))
    ]
    if not scored:
        return None
    return (max if mode == "max" else min)(scored, key=lambda r: r["result"][metric])


# ─── Rendering ──────────────────────────────────────────────────

SCRIPT = """
import json
import os
import subprocess
import time
from collections import deque

import modal

# __METRICS__

RUN_ID = __RUN_ID__
JOBS = __JOBS__
RESULTS_PATH = __RESULTS_PATH__
OUTPUT_VOLUME = __OUTPUT_VOLUME__

app = modal.App(__APP_NAME__)
image = __IMAGE__
outputs = modal.Volume.from_name(OUTPUT_VOLUME, create_if_missing=True)
volumes = {"/outputs": outputs}
for _path, _name in __VOLUMES__.items():
    volumes[_path] = modal.Volume.from_name(_name, create_if_missing=True)
secrets = [modal.Secret.from_name(_n) for _n in __SECRETS__]


@app.function(
    image=image,
    __COMPUTE__,
    timeout=__TIMEOUT__,
    secrets=secrets,
    volumes=volumes,
    max_containers=__MAX_PARALLEL__,
    retries=__RETRIES__,
)
def run_job(index: int, command: str, params: dict) -> dict:
    _print_metrics()
    out_dir = f"/outputs/{RUN_ID}/{index}"
    os.makedirs(out_dir, exist_ok=True)
    env = {
        **os.environ,
        "MGPUX_RUN_ID": RUN_ID,
        "MGPUX_JOB_INDEX": str(index),
        "MGPUX_OUTPUT_DIR": out_dir,
        "MGPUX_PARAMS": json.dumps(params),
    }
    env.update({"MGPUX_PARAM_" + key.upper(): str(value) for key, value in params.items()})
    print(f"[m-gpux] job {index}: {command}", flush=True)
    started = time.time()
    tail = deque(maxlen=60)
    result = None
    proc = subprocess.Popen(
        command, shell=True, cwd="/workspace", env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    for line in proc.stdout:
        print(line, end="", flush=True)
        tail.append(line)
        if line.startswith("MGPUX_RESULT "):
            try:
                result = json.loads(line[len("MGPUX_RESULT "):])
            except ValueError:
                pass
    code = proc.wait()
    result_file = os.path.join(out_dir, "result.json")
    if result is None and os.path.exists(result_file):
        try:
            with open(result_file, encoding="utf-8") as f:
                result = json.load(f)
        except ValueError:
            pass
    outputs.commit()
    return {
        "index": index,
        "params": params,
        "exit_code": code,
        "seconds": round(time.time() - started, 1),
        "result": result,
        "tail": "".join(tail)[-3000:],
    }


@app.local_entrypoint()
def main():
    results = []
    calls = run_job.map(
        range(len(JOBS)),
        [job["command"] for job in JOBS],
        [job["params"] for job in JOBS],
        return_exceptions=True,
    )
    for index, item in enumerate(calls):
        if isinstance(item, BaseException):
            item = {"index": index, "params": JOBS[index]["params"], "exit_code": -1, "error": repr(item)[:500]}
        results.append(item)
        print(f"[m-gpux] job {index} done: exit {item.get('exit_code')} in {item.get('seconds', '?')}s", flush=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"run_id": RUN_ID, "results": results}, f, indent=2)
"""


def output_volume(project: dict[str, Any]) -> str:
    return f"m-gpux-{project['name']}-outputs"[:64]


def image_expr(task: dict[str, Any], root: str) -> str:
    from m_gpux.core.ignore import to_recursive_ignore

    expr = (
        f"modal.Image.from_name({task['image']!r})"
        if task["image"]
        else f"modal.Image.debian_slim(python_version={task['python']!r})"
    )
    if task["apt"]:
        expr += f".apt_install(*{task['apt']!r})"
    if task["requirements"]:
        expr += f".pip_install_from_requirements({task['requirements']!r})"
    if task["pip"]:
        expr += f".pip_install(*{task['pip']!r})"
    if task["env"]:
        expr += f".env({task['env']!r})"
    expr += f'.add_local_dir({root!r}, remote_path="/workspace", ignore={to_recursive_ignore(task["exclude"])!r})'
    return expr


def compute_expr(task: dict[str, Any]) -> str:
    parts = []
    if task["gpus"]:
        parts.append(f"gpu={task['gpus'][0]!r}" if len(task["gpus"]) == 1 else f"gpu={task['gpus']!r}")
    if task["cpu"] is not None:
        parts.append(f"cpu={task['cpu']!r}")
    if task["memory"] is not None:
        parts.append(f"memory={task['memory']!r}")
    return ", ".join(parts) or "cpu=2.0"


def render_script(
    project: dict[str, Any],
    task: dict[str, Any],
    jobs: list[dict[str, Any]],
    run_id: str,
    results_path: str,
    *,
    max_parallel: Optional[int] = None,
    kind: str = "up",
) -> str:
    """The Modal app for one ``up`` (one job) or ``sweep`` (many jobs)."""
    volumes = dict(task["volumes"])
    if task["hf_cache"]:
        volumes.setdefault("/root/.cache/huggingface", "m-gpux-hf-cache")
    app_name = f"m-gpux-{kind}-{project['name']}"[:64]
    replacements = {
        "__RUN_ID__": repr(run_id),
        "__JOBS__": "json.loads(" + repr(json.dumps(jobs)) + ")",
        "__RESULTS_PATH__": repr(results_path),
        "__OUTPUT_VOLUME__": repr(output_volume(project)),
        "__APP_NAME__": repr(app_name),
        "__IMAGE__": image_expr(task, project["root"]),
        "__VOLUMES__": repr(volumes),
        "__COMPUTE__": compute_expr(task),
        "__TIMEOUT__": repr(task["timeout"]),
        "__SECRETS__": repr(task["secrets"]),
        "__MAX_PARALLEL__": repr(max_parallel or task["max_parallel"]),
        "__RETRIES__": repr(task["retries"]),
    }
    script = SCRIPT
    for marker, value in replacements.items():
        script = script.replace(marker, value)
    return script.lstrip()


def estimate_cost(task: dict[str, Any], seconds: float) -> Optional[float]:
    """GPU (first choice) or CPU cost for *seconds* of compute, from the cached rates."""
    from m_gpux.core.pricing import cpu_hourly, gpu_hourly

    if task["gpus"]:
        hourly = gpu_hourly(task["gpus"][0])
        if hourly is None:
            return None
    else:
        hourly = cpu_hourly(task["cpu"] or 2.0, task["memory"] or 2048)
    return hourly * seconds / 3600


TEMPLATE = """# m-gpux project file — https://puxhocdl.github.io/m-gpux/projects/
# Run a task:  m-gpux up {task}
# Sweep it:    m-gpux sweep {task} --grid lr=1e-4,3e-4

[project]
name = "{name}"
# account = "auto"      # a profile name, "auto" (most credit left), or omit for the active one

[defaults]
python = "3.12"
gpu = "{gpu}"            # or ["H100", "A100-80GB"] to fall back, or "none" for CPU
timeout = "2h"
{requirements}# pip = ["torch"]
# secrets = ["hf"]      # m-gpux secrets sync hf HF_TOKEN --to all
# volumes = {{ "/data" = "my-dataset" }}
# hf_cache = true       # shared Hugging Face cache volume

[tasks.{task}]
command = "{command}"
# Print `MGPUX_RESULT {{"loss": 0.12}}` (or write $MGPUX_OUTPUT_DIR/result.json)
# to report metrics; files in $MGPUX_OUTPUT_DIR land in the outputs volume.

# [sweeps.lr]
# task = "{task}"
# grid = {{ lr = [1e-4, 3e-4], batch = [16, 32] }}
# metric = "loss"
# mode = "min"
"""


def render_template(name: str, command: str, *, requirements: bool, gpu: str = "L4", task: str = "main") -> str:
    req = 'requirements = "requirements.txt"\n' if requirements else '# requirements = "requirements.txt"\n'
    return TEMPLATE.format(name=name, command=command.replace('"', '\\"'), requirements=req, gpu=gpu, task=task)
