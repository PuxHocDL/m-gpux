"""Local state stores for sessions and workload presets."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path.home() / ".m-gpux"
SESSIONS_PATH = STATE_DIR / "sessions.json"
PRESETS_PATH = STATE_DIR / "presets.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def new_session_id() -> str:
    return "sess-" + uuid.uuid4().hex[:8]


def list_sessions() -> list[dict[str, Any]]:
    sessions = _read_json(SESSIONS_PATH, [])
    if not isinstance(sessions, list):
        return []
    return [s for s in sessions if isinstance(s, dict)]


def save_session(session: dict[str, Any]) -> dict[str, Any]:
    sessions = list_sessions()
    if not session.get("id"):
        session["id"] = new_session_id()
    session.setdefault("created_at", utc_now())
    session["updated_at"] = utc_now()

    replaced = False
    for idx, existing in enumerate(sessions):
        if existing.get("id") == session["id"]:
            sessions[idx] = session
            replaced = True
            break
    if not replaced:
        sessions.append(session)
    _write_json(SESSIONS_PATH, sessions)
    return session


def get_session(session_id: str) -> dict[str, Any] | None:
    for session in list_sessions():
        if session.get("id") == session_id or session.get("app_name") == session_id:
            return session
    return None


def update_session(session_id: str, **updates: Any) -> dict[str, Any] | None:
    session = get_session(session_id)
    if not session:
        return None
    session.update(updates)
    return save_session(session)


def forget_session(session_id: str) -> bool:
    sessions = list_sessions()
    kept = [s for s in sessions if s.get("id") != session_id and s.get("app_name") != session_id]
    if len(kept) == len(sessions):
        return False
    _write_json(SESSIONS_PATH, kept)
    return True


def list_presets() -> dict[str, dict[str, Any]]:
    presets = _read_json(PRESETS_PATH, {})
    if not isinstance(presets, dict):
        return {}
    return {str(k): v for k, v in presets.items() if isinstance(v, dict)}


def get_preset(name: str) -> dict[str, Any] | None:
    return list_presets().get(name)


def save_preset(name: str, preset: dict[str, Any]) -> dict[str, Any]:
    presets = list_presets()
    existing = presets.get(name, {})
    data = {**existing, **preset}
    data["name"] = name
    data.setdefault("created_at", utc_now())
    data["updated_at"] = utc_now()
    presets[name] = data
    _write_json(PRESETS_PATH, presets)
    return data


def delete_preset(name: str) -> bool:
    presets = list_presets()
    if name not in presets:
        return False
    del presets[name]
    _write_json(PRESETS_PATH, presets)
    return True
