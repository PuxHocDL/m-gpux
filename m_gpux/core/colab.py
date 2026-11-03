"""Google Colab CLI (google-colab-cli) across several Google accounts.

colab-cli keeps its OAuth token in ``~/.config/colab-cli/token.json``, so each
extra account gets its own home folder, ``~/.colab_accounts/<name>``, and runs
with ``USERPROFILE`` (Windows) or ``HOME`` pointed at it. ``main`` is the
normal home. This matches the standalone ``colab_as.py`` script, so accounts
logged in with either tool work in both.

On Windows the CLI imports ``termios``/``tty`` at start-up although only
``colab console`` uses them; the stubs in ``colab_shim/`` go on ``PYTHONPATH``
so every other command runs natively.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

ACCOUNTS_DIR = Path.home() / ".colab_accounts"
MAIN = "main"
SHIM_DIR = Path(__file__).with_name("colab_shim")
GPUS = ("T4", "L4", "G4", "A100", "H100")
TPUS = ("v5e1", "v6e1")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
TIMEOUT = 120
_NOISE = ("A new version of Colab CLI", "Run 'colab update'", "Run 'pip install", "To silence this check")
_SESSION_RE = re.compile(
    r"^\[(?P<name>[^\]]*)\]\s+(?P<endpoint>\S+)\s+\|\s+Hardware:\s+(?P<hardware>[^|]+?)\s+\|"
    r"\s+Shape:\s+(?P<shape>[^|]+?)\s+\|\s+Variant:\s+(?P<variant>[^|]+?)(?:\s+\|\s+Status:\s+(?P<status>.+))?$"
)


class ColabError(RuntimeError):
    pass


def executable() -> Optional[str]:
    found = shutil.which("colab")
    if found:
        return found
    for name in ("colab.exe", "colab"):
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.is_file():
            return str(candidate)
    return None


def home_of(name: str) -> Path:
    return Path.home() if name == MAIN else ACCOUNTS_DIR / name


def token_path(name: str) -> Path:
    return home_of(name) / ".config" / "colab-cli" / "token.json"


def is_logged_in(name: str) -> bool:
    return token_path(name).is_file()


def account_names() -> list[str]:
    extra = sorted(p.name for p in ACCOUNTS_DIR.glob("*") if p.is_dir()) if ACCOUNTS_DIR.is_dir() else []
    return [MAIN, *extra]


def accounts() -> list[dict[str, Any]]:
    return [{"name": n, "home": str(home_of(n)), "logged_in": is_logged_in(n)} for n in account_names()]


def validate_name(name: str) -> str:
    if not NAME_RE.fullmatch(name):
        raise ColabError("account names use letters, digits, '.', '_' or '-' (max 40)")
    return name


def env_for(name: str) -> dict[str, str]:
    home = home_of(name)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    if os.name == "nt":
        env["USERPROFILE"] = str(home)
        env.pop("HOME", None)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SHIM_DIR), os.environ.get("PYTHONPATH", "")]))
    else:
        env["HOME"] = str(home)
    return env


def run(
    name: str, args: list[str], *, interactive: bool = False, timeout: Optional[float] = TIMEOUT
) -> subprocess.CompletedProcess:
    """Run ``colab <args>`` as account *name*.

    Non-interactive calls never prompt: an account without a token would make
    the CLI wait for an OAuth code on stdin, so they are refused instead.
    """
    exe = executable()
    if not exe:
        raise ColabError("the Colab CLI is not installed; run `uv tool install google-colab-cli` (Python 3.12+)")
    if name not in account_names() and name != MAIN:
        raise ColabError(f"unknown Colab account {name!r}; add it with `m-gpux colab login {name}`")
    if interactive:
        return subprocess.run([exe, *args], env=env_for(name), timeout=timeout)
    if not is_logged_in(name):
        raise ColabError(f"Colab account {name!r} is not logged in; run `m-gpux colab login {name}`")
    return subprocess.run(
        [exe, *args],
        env=env_for(name),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        # A console-less parent (the dashboard) would otherwise flash a window per call.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def clean(text: str) -> str:
    """Drop the CLI's update-check banner."""
    lines = [line for line in text.splitlines() if not any(noise in line for noise in _NOISE)]
    return "\n".join(lines).strip()


def _checked(name: str, result: subprocess.CompletedProcess) -> str:
    text = clean((result.stdout or "") + "\n" + (result.stderr or ""))
    # An expired or revoked token makes the CLI ask for a new OAuth code, which
    # fails on our closed stdin.
    if "authorize colab-cli" in text or "EOF when reading a line" in text:
        raise ColabError(f"the login of {name!r} expired; run `m-gpux colab login {name}`")
    if result.returncode != 0:
        raise ColabError(text.splitlines()[-1] if text else f"colab exited {result.returncode}")
    return text


def usage(name: str) -> dict[str, Any]:
    """Compute-unit balance, current burn rate per hour and active runtimes."""
    text = _checked(name, run(name, ["usage"]))
    balance = re.search(r"Current balance:\s*([\d.]+)", text)
    if not balance:
        raise ColabError(text.splitlines()[-1] if text else "no usage information")
    rate = re.search(r"Usage rate:\s*([\d.]+)", text)
    active = re.search(r"Active assignments:\s*(\d+)", text)
    return {
        "balance": float(balance.group(1)),
        "rate": float(rate.group(1)) if rate else 0.0,
        "active": int(active.group(1)) if active else 0,
    }


def sessions(name: str) -> list[dict[str, Any]]:
    text = _checked(name, run(name, ["sessions"]))
    found = []
    for line in text.splitlines():
        match = _SESSION_RE.match(line.strip())
        if match:
            row = {k: (v.strip() if v else None) for k, v in match.groupdict().items()}
            row["name"] = None if row["name"] == "?" else row["name"]
            found.append(row)
    return found


def overview() -> list[dict[str, Any]]:
    """Per account, in parallel: login state, balance and live runtimes."""

    def one(account: dict[str, Any]) -> dict[str, Any]:
        row = {**account, "usage": None, "sessions": [], "error": None}
        if not account["logged_in"]:
            return row
        try:
            row["usage"] = usage(account["name"])
            row["sessions"] = sessions(account["name"])
        except (ColabError, subprocess.TimeoutExpired, OSError) as exc:
            row["error"] = str(exc)[:300] or type(exc).__name__
        return row

    found = accounts()
    with ThreadPoolExecutor(max_workers=min(8, len(found))) as pool:
        return list(pool.map(one, found))


def pick_account(rows: Optional[list[dict[str, Any]]] = None) -> Optional[str]:
    """AUTO: the logged-in account with the most compute units left."""
    rows = overview() if rows is None else rows
    usable = [r for r in rows if r.get("usage") and not r.get("error")]
    usable.sort(key=lambda r: r["usage"]["balance"], reverse=True)
    return usable[0]["name"] if usable else None


def create_account_home(name: str) -> Path:
    validate_name(name)
    if name == MAIN:
        return Path.home()
    home = home_of(name)
    home.mkdir(parents=True, exist_ok=True)
    return home
