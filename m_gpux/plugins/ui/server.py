"""Local HTTP server for the m-gpux dashboard (stdlib only).

Security model, since this server can stop apps and edit ~/.modal.toml:

* It binds to loopback by default and rejects any ``Host`` header other than
  the address it serves, which defeats DNS-rebinding attacks.
* Every ``/api`` call needs ``Authorization: Bearer <token>``. The token is
  random per launch and travels in the URL *fragment*, which browsers never
  send to a server or put in a Referer. A custom header also means a foreign
  page cannot forge a request without a CORS preflight, which is never granted.
* Static assets are served under a strict Content-Security-Policy.
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import re
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from m_gpux.plugins.ui import data

STATIC_DIR = Path(__file__).parent / "static"
MAX_BODY = 64 * 1024
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".json": "application/json",
    ".ico": "image/x-icon",
}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

Handler = Callable[[re.Match, dict[str, str], dict[str, Any]], Any]
ROUTES: list[tuple[str, re.Pattern, Handler]] = []


def route(method: str, pattern: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn))
        return fn

    return register


def _flag(query: dict[str, str], name: str) -> bool:
    return query.get(name, "").lower() in ("1", "true", "yes")


def _seg(match: re.Match, name: str) -> str:
    return unquote(match.group(name))


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ─── API routes ───────────────────────────────────────────────

SEG = r"[^/]+"


@route("GET", r"/api/info")
def _info(m, q, b):
    return data.info()


@route("GET", r"/api/accounts")
def _accounts(m, q, b):
    return data.accounts(refresh=_flag(q, "refresh"))


@route("POST", r"/api/accounts")
def _add_account(m, q, b):
    return data.add_account(str(b.get("name", "")), str(b.get("token_id", "")), str(b.get("token_secret", "")))


@route("POST", rf"/api/accounts/(?P<name>{SEG})/activate")
def _activate(m, q, b):
    return data.activate_account(_seg(m, "name"))


@route("DELETE", rf"/api/accounts/(?P<name>{SEG})")
def _remove(m, q, b):
    return data.remove_account(_seg(m, "name"))


@route("PUT", r"/api/budgets")
def _budget(m, q, b):
    limit = b.get("limit")
    if limit is not None and not isinstance(limit, (int, float)):
        raise data.ActionError("limit must be a number or null")
    return data.update_budget(b.get("profile") or None, None if limit is None else float(limit))


@route("GET", r"/api/apps")
def _apps(m, q, b):
    return data.apps(q.get("profile") or None, refresh=_flag(q, "refresh"))


@route("POST", rf"/api/apps/(?P<profile>{SEG})/(?P<id>{SEG})/stop")
def _stop_app(m, q, b):
    return data.stop_modal_app(_seg(m, "profile"), _seg(m, "id"))


@route("GET", rf"/api/apps/(?P<profile>{SEG})/(?P<id>{SEG})/logs")
def _app_logs(m, q, b):
    return data.app_logs(_seg(m, "profile"), _seg(m, "id"), _int(q.get("tail"), 200))


@route("GET", r"/api/containers")
def _containers(m, q, b):
    return data.containers(q.get("profile") or None, refresh=_flag(q, "refresh"))


@route("POST", rf"/api/containers/(?P<profile>{SEG})/(?P<id>{SEG})/stop")
def _stop_container(m, q, b):
    return data.stop_container(_seg(m, "profile"), _seg(m, "id"))


@route("GET", rf"/api/containers/(?P<profile>{SEG})/(?P<id>{SEG})/logs")
def _container_logs(m, q, b):
    return data.container_logs(_seg(m, "profile"), _seg(m, "id"), _int(q.get("tail"), 200))


@route("GET", r"/api/sandboxes")
def _sandboxes(m, q, b):
    return data.sandboxes(q.get("profile") or None, refresh=_flag(q, "refresh"))


@route("POST", rf"/api/sandboxes/(?P<profile>{SEG})/(?P<id>{SEG})/terminate")
def _terminate(m, q, b):
    return data.terminate_sandbox(_seg(m, "profile"), _seg(m, "id"))


@route("GET", r"/api/sessions")
def _sessions(m, q, b):
    return data.sessions(q.get("profile") or None)


@route("DELETE", rf"/api/sessions/(?P<id>{SEG})")
def _forget(m, q, b):
    return data.forget_session(_seg(m, "id"))


@route("GET", r"/api/endpoints")
def _endpoints(m, q, b):
    return data.endpoints()


@route("GET", r"/api/library")
def _library(m, q, b):
    return data.library()


@route("GET", r"/api/volumes")
def _volumes(m, q, b):
    return data.volumes(q.get("profile") or None, refresh=_flag(q, "refresh"))


@route("GET", rf"/api/volumes/(?P<profile>{SEG})/(?P<name>{SEG})/files")
def _volume_files(m, q, b):
    return data.volume_files(_seg(m, "profile"), _seg(m, "name"), q.get("path") or "/")


@route("GET", r"/api/secrets")
def _secrets(m, q, b):
    return data.secrets_matrix(refresh=_flag(q, "refresh"))


@route("GET", r"/api/runs")
def _runs(m, q, b):
    return data.runs()


@route("GET", r"/api/notify")
def _notify(m, q, b):
    return data.notifications()


@route("POST", r"/api/notify/test")
def _notify_test(m, q, b):
    return data.test_notifications()


@route("GET", r"/api/billing")
def _billing(m, q, b):
    return data.billing()


@route("GET", r"/api/kaggle")
def _kaggle(m, q, b):
    return data.kaggle(refresh=_flag(q, "refresh"))


@route("GET", r"/api/colab")
def _colab(m, q, b):
    return data.colab(refresh=_flag(q, "refresh"))


@route("POST", rf"/api/colab/(?P<account>{SEG})/sessions/(?P<session>{SEG})/stop")
def _stop_colab(m, q, b):
    return data.stop_colab_session(_seg(m, "account"), _seg(m, "session"))


# ─── HTTP plumbing ────────────────────────────────────────────


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # never share a port with another process on Windows

    def __init__(self, address: tuple[str, int], token: Optional[str] = None):
        super().__init__(address, RequestHandler)
        self.token = token or secrets.token_urlsafe(32)
        port = self.server_address[1]
        hosts = {address[0], "127.0.0.1", "localhost"} if address[0] in ("127.0.0.1", "localhost") else {address[0]}
        self.allowed_hosts = {f"{host}:{port}" for host in hosts}

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/#token={self.token}"


class RequestHandler(BaseHTTPRequestHandler):
    server: DashboardServer
    server_version = "m-gpux-ui"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # keep the terminal quiet
        pass

    def do_GET(self) -> None:
        self._handle("GET")

    def do_POST(self) -> None:
        self._handle("POST")

    def do_PUT(self) -> None:
        self._handle("PUT")

    def do_DELETE(self) -> None:
        self._handle("DELETE")

    def _handle(self, method: str) -> None:
        if self.headers.get("Host", "") not in self.server.allowed_hosts:
            self._json(HTTPStatus.MISDIRECTED_REQUEST, {"error": "unexpected Host header"})
            return
        url = urlsplit(self.path)
        if url.path.startswith("/api/"):
            self._api(method, url.path, {k: v[-1] for k, v in parse_qs(url.query).items()})
        elif method == "GET":
            self._static(url.path)
        else:
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})

    def _api(self, method: str, path: str, query: dict[str, str]) -> None:
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not supplied or not hmac.compare_digest(supplied, self.server.token):
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "missing or invalid dashboard token"})
            return
        body: dict[str, Any] = {}
        if method in ("POST", "PUT", "DELETE"):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                # Drain a moderately large body so the client reads the 413
                # instead of a reset (Windows aborts a send to a closed socket).
                if length <= 16 * MAX_BODY:
                    self.rfile.read(length)
                self.close_connection = True
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request body too large"})
                return
            raw = self.rfile.read(length) if length else b""
            if raw:
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "body must be JSON"})
                    return
                if not isinstance(parsed, dict):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "body must be a JSON object"})
                    return
                body = parsed
        allowed = []
        for verb, pattern, handler in ROUTES:
            match = pattern.match(path)
            if not match:
                continue
            if verb != method:
                allowed.append(verb)
                continue
            try:
                self._json(HTTPStatus.OK, handler(match, query, body))
            except data.ActionError as exc:
                self._json(exc.status, {"error": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            return
        if allowed:
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method not allowed"})
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "no such endpoint"})

    def _static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else unquote(path).lstrip("/")
        target = (STATIC_DIR / relative).resolve()
        if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
            # Client-side routes (#/apps) never reach here; anything else is a 404.
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain; charset=utf-8")
            return
        # Fixed types: Windows' registry can map .js to text/plain, which
        # nosniff would then refuse to execute.
        kind = (
            CONTENT_TYPES.get(target.suffix.lower())
            or mimetypes.guess_type(target.name)[0]
            or "application/octet-stream"
        )
        self._send(HTTPStatus.OK, target.read_bytes(), kind)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"), "application/json")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(body)
