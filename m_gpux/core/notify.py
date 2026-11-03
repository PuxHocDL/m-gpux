"""Push notifications for m-gpux events.

Channels live in ``~/.m-gpux/notify.json``. Every channel is a webhook-style
endpoint (Discord, Slack, Telegram, ntfy or a generic JSON webhook) and may
subscribe to a subset of :data:`EVENTS`. Webhook URLs and bot tokens are
credentials: the file is written owner-only where the OS supports it, and
:func:`masked` is the only form ever printed.

:func:`send` never raises; a failing channel is reported in its return value,
so a notification can never break the command that triggered it.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from m_gpux.core.state import STATE_DIR, _read_json, _write_json, utc_now

NOTIFY_PATH = STATE_DIR / "notify.json"
TIMEOUT = 10

EVENTS: dict[str, str] = {
    "run.done": "An `m-gpux up` / `run` job finished",
    "run.failed": "An `m-gpux up` / `run` job failed",
    "sweep.done": "A sweep finished (with its best result)",
    "job.done": "A gateway job finished",
    "job.failed": "A gateway job failed or expired",
    "app.stopped": "A running m-gpux app stopped (watch)",
    "app.long_running": "An app has been running longer than the limit (watch)",
    "credit.low": "An account is low on credit or budget (watch)",
    "budget.over": "An account went over its budget",
    "test": "`m-gpux notify test`",
}

TYPES: dict[str, str] = {
    "discord": "Discord channel webhook URL",
    "slack": "Slack incoming-webhook URL",
    "telegram": "Telegram bot token + chat id",
    "ntfy": "ntfy topic URL (https://ntfy.sh/<topic> or self-hosted)",
    "webhook": "Any HTTPS endpoint; receives a JSON body",
}

LEVEL_ICON = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")


class NotifyError(ValueError):
    """Invalid channel configuration."""


# ─── Config ─────────────────────────────────────────────────────


def load_channels() -> list[dict[str, Any]]:
    data = _read_json(NOTIFY_PATH, {})
    channels = data.get("channels", []) if isinstance(data, dict) else []
    return [c for c in channels if isinstance(c, dict) and c.get("name") and c.get("type") in TYPES]


def save_channels(channels: list[dict[str, Any]]) -> None:
    _write_json(NOTIFY_PATH, {"channels": channels})
    try:
        os.chmod(NOTIFY_PATH, 0o600)
    except OSError:
        pass


def _https(url: str, label: str) -> str:
    url = (url or "").strip()
    parsed = urllib.parse.urlparse(url)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise NotifyError(f"{label} must be an https:// URL.")
    if not parsed.netloc:
        raise NotifyError(f"{label} is not a URL.")
    return url


def validate_channel(channel: dict[str, Any]) -> dict[str, Any]:
    """Return a cleaned channel or raise :class:`NotifyError`."""
    name = str(channel.get("name", "")).strip()
    kind = str(channel.get("type", "")).strip().lower()
    if not NAME_RE.match(name):
        raise NotifyError("Channel names use letters, digits, '.', '_' and '-' (max 40).")
    if kind not in TYPES:
        raise NotifyError(f"Unknown channel type '{kind}'. Use one of: {', '.join(TYPES)}.")
    events = [str(e) for e in channel.get("events") or ["*"]]
    bad = [e for e in events if e != "*" and e not in EVENTS]
    if bad:
        raise NotifyError(f"Unknown event(s): {', '.join(bad)}. Known: {', '.join(EVENTS)}.")
    clean: dict[str, Any] = {"name": name, "type": kind, "events": events}
    if kind == "telegram":
        token = str(channel.get("bot_token", "")).strip()
        chat = str(channel.get("chat_id", "")).strip()
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", token):
            raise NotifyError("Telegram bot token looks like 123456:ABC… (from @BotFather).")
        if not re.fullmatch(r"-?\d+|@[A-Za-z0-9_]{4,}", chat):
            raise NotifyError("Telegram chat id is a number (or @channelname).")
        clean.update(bot_token=token, chat_id=chat)
        return clean
    url = _https(str(channel.get("url", "")), "The URL")
    host = urllib.parse.urlparse(url).hostname or ""
    if kind == "discord" and not (host.endswith("discord.com") or host.endswith("discordapp.com")):
        raise NotifyError("A Discord webhook URL starts with https://discord.com/api/webhooks/.")
    if kind == "slack" and host != "hooks.slack.com":
        raise NotifyError("A Slack webhook URL starts with https://hooks.slack.com/.")
    clean["url"] = url
    return clean


def add_channel(channel: dict[str, Any]) -> dict[str, Any]:
    clean = validate_channel(channel)
    channels = [c for c in load_channels() if c["name"] != clean["name"]]
    channels.append(clean)
    save_channels(channels)
    return clean


def remove_channel(name: str) -> bool:
    channels = load_channels()
    kept = [c for c in channels if c["name"] != name]
    if len(kept) == len(channels):
        return False
    save_channels(kept)
    return True


def masked(channel: dict[str, Any]) -> str:
    """A printable description that does not reveal the secret part."""
    if channel["type"] == "telegram":
        return f"bot …{str(channel.get('bot_token', ''))[-4:]} → chat {channel.get('chat_id')}"
    parsed = urllib.parse.urlparse(str(channel.get("url", "")))
    tail = parsed.path.rstrip("/")[-4:]
    return f"{parsed.scheme}://{parsed.netloc}/…{tail}" if tail else f"{parsed.scheme}://{parsed.netloc}"


# ─── Delivery ───────────────────────────────────────────────────


def _request(url: str, *, body: bytes, content_type: str, headers: Optional[dict[str, str]] = None) -> None:
    from m_gpux import __version__

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    req.add_header("User-Agent", f"m-gpux/{__version__} (+https://github.com/PuxHocDL/m-gpux)")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 - URL validated as http(s)
        resp.read(1024)


def payload_for(
    channel: dict[str, Any], event: str, title: str, message: str, level: str
) -> tuple[str, bytes, str, dict]:
    """``(url, body, content_type, headers)`` for one channel. Pure, so it is unit-tested."""
    icon = LEVEL_ICON.get(level, "")
    text = f"{icon} {title}".strip() + (f"\n{message}" if message else "")
    kind = channel["type"]
    if kind == "discord":
        body = {"content": text[:1900], "username": "m-gpux", "allowed_mentions": {"parse": []}}
        return channel["url"], json.dumps(body).encode(), "application/json", {}
    if kind == "slack":
        return channel["url"], json.dumps({"text": text[:3000]}).encode(), "application/json", {}
    if kind == "telegram":
        url = f"https://api.telegram.org/bot{channel['bot_token']}/sendMessage"
        body = {"chat_id": channel["chat_id"], "text": text[:4000], "disable_web_page_preview": True}
        return url, json.dumps(body).encode(), "application/json", {}
    if kind == "ntfy":
        priority = {"error": "high", "warning": "high"}.get(level, "default")
        # Header values must be latin-1; keep the title ASCII-safe.
        safe_title = title.encode("ascii", "replace").decode()[:200]
        headers = {"Title": safe_title, "Priority": priority, "Tags": f"m-gpux,{event}"}
        return channel["url"], message.encode() or title.encode(), "text/plain; charset=utf-8", headers
    body = {"source": "m-gpux", "event": event, "level": level, "title": title, "message": message, "time": utc_now()}
    return channel["url"], json.dumps(body).encode(), "application/json", {}


def _subscribed(channel: dict[str, Any], event: str) -> bool:
    events = channel.get("events") or ["*"]
    return "*" in events or event in events or event == "test"


def send(
    event: str,
    title: str,
    message: str = "",
    *,
    level: str = "info",
    channels: Optional[list[dict[str, Any]]] = None,
) -> list[tuple[str, bool, str]]:
    """Deliver to every subscribed channel. Returns ``[(channel, ok, error)]``; never raises."""
    results: list[tuple[str, bool, str]] = []
    for channel in load_channels() if channels is None else channels:
        if not _subscribed(channel, event):
            continue
        try:
            url, body, content_type, headers = payload_for(channel, event, title, message, level)
            _request(url, body=body, content_type=content_type, headers=headers)
            results.append((channel["name"], True, ""))
        except urllib.error.HTTPError as exc:
            results.append((channel["name"], False, f"HTTP {exc.code}"))
        except Exception as exc:
            # Never echo the URL: urllib errors can include it.
            results.append((channel["name"], False, type(exc).__name__))
    return results


def notify(event: str, title: str, message: str = "", *, level: str = "info") -> None:
    """Fire-and-forget form of :func:`send` for use inside other commands."""
    if not load_channels():
        return
    failed = [name for name, ok, _ in send(event, title, message, level=level) if not ok]
    if failed:
        from m_gpux.core.console import console

        console.print(f"[dim]Notification failed for: {', '.join(failed)} (m-gpux notify test)[/dim]")
