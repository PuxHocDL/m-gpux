from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from m_gpux.plugins.gateway.config import GatewayConfigError, load_gateway_config
from m_gpux.plugins.gateway.renderer import render_gateway_app


VALID_MANIFEST = '''[gateway]
name = "m-gpux-test-gateway"
source = "."
max_input_bytes = 2048
max_output_bytes = 4096

[tasks.echo]
description = "Echo JSON"
command = ["python", "worker.py"]
packages = []
cpu = 0.25
memory = 256
timeout = 30
'''


class GatewayConfigTests(unittest.TestCase):
    def write_manifest(self, root: Path, text: str, *, bom: bool = False) -> Path:
        path = root / "mgpux.gateway.toml"
        encoding = "utf-8-sig" if bom else "utf-8"
        path.write_text(text, encoding=encoding)
        return path

    def test_loads_valid_windows_bom_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_gateway_config(self.write_manifest(Path(tmp), VALID_MANIFEST, bom=True))
            self.assertEqual(config.name, "m-gpux-test-gateway")
            self.assertEqual(config.max_input_bytes, 2048)
            self.assertEqual(config.tasks[0].command, ("python", "worker.py"))

    def test_rejects_shell_command_string(self) -> None:
        manifest = VALID_MANIFEST.replace('command = ["python", "worker.py"]', 'command = "python worker.py"')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(GatewayConfigError, "array of non-empty strings"):
                load_gateway_config(self.write_manifest(Path(tmp), manifest))

    def test_rejects_timeout_below_modal_server_minimum(self) -> None:
        manifest = VALID_MANIFEST.replace("timeout = 30", "timeout = 5")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(GatewayConfigError, "timeout must be an integer from 10"):
                load_gateway_config(self.write_manifest(Path(tmp), manifest))

    def test_rejects_invalid_task_name(self) -> None:
        manifest = VALID_MANIFEST.replace("[tasks.echo]", '[tasks."echo; rm"]')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(GatewayConfigError, "task name"):
                load_gateway_config(self.write_manifest(Path(tmp), manifest))


class GatewayRendererTests(unittest.TestCase):
    def test_generated_app_compiles_and_keeps_key_out_of_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "mgpux.gateway.toml"
            path.write_text(VALID_MANIFEST, encoding="utf-8")
            source = render_gateway_app(load_gateway_config(path), "gateway-secret-name")

            compile(source, "modal_gateway.py", "exec")
            self.assertIn("gateway-secret-name", source)
            self.assertNotIn("MGPUX_TEST_SECRET_VALUE", source)
            self.assertIn("shell=False", source)
            self.assertIn('command=[\'python\', \'worker.py\']', source)
            self.assertIn("hmac.compare_digest", source)
            self.assertIn("skip_if_exists=True", source)

    def render(self) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mgpux.gateway.toml"
            path.write_text(VALID_MANIFEST, encoding="utf-8")
            return render_gateway_app(load_gateway_config(path), "gateway-secret-name")

    def test_async_handlers_only_use_aio_modal_calls(self) -> None:
        handlers = self.render().split("def gateway():", 1)[1]
        for blocking in ("jobs.get(", "jobs.put(", "jobs.pop(", "jobs[", ".spawn(", ".get(timeout", ".cancel(", ".tail("):
            self.assertNotIn(blocking, handlers)
        for async_call in ("jobs.get.aio(", "jobs.put.aio(", ".spawn.aio(", ".get.aio(timeout=0)", ".cancel.aio(", ".tail.aio("):
            self.assertIn(async_call, handlers)

    def test_expired_and_timed_out_jobs_are_not_reported_as_running(self) -> None:
        # Both subclass TimeoutError, so they must be caught before it.
        source = self.render()
        expired = source.index("except OutputExpiredError")
        timed_out = source.index("except FunctionTimeoutError")
        running = source.index("except TimeoutError")
        self.assertLess(expired, running)
        self.assertLess(timed_out, running)


class GatewayClientTests(unittest.TestCase):
    def test_wait_for_job_stops_on_expired(self) -> None:
        from m_gpux.plugins.gateway import client

        with mock.patch.object(client, "gateway_request", return_value={"id": "fc-1", "status": "expired"}) as req:
            result = client.wait_for_job("https://x.modal.run", "k", "fc-1", timeout=5)
        self.assertEqual(result["status"], "expired")
        req.assert_called_once()


class GatewayJobsCommandTests(unittest.TestCase):
    def test_refresh_marks_forgotten_jobs_expired_and_skips_finished(self) -> None:
        from typer.testing import CliRunner

        from m_gpux.core import state
        from m_gpux.plugins.gateway import plugin
        from m_gpux.plugins.gateway.client import GatewayHTTPError

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(state, "GATEWAY_PATH", Path(tmp) / "gateway.json"):
            state.save_gateway_endpoint("https://x.modal.run", "k")
            state.save_gateway_job({"id": "fc-done", "task": "echo", "status": "succeeded"})
            state.save_gateway_job({"id": "fc-old", "task": "echo", "status": "running"})
            with mock.patch.object(plugin, "gateway_request", side_effect=GatewayHTTPError(404, "gone")) as req:
                outcome = CliRunner().invoke(plugin.app, ["jobs", "--refresh"])
            self.assertEqual(outcome.exit_code, 0, outcome.output)
            req.assert_called_once()  # the succeeded job is not re-polled
            statuses = {job["id"]: job["status"] for job in state.list_gateway_jobs()}
        self.assertEqual(statuses, {"fc-done": "succeeded", "fc-old": "expired"})


if __name__ == "__main__":
    unittest.main()
