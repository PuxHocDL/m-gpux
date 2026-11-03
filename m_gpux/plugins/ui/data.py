"""What the local dashboard shows and does.

Reads use public interfaces only: ``modal ... --json`` for apps and containers
(the same calls ``m-gpux stop`` makes), the SDK for workspaces, sandboxes and
billing, and m-gpux's own state files. Per-account work fans out over a thread
pool and is cached briefly, so the page stays fast with many accounts.

Nothing returned from this module ever contains a token secret or an API key.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

import tomlkit

from m_gpux import __version__
from m_gpux.core.budget import budget_for, clear_budget, load_budgets, set_budget, spendable
from m_gpux.core.modal_cli import modal_cmd, modal_env, stop_app
from m_gpux.core.profiles import MONTHLY_CREDIT, load_config, save_config
from m_gpux.core.runner import ALIVE_APP_STATES

PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._'-]{0,63}$")
MODAL_ID = re.compile(r"^[a-z]{2}-[A-Za-z0-9]{1,64}$")
CLI_TIMEOUT = 45


class ActionError(Exception):
    """A user-facing failure (bad input, unknown resource, Modal refused)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ─── Cache ────────────────────────────────────────────────────

_cache: dict[tuple, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


def cached(ttl: float) -> Callable:
    """Memoise a function per argument tuple for *ttl* seconds (``refresh=True`` bypasses)."""

    def decorate(fn: Callable) -> Callable:
        def wrapper(*args: Any, refresh: bool = False) -> Any:
            key = (fn.__name__, args)
            with _batch_locks.setdefault(f"{fn.__name__}{args}", threading.Lock()):
                with _cache_lock:
                    hit = _cache.get(key)
                age = time.monotonic() - hit[0] if hit else None
                # A refresh within 2 s of the last fetch reuses it (another tab or page just did it).
                if hit and age < (2 if refresh else ttl):
                    return hit[1]
                value = fn(*args)
                with _cache_lock:
                    _cache[key] = (time.monotonic(), value)
                return value

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorate


def invalidate(*names: str) -> None:
    """Drop cached results for the named functions (all of them when none given)."""
    with _cache_lock:
        for key in [k for k in _cache if not names or k[0] in names]:
            del _cache[key]


ERROR_TTL = 60
SDK_TIMEOUT = 120
_batch_locks: dict[str, threading.Lock] = {}
_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_lock = threading.Lock()
SDK_WARMUP_WAIT = 20
_sdk_ready = threading.Event()
_sdk_ready.set()  # only cleared while prefetch() warms up the SDK clients


def _run_async(coro: Any) -> Any:
    """Run *coro* on the dashboard's single background event loop and wait for it.

    Modal's ``.aio`` calls hang (then raise TimeoutError) when two request
    threads each drive their own ``asyncio.run`` loop at the same time, which is
    exactly what the overview page does. One shared loop avoids that while still
    running every account concurrently.
    """
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="m-gpux-ui-modal", daemon=True).start()
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(SDK_TIMEOUT)


def _batch(name: str, profiles_: list[str], fetch: Callable, ttl: float, refresh: bool) -> dict[str, Any]:
    """Fetch per-account data concurrently on one event loop, with per-account caching.

    Modal's blocking calls made from several threads end up queued behind each
    other, so SDK fan-out goes through ``.aio`` and ``asyncio.gather`` on the
    shared loop instead (7 accounts: ~9 s rather than ~30 s). Failures come back
    as exceptions and are cached for ``ERROR_TTL`` only, so a broken account is
    retried soon.
    """
    with _batch_locks.setdefault(name, threading.Lock()):  # concurrent page loads share one fetch
        now = time.monotonic()
        with _cache_lock:
            known = {p: _cache[(name, (p,))] for p in profiles_ if (name, (p,)) in _cache}
        stale = [
            p
            for p in profiles_
            if (refresh and now - known.get(p, (0,))[0] >= 2) or p not in known or now - known[p][0] >= ttl
        ]
        if stale:

            async def gather() -> list[Any]:
                return await asyncio.gather(*(fetch(p) for p in stale), return_exceptions=True)

            results = _run_async(gather())
            with _cache_lock:
                for profile, result in zip(stale, results, strict=True):
                    shorten = ttl - ERROR_TTL if isinstance(result, BaseException) and ttl > ERROR_TTL else 0
                    _cache[(name, (profile,))] = (time.monotonic() - shorten, result)
        with _cache_lock:
            return {p: _cache[(name, (p,))][1] for p in profiles_}


