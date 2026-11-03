"""Kaggle CLI across several accounts (the "zoo").

Accounts live in ``~/.kaggle/zoo.json``, the same file the standalone
``kzoo.py`` script uses, so both keep working side by side::

    {"accounts": {"<username>": {"token": "KGAT_...", "team": "...", "note": "...",
                                 "default": true, "no_submit": ["<competition>"]}}}

The account marked ``"default": true`` (or one without a token) runs with the
machine's normal Kaggle credentials. Every other account runs the ``kaggle`` CLI
with its own ``KAGGLE_API_TOKEN``. ``no_submit`` lists competitions an account
must never submit to (for example, because it is on another team).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

ZOO_PATH = Path.home() / ".kaggle" / "zoo.json"
# Kaggle runs at most two GPU sessions at once per account.
GPU_SLOTS = 2
LIVE_STATES = ("RUNNING", "QUEUED")
DONE_STATES = ("COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED", "CANCELLED")
TIMEOUT = 120


class KaggleError(RuntimeError):
    pass


@dataclass
class KaggleAccount:
    name: str
    token: Optional[str] = None
    team: str = ""
    note: str = ""
    default: bool = False
    no_submit: list[str] = field(default_factory=list)

    @property
    def uses_machine_credentials(self) -> bool:
        return self.default or not self.token

    def public(self) -> dict[str, Any]:
        """Everything but the token."""
        return {
            "name": self.name,
            "team": self.team,
            "note": self.note,
            "default": self.default,
            "no_submit": list(self.no_submit),
            "credentials": "machine" if self.uses_machine_credentials else f"token …{(self.token or '')[-4:]}",
        }


# ─── Zoo file ─────────────────────────────────────────────────


def load_zoo() -> dict[str, Any]:
    try:
        data = json.loads(ZOO_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"accounts": {}}
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
        return {"accounts": {}}
    return data


def save_zoo(zoo: dict[str, Any]) -> None:
    """Atomic write that keeps the account order and non-ASCII notes as the user wrote them."""
    ZOO_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".zoo.", suffix=".tmp", dir=ZOO_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(zoo, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, ZOO_PATH)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def accounts() -> list[KaggleAccount]:
    """Configured accounts; just the machine's own credentials when there is no zoo file."""
    found = []
    for name, raw in load_zoo()["accounts"].items():
        if not isinstance(raw, dict):
            continue
        found.append(
            KaggleAccount(
                name=str(name),
                token=raw.get("token") or None,
                team=str(raw.get("team") or ""),
                note=str(raw.get("note") or ""),
                default=bool(raw.get("default", False)),
                no_submit=[str(c) for c in raw.get("no_submit") or []],
            )
        )
    if not found and has_machine_credentials():
        found.append(KaggleAccount(name="default", default=True))
    return found


def get_account(name: str) -> KaggleAccount:
    for account in accounts():
        if account.name.casefold() == name.casefold():
            return account
    raise KaggleError(f"unknown Kaggle account {name!r}; see `m-gpux kaggle accounts`")


def has_machine_credentials() -> bool:
    home = Path.home()
    return bool(
        os.environ.get("KAGGLE_API_TOKEN")
        or os.environ.get("KAGGLE_KEY")
        or (home / ".kaggle" / "access_token").is_file()
        or (home / ".kaggle" / "kaggle.json").is_file()
        or (home / ".config" / "kaggle" / "kaggle.json").is_file()
    )


def add_account(token: str, *, user: Optional[str] = None, team: str = "", note: str = "") -> str:
    """Register a token; the username is detected from the account's own kernels or datasets."""
    probe = KaggleAccount(name=user or "?", token=token.strip())
    username = user or whoami(probe)
    if not username:
        raise KaggleError("could not detect the username for this token (no kernels or datasets yet?); pass --user")
    zoo = load_zoo()
    entry = {**zoo["accounts"].get(username, {}), "token": token.strip()}
    entry.update({k: v for k, v in (("team", team), ("note", note)) if v})
    zoo["accounts"][username] = entry
    save_zoo(zoo)
    return username


