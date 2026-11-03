"""Parse and validate the declarative Compute Gateway manifest."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit

DEFAULT_MANIFEST = "mgpux.gateway.toml"
DEFAULT_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
)

_APP_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_TASK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class GatewayConfigError(ValueError):
    """Raised when a gateway manifest is unsafe or malformed."""


@dataclass(frozen=True)
class GatewayTask:
    name: str
    description: str
    command: tuple[str, ...]
    packages: tuple[str, ...]
    gpu: str | tuple[str, ...] | None
    cpu: float | None
    memory: int | None
    timeout: int
    retries: int
    max_containers: int
    scaledown_window: int


@dataclass(frozen=True)
class GatewayConfig:
    manifest_path: Path
    name: str
    source: Path
    python_version: str
    max_input_bytes: int
    max_output_bytes: int
    excludes: tuple[str, ...]
    tasks: tuple[GatewayTask, ...]


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GatewayConfigError(f"{label} must be a TOML table")
    return dict(value)


def _string_list(value: Any, label: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise GatewayConfigError(f"{label} must be an array of non-empty strings")
    result = tuple(item.strip() for item in value)
    if not allow_empty and not result:
        raise GatewayConfigError(f"{label} must contain at least one item")
    return result


def _integer(value: Any, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise GatewayConfigError(f"{label} must be an integer from {low} to {high}")
    return value


def _optional_number(value: Any, label: str, low: float, high: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= float(value) <= high:
        raise GatewayConfigError(f"{label} must be a number from {low:g} to {high:g}")
    return float(value)


def _task(name: str, raw: Any) -> GatewayTask:
    if not _TASK_RE.fullmatch(name):
        raise GatewayConfigError(f"task name {name!r} must match {_TASK_RE.pattern}")
    data = _mapping(raw, f"tasks.{name}")
    command = _string_list(data.get("command"), f"tasks.{name}.command", allow_empty=False)
    packages = _string_list(data.get("packages", []), f"tasks.{name}.packages")
    description = data.get("description", "")
    if not isinstance(description, str):
        raise GatewayConfigError(f"tasks.{name}.description must be a string")

    gpu_raw = data.get("gpu")
    gpu: str | tuple[str, ...] | None
    if gpu_raw is None:
        gpu = None
    elif isinstance(gpu_raw, str) and gpu_raw.strip():
        gpu = gpu_raw.strip()
    elif isinstance(gpu_raw, (list, tuple)):
        gpu = _string_list(gpu_raw, f"tasks.{name}.gpu", allow_empty=False)
    else:
        raise GatewayConfigError(f"tasks.{name}.gpu must be a string or non-empty string array")

    memory = data.get("memory")
    if memory is not None:
        memory = _integer(memory, f"tasks.{name}.memory", 128, 1_048_576)
    return GatewayTask(
        name=name,
        description=description.strip(),
        command=command,
        packages=packages,
        gpu=gpu,
        cpu=_optional_number(data.get("cpu"), f"tasks.{name}.cpu", 0.125, 256),
        memory=memory,
        # Modal's servers reject timeouts below 10s, although the docs still say 1s.
        timeout=_integer(data.get("timeout", 300), f"tasks.{name}.timeout", 10, 86_400),
        retries=_integer(data.get("retries", 0), f"tasks.{name}.retries", 0, 10),
        max_containers=_integer(data.get("max_containers", 10), f"tasks.{name}.max_containers", 1, 1_000),
        scaledown_window=_integer(
            data.get("scaledown_window", 60),
            f"tasks.{name}.scaledown_window",
            2,
            1_200,
        ),
    )


def load_gateway_config(path: str | Path = DEFAULT_MANIFEST) -> GatewayConfig:
    """Load *path* and reject values that cannot be rendered safely."""
    manifest = Path(path).expanduser().resolve()
    if not manifest.is_file():
        raise GatewayConfigError(f"manifest not found: {manifest}")
    try:
        # ``utf-8-sig`` accepts both normal UTF-8 and the BOM emitted by some
        # Windows editors / PowerShell versions.
        document = tomlkit.loads(manifest.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise GatewayConfigError(f"invalid TOML in {manifest.name}: {exc}") from exc

    gateway = _mapping(document.get("gateway"), "gateway")
    name = gateway.get("name", "m-gpux-compute-gateway")
    if not isinstance(name, str) or not _APP_RE.fullmatch(name):
        raise GatewayConfigError(f"gateway.name must match {_APP_RE.pattern}")
    source_raw = gateway.get("source", ".")
    if not isinstance(source_raw, str) or not source_raw.strip():
        raise GatewayConfigError("gateway.source must be a non-empty path")
    source = (manifest.parent / source_raw).resolve()
    if not source.is_dir():
        raise GatewayConfigError(f"gateway.source is not a directory: {source}")

    python_version = gateway.get("python_version", "3.12")
    if not isinstance(python_version, str) or not re.fullmatch(r"3\.(?:10|11|12|13|14)", python_version):
        raise GatewayConfigError("gateway.python_version must be one of 3.10 through 3.14")
    excludes = _string_list(gateway.get("exclude", list(DEFAULT_EXCLUDES)), "gateway.exclude")

    tasks_raw = _mapping(document.get("tasks"), "tasks")
    if not tasks_raw:
        raise GatewayConfigError("manifest must declare at least one [tasks.<name>] table")
    tasks = tuple(_task(str(task_name), raw) for task_name, raw in tasks_raw.items())
    return GatewayConfig(
        manifest_path=manifest,
        name=name,
        source=source,
        python_version=python_version,
        max_input_bytes=_integer(gateway.get("max_input_bytes", 1_048_576), "gateway.max_input_bytes", 1, 10_485_760),
        max_output_bytes=_integer(
            gateway.get("max_output_bytes", 1_048_576), "gateway.max_output_bytes", 1_024, 10_485_760
        ),
        excludes=excludes,
        tasks=tasks,
    )