def _error_text(exc: BaseException) -> str:
    return str(exc)[:300] or type(exc).__name__


# ─── Helpers ──────────────────────────────────────────────────


def profiles() -> list[tuple[str, bool]]:
    doc = load_config()
    return [(name, bool(doc[name].get("active", False))) for name in doc]


def _require_profile(profile: str) -> None:
    if profile not in {name for name, _ in profiles()}:
        raise ActionError(f"unknown account {profile!r}", 404)


def _require_id(value: str, kind: str) -> str:
    if not MODAL_ID.fullmatch(value):
        raise ActionError(f"invalid {kind} id", 400)
    return value


def _credentials(profile: str) -> tuple[str, str]:
    doc = load_config()
    if profile not in doc:
        raise ActionError(f"unknown account {profile!r}", 404)
    return str(doc[profile]["token_id"]), str(doc[profile]["token_secret"])


def _client(profile: str):
    import modal

    return modal.Client.from_credentials(*_credentials(profile))


_clients: dict[str, tuple[tuple[str, str], Any]] = {}
_client_locks: dict[str, asyncio.Lock] = {}


async def _aclient(profile: str):
    """One reused client per account, created on the shared loop.

    Creating two clients for the same token concurrently (the overview loads
    accounts and sandboxes at once) hangs until Modal's timeout; reusing one
    also skips the handshake on every refresh.
    """
    import modal

    credentials = _credentials(profile)
    async with _client_locks.setdefault(profile, asyncio.Lock()):
        cached = _clients.get(profile)
        if cached and cached[0] == credentials:
            return cached[1]
        client = await modal.Client.from_credentials.aio(*credentials)
        _clients[profile] = (credentials, client)
        return client


def _fan_out(fn: Callable[[str], Any], names: list[str], refresh: bool) -> tuple[list[Any], list[dict[str, str]]]:
    """Run ``fn(profile)`` for every profile in parallel; collect results and per-account errors."""
    if not names:
        return [], []

    def run(name: str) -> tuple[str, Any, Optional[str]]:
        try:
            return name, fn(name, refresh=refresh), None
        except Exception as exc:  # one broken account must not blank the page
            return name, None, str(exc)[:300] or type(exc).__name__

    # Each worker runs a `modal` CLI process; on a cold start these wait for the
    # SDK warm-up (`_collect`) so they don't starve its first handshakes.
    with ThreadPoolExecutor(max_workers=min(8, len(names))) as pool:
        outcomes = list(pool.map(run, names))
    results = [value for _, value, error in outcomes if error is None]
    errors = [{"profile": name, "error": error} for name, _, error in outcomes if error is not None]
    return results, errors


def _scope(profile: Optional[str]) -> list[str]:
    names = [name for name, _ in profiles()]
    if profile:
        _require_profile(profile)
        return [profile]
    return names


