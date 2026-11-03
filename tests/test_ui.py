from __future__ import annotations

import http.client
import json
import threading
import tomlkit
import unittest
from pathlib import Path
from unittest import mock

from m_gpux.plugins.ui import data
from m_gpux.plugins.ui.server import STATIC_DIR, DashboardServer

ROOT = Path(__file__).resolve().parents[1]


class DashboardServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = DashboardServer(("127.0.0.1", 0), token="test-token")
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method: str, path: str, *, token: str | None = "test-token", host: str | None = None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = None
        if body is not None:
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, dict(response.getheaders()), raw

    def test_api_requires_the_launch_token(self) -> None:
        self.assertEqual(self.request("GET", "/api/info", token=None)[0], 401)
        self.assertEqual(self.request("GET", "/api/info", token="wrong")[0], 401)
        with mock.patch.object(data, "info", return_value={"version": "x", "accounts": 0}):
            status, _, raw = self.request("GET", "/api/info")
        self.assertEqual((status, json.loads(raw)), (200, {"version": "x", "accounts": 0}))

    def test_foreign_host_header_is_rejected(self) -> None:
        # DNS rebinding: a hostile name resolving to 127.0.0.1 must not reach the API or the page.
        self.assertEqual(self.request("GET", "/api/info", host=f"evil.example:{self.port}")[0], 421)
        self.assertEqual(self.request("GET", "/", host=f"evil.example:{self.port}", token=None)[0], 421)
        with mock.patch.object(data, "info", return_value={}):
            self.assertEqual(self.request("GET", "/api/info", host=f"localhost:{self.port}")[0], 200)

    def test_static_files_are_served_with_csp_and_no_traversal(self) -> None:
        status, headers, raw = self.request("GET", "/", token=None)
        self.assertEqual(status, 200)
        self.assertIn(b'src="app.js"', raw)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, headers, _ = self.request("GET", "/app.js", token=None)
        self.assertEqual((status, headers["Content-Type"]), (200, "text/javascript; charset=utf-8"))
        self.assertEqual(self.request("GET", "/../pyproject.toml", token=None)[0], 404)
        self.assertEqual(self.request("GET", "/%2e%2e/pyproject.toml", token=None)[0], 404)

    def test_routing_errors_and_limits(self) -> None:
        self.assertEqual(self.request("GET", "/api/nope")[0], 404)
        self.assertEqual(self.request("DELETE", "/api/billing")[0], 405)
        self.assertEqual(self.request("POST", "/api/accounts", body=b"{not json")[0], 400)
        self.assertEqual(self.request("POST", "/api/accounts", body=b"[1]")[0], 400)
        self.assertEqual(self.request("POST", "/api/accounts", body=b"x" * 70_000)[0], 413)

    def test_action_errors_map_to_their_status(self) -> None:
        with mock.patch.object(data, "remove_account", side_effect=data.ActionError("unknown account 'x'", 404)):
            status, _, raw = self.request("DELETE", "/api/accounts/x")
        self.assertEqual((status, json.loads(raw)["error"]), (404, "unknown account 'x'"))

    def test_path_segments_are_url_decoded(self) -> None:
        with mock.patch.object(data, "activate_account", return_value={"active": "last hope 3"}) as activate:
            status, _, _ = self.request("POST", "/api/accounts/last%20hope%203/activate")
        self.assertEqual(status, 200)
        activate.assert_called_once_with("last hope 3")


