"""Run one Modal SDK operation against several workspaces.

Each profile in ``~/.modal.toml`` is its own workspace, and Secrets, Images and
Volumes are scoped to a workspace. The ``secrets``, ``image sync`` and
``volume`` commands all follow the same shape: resolve a ``--to`` target to a
list of profiles, then do the same thing in each of them in parallel and report
per-profile success or failure.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, TypeVar

from m_gpux.core.profiles import load_config

T = TypeVar("T")


class WorkspaceError(RuntimeError):
    """A target or profile that cannot be used."""


def resolve_targets(spec: Optional[str], *, default_active: bool = True) -> list[str]:
    """Turn ``--to`` into profile names.

    ``all`` (or ``*``) means every profile, ``a,b`` a list, and an empty value
    the active profile (or every profile when *default_active* is false).
    """
    doc = load_config()
    names = list(doc.keys())
    if not names:
        raise WorkspaceError("No Modal profiles configured. Run `m-gpux account add` first.")
    raw = (spec or "").strip()
    if not raw:
        if not default_active:
            return names
        active = [n for n in names if doc[n].get("active")]
        return active[:1] or names[:1]
    if raw.lower() in ("all", "*"):
        return names
    wanted = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [w for w in wanted if w not in names]
    if unknown:
        raise WorkspaceError(f"Unknown profile(s): {', '.join(unknown)}. Known: {', '.join(names)}")
    return list(dict.fromkeys(wanted))


def client_for(profile: str):
    """A Modal client authenticated as *profile* (tokens never leave this process)."""
    doc = load_config()
    if profile not in doc:
        raise WorkspaceError(f"Unknown profile '{profile}'.")
    token_id = doc[profile].get("token_id")
    token_secret = doc[profile].get("token_secret")
    if not token_id or not token_secret:
        raise WorkspaceError(f"Profile '{profile}' has no token.")
    from modal.client import Client

    return Client.from_credentials(str(token_id), str(token_secret))


def for_each(
    profiles: list[str],
    action: Callable[[str, Any], T],
    *,
    workers: int = 8,
) -> dict[str, T | Exception]:
    """Call ``action(profile, client)`` for every profile in parallel.

    Returns ``{profile: result_or_exception}`` in the order given. The sync
    Modal SDK runs every call on its own shared event loop, so plain threads
    are safe here (unlike per-thread ``asyncio.run`` loops).
    """

    def one(profile: str) -> T | Exception:
        try:
            return action(profile, client_for(profile))
        except Exception as exc:  # reported per profile, never aborts the batch
            return exc

    if not profiles:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(profiles)))) as pool:
        results = list(pool.map(one, profiles))
    return dict(zip(profiles, results, strict=True))


def short_error(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text.splitlines()[0][:160]