def _modal_json(profile: str, *args: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        modal_cmd(*args, "--json"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=CLI_TIMEOUT,
        env={**modal_env(profile), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "modal CLI failed").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "modal CLI failed")
    data = json.loads(result.stdout) if result.stdout.strip() else []
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _pick(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def _run_cli(profile: str, *args: str) -> str:
    result = subprocess.run(
        modal_cmd(*args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=CLI_TIMEOUT,
        env={**modal_env(profile), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "modal CLI failed").strip().splitlines()
        raise ActionError(detail[-1] if detail else "modal CLI failed", 502)
    return result.stdout


# ─── Accounts ─────────────────────────────────────────────────


async def _fetch_account(profile: str) -> dict[str, Any]:
    import modal

    workspace = modal.Workspace.from_context(client=await _aclient(profile))
    await workspace.hydrate.aio()
    try:
        # Same figure as `m-gpux billing` and AUTO selection: metered cost this cycle.
        used: Optional[float] = round(float((await workspace.billing.summary.aio()).metered_cost), 4)
    except Exception:  # billing needs an owner token; the workspace is still reachable
        used = None
    return {"workspace": workspace.name, "used": used}


def accounts(refresh: bool = False) -> dict[str, Any]:
    entries = profiles()
    budgets = load_budgets()
    details = _batch("_account_details", [name for name, _ in entries], _fetch_account, 300, refresh)
    failed = {name: _error_text(value) for name, value in details.items() if isinstance(value, BaseException)}
    rows = []
    for name, active in entries:
        info = {} if name in failed else details.get(name) or {}
        used = info.get("used")
        limit = budget_for(name, budgets)
        cap = MONTHLY_CREDIT if limit is None else limit
        rows.append(
            {
                "name": name,
                "active": active,
                "workspace": info.get("workspace"),
                "used": used,
                "cap": cap,
                "budget": limit,
                "spendable": None if used is None else round(spendable(name, used, MONTHLY_CREDIT, budgets), 4),
                "status": "error" if name in failed else ("ok" if used is not None else "unknown"),
                "error": failed.get(name),
            }
        )
    return {"accounts": rows, "monthly_credit": MONTHLY_CREDIT}


def activate_account(name: str) -> dict[str, Any]:
    doc = load_config()
    if name not in doc:
        raise ActionError(f"unknown account {name!r}", 404)
    for other in doc:
        doc[other].pop("active", None)
    doc[name]["active"] = True
    save_config(doc)
    return {"active": name}


def add_account(name: str, token_id: str, token_secret: str) -> dict[str, Any]:
    import modal

    name, token_id, token_secret = name.strip(), token_id.strip(), token_secret.strip()
    if not PROFILE_NAME.fullmatch(name):
        raise ActionError("account name: letters, digits, spaces, . _ ' - (max 64)")
    if not re.fullmatch(r"ak-[A-Za-z0-9]+", token_id) or not re.fullmatch(r"as-[A-Za-z0-9]+", token_secret):
        raise ActionError("token id must start with ak- and token secret with as-")
    doc = load_config()
    if name in doc:
        raise ActionError(f"account {name!r} already exists", 409)
    # Verify before saving, so a typo never lands in ~/.modal.toml.
    try:
        workspace = modal.Workspace.from_context(client=modal.Client.from_credentials(token_id, token_secret))
        workspace.hydrate()
    except Exception as exc:
        raise ActionError(f"Modal rejected these credentials: {str(exc)[:200]}", 422) from None
    doc[name] = tomlkit.table()
    doc[name]["token_id"] = token_id
    doc[name]["token_secret"] = token_secret
    if len(doc) == 1:
        doc[name]["active"] = True
    save_config(doc)
    invalidate("_account_details")
    return {"name": name, "workspace": workspace.name}


def remove_account(name: str) -> dict[str, Any]:
    doc = load_config()
    if name not in doc:
        raise ActionError(f"unknown account {name!r}", 404)
    was_active = bool(doc[name].get("active", False))
    del doc[name]
    new_active = None
    if was_active and len(doc):
        new_active = next(iter(doc))
        doc[new_active]["active"] = True
    save_config(doc)
    invalidate()
    return {"removed": name, "active": new_active}


def update_budget(profile: Optional[str], limit: Optional[float]) -> dict[str, Any]:
    if profile:
        _require_profile(profile)
    if limit is None:
        clear_budget(profile)
    else:
        if not 0 <= limit <= 100_000:
            raise ActionError("budget must be between 0 and 100000 USD")
        set_budget(profile, limit)
    return {"budgets": load_budgets()}


# ─── Compute ──────────────────────────────────────────────────


@cached(15)
def _apps(profile: str) -> list[dict[str, Any]]:
    rows = []
    for row in _modal_json(profile, "app", "list"):
        state = str(_pick(row, "State", "state")).strip().lower()
        description = str(_pick(row, "Description", "description"))
        rows.append(
            {
                "profile": profile,
                "id": _pick(row, "App ID", "app_id"),
                "name": description,
                "state": state,
                "alive": state in ALIVE_APP_STATES,
                "managed": description.startswith("m-gpux"),
                "tasks": int(_pick(row, "Tasks", "n_running_tasks", default=0) or 0),
                "created_at": _pick(row, "Created at", "created_at", default=None),
                "stopped_at": _pick(row, "Stopped at", "stopped_at", default=None),
            }
        )
    return rows


@cached(15)
def _containers(profile: str) -> list[dict[str, Any]]:
    return [
        {
            "profile": profile,
            "id": _pick(row, "Container ID", "container_id"),
            "app_id": _pick(row, "App ID", "app_id"),
            "app_name": _pick(row, "App Name", "app_name"),
            "started_at": _pick(row, "Start Time", "start_time", default=None),
        }
        for row in _modal_json(profile, "container", "list")
    ]


async def _fetch_sandboxes(profile: str) -> list[dict[str, Any]]:
    import modal

    from m_gpux.plugins.dev.devbox import load_boxes

    boxes = {box.get("sandbox_id"): name for name, box in load_boxes().items() if box.get("profile") == profile}
    return [
        {"profile": profile, "id": sandbox.object_id, "dev_box": boxes.get(sandbox.object_id)}
        async for sandbox in modal.Sandbox.list.aio(client=await _aclient(profile))
    ]


def _collect(fn: Callable, profile: Optional[str], refresh: bool, key: str) -> dict[str, Any]:
    _sdk_ready.wait(SDK_WARMUP_WAIT)
    found, errors = _fan_out(fn, _scope(profile), refresh)
    return {key: [row for rows in found for row in rows], "errors": errors}


def apps(profile: Optional[str] = None, refresh: bool = False) -> dict[str, Any]:
    return _collect(_apps, profile, refresh, "apps")


def containers(profile: Optional[str] = None, refresh: bool = False) -> dict[str, Any]:
    return _collect(_containers, profile, refresh, "containers")


def sandboxes(profile: Optional[str] = None, refresh: bool = False) -> dict[str, Any]:
    from m_gpux.plugins.dev.devbox import load_boxes

    found = _batch("_sandboxes", _scope(profile), _fetch_sandboxes, 15, refresh)
    result: dict[str, Any] = {
        "sandboxes": [row for rows in found.values() if not isinstance(rows, BaseException) for row in rows],
        "errors": [
            {"profile": name, "error": _error_text(rows)}
            for name, rows in found.items()
            if isinstance(rows, BaseException)
        ],
    }
    result["dev_boxes"] = [
        {
            "name": name,
            "profile": box.get("profile"),
            "state": box.get("state", "unknown"),
            "compute": box.get("compute_label") or box.get("gpu") or "CPU",
            "sandbox_id": box.get("sandbox_id"),
            "has_snapshot": bool(box.get("snapshot_id")),
            "local_dir": box.get("local_dir"),
            "started_at": box.get("started_at"),
            "created_at": box.get("created_at"),
        }
        for name, box in sorted(load_boxes().items())
        if not profile or box.get("profile") == profile
    ]
    return result


def stop_modal_app(profile: str, app_id: str) -> dict[str, Any]:
    _require_profile(profile)
    _require_id(app_id, "app")
    result = stop_app(app_id, profile=profile)
    if result.returncode != 0:
        raise ActionError((result.stderr or "modal app stop failed").strip()[:300], 502)
    invalidate("_apps", "_containers")
    return {"stopped": app_id}


def stop_container(profile: str, container_id: str) -> dict[str, Any]:
    _require_profile(profile)
    _run_cli(profile, "container", "stop", _require_id(container_id, "container"))
    invalidate("_apps", "_containers")
    return {"stopped": container_id}


def terminate_sandbox(profile: str, sandbox_id: str) -> dict[str, Any]:
    import modal

    _require_profile(profile)
    modal.Sandbox.from_id(_require_id(sandbox_id, "sandbox"), client=_client(profile)).terminate()
    invalidate("_sandboxes", "_containers")
    return {"terminated": sandbox_id}


def app_logs(profile: str, app_id: str, tail: int = 200) -> dict[str, Any]:
    _require_profile(profile)
    _require_id(app_id, "app")
    tail = max(1, min(tail, 1000))
    # Since modal 1.4, `app logs` without --follow prints recent entries and exits.
    output = _run_cli(profile, "app", "logs", app_id, "--tail", str(tail), "--timestamps")
    return {"id": app_id, "lines": output.splitlines()[-tail:]}


def container_logs(profile: str, container_id: str, tail: int = 200) -> dict[str, Any]:
    _require_profile(profile)
    tail = max(1, min(tail, 1000))
    output = _run_cli(
        profile, "container", "logs", _require_id(container_id, "container"), "--tail", str(tail), "--timestamps"
    )
    return {"id": container_id, "lines": output.splitlines()[-tail:]}


# ─── Local workloads ──────────────────────────────────────────


def sessions(profile: Optional[str] = None) -> dict[str, Any]:
    from m_gpux.core.state import list_sessions

    rows = [s for s in list_sessions() if not profile or s.get("profile") == profile]
    rows.sort(key=lambda s: str(s.get("created_at") or ""), reverse=True)
    keep = ("id", "kind", "app_name", "description", "profile", "compute", "python_version", "preset")
    known = {name for name, _ in profiles()}
    with _cache_lock:  # only apps already fetched: this page never waits on the modal CLI
        live = {
            key[1][0]: {app["name"] for app in value[1] if app["alive"]}
            for key, value in _cache.items()
            if key[0] == "_apps" and isinstance(value[1], list)
        }

    def effective(s: dict[str, Any]) -> str:
        # sessions.json only learns about stops made through m-gpux; correct what we can.
        recorded = str(s.get("state") or "unknown")
        if recorded != "running":
            return recorded
        if s.get("profile") and s["profile"] not in known:
            return "orphaned"
        if s.get("profile") in live and s.get("app_name") not in live[s["profile"]]:
            return "ended"
        return recorded

    return {
        "sessions": [
            {
                **{k: s.get(k) for k in keep},
                "state": effective(s),
                "recorded_state": s.get("state"),
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
            }
            for s in rows
        ]
    }


def forget_session(session_id: str) -> dict[str, Any]:
    from m_gpux.core.state import forget_session as forget

    if not forget(session_id):
        raise ActionError("session not found", 404)
    return {"forgotten": session_id}


def endpoints() -> dict[str, Any]:
    from m_gpux.core.state import get_gateway_endpoint, get_serve_endpoint, list_gateway_jobs

    serve = get_serve_endpoint()
    gateway = get_gateway_endpoint()
    jobs = list_gateway_jobs()
    counts: dict[str, int] = {}
    for job in jobs:
        status = str(job.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return {
        "serve": {k: v for k, v in serve.items() if "key" not in k.lower()} if serve else None,
        "gateway": (
            {
                "url": gateway.get("url"),
                "app_name": gateway.get("app_name"),
                "profile": gateway.get("profile"),
                "tasks": gateway.get("tasks", []),
                "updated_at": gateway.get("updated_at"),
                "job_counts": counts,
                "recent_jobs": [
                    {k: job.get(k) for k in ("id", "task", "status", "submitted_at", "finished_at")}
                    for job in jobs[:20]
                ],
            }
            if gateway
            else None
        ),
    }


def library() -> dict[str, Any]:
    from m_gpux.core.images import list_images
    from m_gpux.core.state import list_presets

    keep = ("action", "compute_label", "profile", "python_version", "created_at", "updated_at")
    return {
        "presets": [{"name": name, **{k: p.get(k) for k in keep}} for name, p in sorted(list_presets().items())],
        "images": [{"name": name, **meta} for name, meta in sorted(list_images().items())],
    }


def billing() -> dict[str, Any]:
    from m_gpux.core.pricing import load_rates, rates_age_seconds

    rates = load_rates()
    gpus = sorted(
        (
            {"gpu": key.removeprefix("gpu_hour_cost_").upper(), "hourly": value}
            for key, value in rates.items()
            if key.startswith("gpu_hour_cost_")
        ),
        key=lambda row: row["hourly"],
    )
    return {
        "budgets": load_budgets(),
        "gpu_rates": gpus,
        "cpu_hour": rates.get("cpu_hour_cost"),
        "mem_gib_hour": rates.get("mem_gib_hour_cost"),
        "rates_age_seconds": rates_age_seconds(),
    }


def info() -> dict[str, Any]:
    return {"version": __version__, "accounts": len(profiles())}


# ─── Other clouds: Kaggle & Colab ─────────────────────────────


@cached(120)
def _kaggle() -> dict[str, Any]:
    from m_gpux.core import kaggle as kz

    if not kz.executable():
        return {"installed": False, "accounts": []}
    rows = kz.overview()
    return {
        "installed": True,
        "accounts": rows,  # account.public(): no tokens
        "gpu_slots": kz.GPU_SLOTS,
        "auto": kz.pick_account(rows),
        "zoo_path": str(kz.ZOO_PATH),
    }


def kaggle(refresh: bool = False) -> dict[str, Any]:
    return _kaggle(refresh=refresh)


@cached(60)
def _colab() -> dict[str, Any]:
    from m_gpux.core import colab as cb

    if not cb.executable():
        return {"installed": False, "accounts": []}
    rows = cb.overview()
    return {"installed": True, "accounts": rows, "auto": cb.pick_account(rows), "gpus": list(cb.GPUS)}


def colab(refresh: bool = False) -> dict[str, Any]:
    return _colab(refresh=refresh)


def stop_colab_session(account: str, session: str) -> dict[str, Any]:
    from m_gpux.core import colab as cb

    if account not in cb.account_names():
        raise ActionError(f"unknown Colab account {account!r}", 404)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", session):
        raise ActionError("invalid session name")
    try:
        result = cb.run(account, ["stop", "-s", session], timeout=120)
    except cb.ColabError as exc:
        raise ActionError(str(exc), 409) from None
    text = cb.clean((result.stdout or "") + (result.stderr or ""))
    if result.returncode != 0 or "not found" in text.lower():
        raise ActionError(text.splitlines()[-1] if text else "colab stop failed", 502)
    invalidate("_colab")
    return {"stopped": session}


def prefetch() -> None:
    """Warm the caches while the browser opens: SDK data first, then the CLI-backed lists.

    CLI-backed requests wait for the SDK warm-up (see ``_collect``): the first
    client handshakes take ~9 s alone but ~35 s when competing with a burst of
    ``modal`` processes for the CPU.
    """
    _sdk_ready.clear()
    try:
        sdk = [threading.Thread(target=fn, daemon=True) for fn in (accounts, sandboxes)]
        for thread in sdk:
            thread.start()
        for thread in sdk:
            thread.join()
    finally:
        _sdk_ready.set()
    for fn in (apps, containers):
        try:
            fn()
        except Exception:
            pass  # the page will show the error when it asks
