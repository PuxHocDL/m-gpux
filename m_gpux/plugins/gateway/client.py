"""Small dependency-free HTTP client for a deployed Compute Gateway."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

# Modal keeps spawned results (and idle Dict entries) for 7 days, after which a
# job is reported as "expired".
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "expired"})


class GatewayHTTPError(RuntimeError):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"gateway returned HTTP {status}: {detail}")


def gateway_request(
    url: str,
    api_key: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> Any:
    body = None
    request_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        **(headers or {}),
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url.rstrip("/") + "/" + path.lstrip("/"),
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            parsed = json.loads(raw)
            detail = parsed.get("detail", parsed) if isinstance(parsed, dict) else parsed
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = raw.decode("utf-8", errors="replace") or exc.reason
        raise GatewayHTTPError(exc.code, str(detail)) from None
    except urllib.error.URLError as exc:
        raise GatewayHTTPError(0, str(exc.reason)) from None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GatewayHTTPError(0, "gateway returned a non-JSON response") from exc


def wait_for_job(
    url: str,
    api_key: str,
    job_id: str,
    *,
    timeout: float = 900.0,
    interval: float = 1.0,
) -> dict[str, Any]:
    """Poll until a job reaches a terminal state or the client timeout expires."""
    deadline = time.monotonic() + timeout
    while True:
        result = gateway_request(url, api_key, f"/v1/jobs/{job_id}", timeout=min(30.0, timeout))
        if not isinstance(result, dict):
            raise GatewayHTTPError(0, "gateway returned an invalid job response")
        if result.get("status") in TERMINAL_STATES:
            return result
        if time.monotonic() >= deadline:
            raise TimeoutError(f"job {job_id} did not finish within {timeout:g}s")
        time.sleep(max(0.1, interval))