def remove_account(name: str) -> bool:
    zoo = load_zoo()
    key = next((k for k in zoo["accounts"] if k.casefold() == name.casefold()), None)
    if key is None:
        return False
    del zoo["accounts"][key]
    save_zoo(zoo)
    return True


# ─── Running the CLI ──────────────────────────────────────────


def executable() -> Optional[str]:
    return shutil.which("kaggle")


def env_for(account: KaggleAccount) -> dict[str, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env.pop("KAGGLE_API_TOKEN", None)
    if not account.uses_machine_credentials:
        env["KAGGLE_API_TOKEN"] = str(account.token)
    return env


def check_submit_allowed(account: KaggleAccount, args: list[str]) -> None:
    """Refuse `competitions submit` to a competition listed in the account's ``no_submit``."""
    if args[:2] in (["competitions", "submit"], ["c", "submit"]):
        competition = next((a for a in args[2:] if not a.startswith("-")), None)
        if competition and competition in account.no_submit:
            raise KaggleError(f"{account.name} must not submit to {competition} (no_submit in {ZOO_PATH})")


def run(
    account: KaggleAccount, args: list[str], *, capture: bool = True, timeout: Optional[float] = TIMEOUT
) -> subprocess.CompletedProcess:
    exe = executable()
    if not exe:
        raise KaggleError("the kaggle CLI is not installed; run `pip install kaggle`")
    check_submit_allowed(account, args)
    return subprocess.run(
        [exe, "-W", *args],  # -W: no "outdated version" banner in parsed output
        env=env_for(account),
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def run_json(account: KaggleAccount, args: list[str], *, timeout: Optional[float] = TIMEOUT) -> Any:
    result = run(account, [*args, "--format", "json"], timeout=timeout)
    output = (result.stdout or "").strip()
    start = min((i for i in (output.find("["), output.find("{")) if i >= 0), default=-1)
    if result.returncode != 0 or start < 0:
        detail = (result.stderr or result.stdout or "kaggle CLI failed").strip().splitlines()
        raise KaggleError(detail[-1] if detail else "kaggle CLI failed")
    try:
        return json.loads(output[start:])
    except json.JSONDecodeError as exc:
        raise KaggleError(f"unexpected kaggle output: {output[:200]}") from exc


# ─── Queries ──────────────────────────────────────────────────


def whoami(account: KaggleAccount) -> Optional[str]:
    for args in (["kernels", "list", "--mine", "--page-size", "5"], ["datasets", "list", "--mine"]):
        try:
            for row in run_json(account, args):
                ref = str(row.get("ref", ""))
                if "/" in ref:
                    return ref.split("/")[0]
        except KaggleError:
            continue
    return None


def _hours(value: Any) -> float:
    try:
        return float(str(value).rstrip("h"))
    except ValueError:
        return 0.0


def _utc(value: Any) -> Optional[str]:
    """Kaggle prints UTC times without an offset; make that explicit."""
    if not value:
        return None
    text = str(value)
    return text if text.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", text) else text + "Z"


def quota(account: KaggleAccount) -> dict[str, dict[str, Any]]:
    """Weekly accelerator hours: ``{"gpu": {"used", "remaining", "total", "refresh_at"}, "tpu": {...}}``."""
    return {
        str(row.get("resource", "")).lower(): {
            "used": _hours(row.get("used")),
            "remaining": _hours(row.get("remaining")),
            "total": _hours(row.get("total")),
            "refresh_at": _utc(row.get("refreshAt")),
        }
        for row in run_json(account, ["quota"])
    }


def kernel_status(account: KaggleAccount, ref: str) -> str:
    result = run(account, ["kernels", "status", ref])
    text = (result.stdout or "") + (result.stderr or "")
    match = re.search(r"KernelWorkerStatus\.(\w+)", text)
    if match:
        return match.group(1)
    return "NOT_FOUND" if ("404" in text or "denied" in text.lower()) else "UNKNOWN"


def live_kernels(account: KaggleAccount, hours: int = 14) -> list[dict[str, str]]:
    """Kernels run in the last *hours* that are still RUNNING or QUEUED."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = []
    for row in run_json(account, ["kernels", "list", "--mine", "--sort-by", "dateRun", "--page-size", "20"]):
        try:
            started = datetime.fromisoformat(str(row["lastRunTime"])[:19]).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        if started >= since:
            recent.append(str(row["ref"]))
    live = []
    for ref in recent:
        state = kernel_status(account, ref)
        if state in LIVE_STATES:
            live.append({"ref": ref, "state": state})
    return live


def submissions_today(account: KaggleAccount, competition: str) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date().isoformat()
    rows = run_json(account, ["competitions", "submissions", competition])
    return [
        {
            "ref": row.get("ref"),
            "date": row.get("date"),
            "status": str(row.get("status") or "").replace("SubmissionStatus.", ""),
            "public_score": row.get("publicScore"),
            "private_score": row.get("privateScore"),
            "description": row.get("description") or "",
        }
        for row in rows
        if str(row.get("date", "")).startswith(today)
    ]


def overview(hours: int = 14, *, with_kernels: bool = True) -> list[dict[str, Any]]:
    """Per account, in parallel: GPU/TPU quota and (optionally) live kernels. Errors are reported per account."""

    def one(account: KaggleAccount) -> dict[str, Any]:
        row: dict[str, Any] = {**account.public(), "error": None}
        try:
            row["quota"] = quota(account)
            if with_kernels:
                row["live"] = live_kernels(account, hours)
        except (KaggleError, subprocess.TimeoutExpired, OSError) as exc:
            row["error"] = str(exc)[:300] or type(exc).__name__
        return row

    found = accounts()
    if not found:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(found))) as pool:
        return list(pool.map(one, found))


def pick_account(rows: Optional[list[dict[str, Any]]] = None) -> Optional[str]:
    """AUTO: the account with a free GPU slot and the most GPU hours left this week."""
    rows = overview() if rows is None else rows
    usable = [
        r for r in rows if not r.get("error") and len(r.get("live") or []) < GPU_SLOTS and r.get("quota", {}).get("gpu")
    ]
    usable.sort(key=lambda r: r["quota"]["gpu"]["remaining"], reverse=True)
    return usable[0]["name"] if usable and usable[0]["quota"]["gpu"]["remaining"] > 0 else None


# ─── Kernels ──────────────────────────────────────────────────


def read_kernel_metadata(folder: Path) -> dict[str, Any]:
    path = folder / "kernel-metadata.json"
    if not path.is_file():
        raise KaggleError(f"{folder} has no kernel-metadata.json (create one with `kaggle kernels init -p {folder}`)")
    try:
        meta = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise KaggleError(f"invalid kernel-metadata.json: {exc}") from exc
    if "/" not in str(meta.get("id", "")):
        raise KaggleError('kernel-metadata.json needs an "id" like "<user>/<slug>"')
    return meta


def push_kernel(account: KaggleAccount, folder: Path) -> dict[str, Any]:
    """Push the kernel in *folder* as *account*.

    When the metadata's owner differs from the account, the folder is pushed
    from a temporary copy whose ``id`` names this account, so the original
    files are never modified.
    """
    meta = read_kernel_metadata(folder)
    owner, slug = str(meta["id"]).split("/", 1)
    target = owner if account.uses_machine_credentials and account.name == "default" else account.name
    source = folder
    with tempfile.TemporaryDirectory(prefix="mgpux-kernel-") as tmp:
        if target != owner:
            source = Path(tmp) / folder.name
            shutil.copytree(folder, source)
            meta["id"] = f"{target}/{slug}"
            (source / "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        result = run(account, ["kernels", "push", "-p", str(source)], timeout=600)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    # The CLI can exit 0 while printing an error (e.g. a slug clash), so read the text too.
    if result.returncode != 0 or ("error" in output.lower() and "successfully" not in output.lower()):
        raise KaggleError(output.splitlines()[-1] if output else "kaggle kernels push failed")
    version = re.search(r"version (\d+)", output)
    return {"ref": f"{target}/{slug}", "version": int(version.group(1)) if version else None, "output": output}


def download_output(account: KaggleAccount, ref: str, dest: Path) -> subprocess.CompletedProcess:
    dest.mkdir(parents=True, exist_ok=True)
    return run(account, ["kernels", "output", ref, "-p", str(dest)], capture=False, timeout=None)