class DashboardDataTests(unittest.TestCase):
    def setUp(self) -> None:
        data.invalidate()
        self.addCleanup(data.invalidate)

    def test_batch_caches_success_and_retries_failures_sooner(self) -> None:
        calls: list[str] = []

        async def fetch(profile: str):
            calls.append(profile)
            if profile == "bad":
                raise RuntimeError("unreachable")
            return {"workspace": profile}

        first = data._batch("t", ["good", "bad"], fetch, 300, False)
        self.assertEqual(first["good"], {"workspace": "good"})
        self.assertIsInstance(first["bad"], RuntimeError)
        data._batch("t", ["good", "bad"], fetch, 300, False)
        self.assertEqual(calls, ["good", "bad"])  # both cached for now
        with mock.patch.object(data.time, "monotonic", return_value=data.time.monotonic() + data.ERROR_TTL + 1):
            data._batch("t", ["good", "bad"], fetch, 300, False)
        self.assertEqual(calls, ["good", "bad", "bad"])  # only the failure is retried

    def test_accounts_never_expose_tokens_and_flag_unreachable_ones(self) -> None:
        config = {
            "a": {"token_id": "ak-SECRETID", "token_secret": "as-SECRET", "active": True},
            "b": {"token_id": "ak-2", "token_secret": "as-2"},
        }

        async def fetch(profile: str):
            if profile == "b":
                raise RuntimeError("Token not found")
            return {"workspace": "ws-a", "used": 7.5}

        with (
            mock.patch.object(data, "load_config", return_value=config),
            mock.patch.object(data, "_fetch_account", fetch),
            mock.patch.object(data, "load_budgets", return_value={"a": 20.0}),
        ):
            result = data.accounts()
        text = json.dumps(result)
        self.assertNotIn("SECRET", text)
        rows = {row["name"]: row for row in result["accounts"]}
        self.assertEqual((rows["a"]["cap"], rows["a"]["spendable"], rows["a"]["active"]), (20.0, 12.5, True))
        self.assertEqual((rows["b"]["status"], rows["b"]["error"]), ("error", "Token not found"))

    def test_sdk_work_from_many_threads_shares_one_loop(self) -> None:
        # Two request threads each running their own event loop made Modal's
        # .aio calls hang; everything must land on the single shared loop.
        import asyncio

        loops: list[object] = []

        async def where() -> None:
            await asyncio.sleep(0.01)
            loops.append(asyncio.get_running_loop())

        threads = [threading.Thread(target=lambda: data._run_async(where())) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(len(loops), 4)
        self.assertEqual(len(set(map(id, loops))), 1)

    def test_running_sessions_are_reconciled_with_accounts_and_live_apps(self) -> None:
        sessions = [
            {"id": "s1", "state": "running", "profile": "gone", "app_name": "a"},
            {"id": "s2", "state": "running", "profile": "p", "app_name": "dead"},
            {"id": "s3", "state": "running", "profile": "p", "app_name": "live"},
            {"id": "s4", "state": "stopped", "profile": "p", "app_name": "x"},
        ]
        data._cache[("_apps", ("p",))] = (data.time.monotonic(), [{"name": "live", "alive": True}])
        with (
            mock.patch("m_gpux.core.state.list_sessions", return_value=sessions),
            mock.patch.object(data, "load_config", return_value={"p": {"token_id": "ak-1", "token_secret": "as-1"}}),
        ):
            states = {s["id"]: s["state"] for s in data.sessions()["sessions"]}
        self.assertEqual(states, {"s1": "orphaned", "s2": "ended", "s3": "running", "s4": "stopped"})

    def test_volume_browsing_stays_inside_the_volume(self) -> None:
        with mock.patch.object(data, "load_config", return_value={"p": {"token_id": "ak-1", "token_secret": "as-1"}}):
            for name, path in (("v", "/a/../b"), ("v", "../etc"), ("bad name", "/"), ("../v", "/")):
                with self.subTest(name=name, path=path), self.assertRaises(data.ActionError):
                    data.volume_files("p", name, path)

    def test_notification_channels_are_masked(self) -> None:
        channel = {
            "name": "d",
            "type": "discord",
            "url": "https://discord.com/api/webhooks/1/SECRETTOKEN",
            "events": ["*"],
        }
        with mock.patch("m_gpux.core.notify.load_channels", return_value=[channel]):
            payload = json.dumps(data.notifications())
        self.assertNotIn("SECRET", payload)
        self.assertIn("discord.com", payload)

    def test_ids_and_names_are_validated_before_reaching_modal(self) -> None:
        with mock.patch.object(data, "load_config", return_value={"p": {"token_id": "ak-1", "token_secret": "as-1"}}):
            with self.assertRaises(data.ActionError):
                data.stop_modal_app("p", "--yes; rm -rf /")
            with self.assertRaises(data.ActionError):
                data.stop_container("missing", "ta-abc")
            with self.assertRaises(data.ActionError):
                data.add_account("../x", "ak-1", "as-1")


class DashboardPackagingTests(unittest.TestCase):
    def test_static_assets_ship_in_the_wheel(self) -> None:
        for name in ("index.html", "app.css", "app.js", "core.js", "views.js", "icons.js", "favicon.svg"):
            self.assertTrue((STATIC_DIR / name).is_file(), name)
        pyproject = tomlkit.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn("static/*", pyproject["tool"]["setuptools"]["package-data"]["m_gpux.plugins.ui"])
        self.assertEqual(
            pyproject["project"]["entry-points"]["m_gpux.plugins"]["ui"], "m_gpux.plugins.ui.plugin:UIPlugin"
        )


if __name__ == "__main__":
    unittest.main()
