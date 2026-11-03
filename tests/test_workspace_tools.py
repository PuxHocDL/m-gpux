from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import typer
from typer.testing import CliRunner

from m_gpux.core import notify, project, router
from m_gpux.main import app
from m_gpux.plugins.notify import plugin as notify_plugin
from m_gpux.plugins.project import plugin as project_plugin
from m_gpux.plugins.secrets import plugin as secrets_plugin
from m_gpux.plugins.volume import plugin as volume_plugin

runner = CliRunner()


class ProjectFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_defaults_merge_into_tasks_and_values_are_normalised(self) -> None:
        (self.root / "requirements.txt").write_text("numpy\n")
        doc = {
            "project": {"name": "Demo Proj"},
            "defaults": {"gpu": ["H100", "A100-80GB"], "gpu_count": 2, "requirements": "requirements.txt"},
            "tasks": {
                "train": {"command": "python train.py", "timeout": "30m"},
                "eval": {"command": "x", "gpu": "none"},
            },
        }
        loaded = project.validate_project(doc, self.root)
        train, evaluate = loaded["tasks"]["train"], loaded["tasks"]["eval"]
        self.assertEqual(loaded["name"], "demo-proj")
        self.assertEqual(train["gpus"], ["H100:2", "A100-80GB:2"])
        self.assertEqual(train["timeout"], 1800)
        self.assertTrue(train["requirements"].endswith("requirements.txt"))
        self.assertEqual((evaluate["gpus"], evaluate["cpu"]), ([], 2.0))

    def test_invalid_files_fail_with_a_clear_message(self) -> None:
        cases = [
            ({"tasks": {}}, "at least one task"),
            ({"tasks": {"t": {"command": "x", "gpu": "RTX9000"}}}, "Unknown GPU"),
            ({"tasks": {"t": {"command": "x", "typo": 1}}}, "unknown key"),
            ({"tasks": {"t": {"command": "x", "timeout": "2d"}}}, "timeout"),
            ({"tasks": {"t": {"command": "x", "volumes": {"/workspace": "v"}}}}, "volume mount"),
            ({"tasks": {"t": {"command": "x", "requirements": "nope.txt"}}}, "not found"),
            (
                {"tasks": {"t": {"command": "x"}}, "sweeps": {"s": {"task": "missing", "grid": {"a": [1]}}}},
                "not declared",
            ),
            ({"extra": 1, "tasks": {"t": {"command": "x"}}}, "top-level"),
        ]
        for doc, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(project.ProjectError, message):
                project.validate_project(doc, self.root)

    def test_grid_expansion_and_parameter_substitution(self) -> None:
        grid = project.parse_grid_args(["lr=1e-4,3e-4", "batch=16,32", "opt=adam"])
        self.assertEqual(grid, {"lr": [0.0001, 0.0003], "batch": [16, 32], "opt": ["adam"]})
        combos = project.expand_grid(grid)
        self.assertEqual(len(combos), 4)
        self.assertEqual(
            project.apply_params("python t.py --lr {lr}", {"lr": 0.001, "name": "a b"}),
            "python t.py --lr 0.001 --name 'a b'",
        )
        with self.assertRaisesRegex(project.ProjectError, "limit"):
            project.expand_grid({"a": list(range(20)), "b": list(range(20))}, limit=100)

    def test_rendered_script_is_valid_python_with_every_marker_filled(self) -> None:
        doc = {
            "defaults": {"gpu": "L4", "secrets": ["hf"], "volumes": {"/data": "ds"}, "pip": ["torch"]},
            "tasks": {"train": {"command": "python train.py"}},
        }
        loaded = project.validate_project(doc, self.root)
        task = loaded["tasks"]["train"]
        script = project.render_script(
            loaded, task, [{"command": "python train.py", "params": {"lr": 1}}], "r1", "/tmp/r1.json"
        )
        self.assertNotRegex(script.replace("# __METRICS__", ""), r"__[A-Z_]+__")
        compile(script.replace("# __METRICS__", ""), "modal_runner.py", "exec")
        self.assertIn("gpu='L4'", script)
        self.assertIn("'/root/.cache/huggingface': 'm-gpux-hf-cache'", script)
        # The runner's summary regex stops at the first ')' inside the decorator.
        decorator = re.search(r"@app\.function\(([^)]*)\)", script).group(1)
        self.assertIn("timeout=3600", decorator)

    def test_best_run_and_cost_estimate(self) -> None:
        results = [
            {"index": 0, "exit_code": 0, "result": {"loss": 0.3}},
            {"index": 1, "exit_code": 0, "result": {"loss": 0.1}},
            {"index": 2, "exit_code": 1, "result": {"loss": 0.0}},
        ]
        self.assertEqual(project.pick_best(results, "loss", "min")["index"], 1)
        self.assertEqual(project.pick_best(results, "loss", "max")["index"], 0)
        self.assertIsNone(project.pick_best(results, None))
        task = project.resolve_task({"command": "x", "gpu": "none", "cpu": 2}, "t", self.root)
        self.assertGreater(project.estimate_cost(task, 3600), 0)

    def test_init_template_round_trips_and_is_found_from_subfolders(self) -> None:
        path = self.root / project.PROJECT_FILE
        path.write_text(project.render_template("demo", 'python "a b.py"', requirements=False), encoding="utf-8")
        loaded = project.load_project(path)
        self.assertEqual(loaded["tasks"]["main"]["command"], 'python "a b.py"')
        nested = self.root / "src" / "pkg"
        nested.mkdir(parents=True)
        self.assertEqual(project.find_project(nested), path.resolve())


class UpCommandTests(unittest.TestCase):
    def test_up_records_the_run_and_notifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / project.PROJECT_FILE).write_text(
                '[tasks.train]\ncommand = "python train.py"\ngpu = "T4"\n', encoding="utf-8"
            )

            def fake_execute(content, description, **kwargs):
                self.assertTrue(kwargs["assume_yes"])
                self.assertEqual(kwargs["profile"], "p1")
                path = re.search(r"RESULTS_PATH = '([^']+)'", content).group(1)
                Path(path).write_text(
                    json.dumps(
                        {
                            "results": [
                                {"index": 0, "params": {}, "exit_code": 0, "seconds": 12.5, "result": {"acc": 0.9}}
                            ]
                        }
                    )
                )

            with (
                mock.patch.object(project_plugin, "RUNS_DIR", root / "runs"),
                mock.patch("m_gpux.core.runner.execute_modal_temp_script", side_effect=fake_execute),
                mock.patch.object(project_plugin, "resolve_account", return_value="p1"),
                mock.patch.object(project_plugin, "notify") as sent,
                mock.patch.object(project_plugin.Path, "cwd", return_value=root),
            ):
                result = runner.invoke(app, ["up", "train", "--yes", "--", "--epochs", "2"])
                self.assertEqual(result.exit_code, 0, result.output)
                record = json.loads(next((root / "runs").glob("*.json")).read_text())
        self.assertEqual(record["status"], "done")
        self.assertEqual(record["compute_seconds"], 12.5)
        self.assertEqual(sent.call_args.args[0], "run.done")

    def test_dry_run_prints_the_app_without_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / project.PROJECT_FILE).write_text('[tasks.t]\ncommand = "echo {lr}"\n', encoding="utf-8")
            with (
                mock.patch.object(project_plugin, "RUNS_DIR", root / "runs"),
                mock.patch("m_gpux.core.runner.execute_modal_temp_script") as execute,
                mock.patch.object(project_plugin.Path, "cwd", return_value=root),
            ):
                result = runner.invoke(app, ["sweep", "t", "--grid", "lr=1,2", "--dry-run"])
        self.assertEqual(result.exit_code, 0, result.output)
        execute.assert_not_called()
        self.assertIn("echo 1", result.output)


class NotifyTests(unittest.TestCase):
    def test_channels_are_validated(self) -> None:
        bad = [
            {"name": "d", "type": "discord", "url": "http://discord.com/api/webhooks/1/x"},
            {"name": "d", "type": "discord", "url": "https://evil.example/api/webhooks/1/x"},
            {"name": "s", "type": "slack", "url": "https://hooks.example.com/x"},
            {"name": "t", "type": "telegram", "bot_token": "nope", "chat_id": "1"},
            {"name": "w", "type": "webhook", "url": "https://x.example", "events": ["bogus"]},
            {"name": "bad name!", "type": "webhook", "url": "https://x.example"},
        ]
        for channel in bad:
            with self.subTest(channel=channel), self.assertRaises(notify.NotifyError):
                notify.validate_channel(channel)
        ok = notify.validate_channel({"name": "local", "type": "webhook", "url": "http://localhost:9000/hook"})
        self.assertEqual(ok["events"], ["*"])

    def test_masked_never_shows_the_secret_part(self) -> None:
        discord = {"name": "d", "type": "discord", "url": "https://discord.com/api/webhooks/123/SECRETTOKENabcd"}
        telegram = {
            "name": "t",
            "type": "telegram",
            "bot_token": "123456:SECRETSECRETSECRETSECRETxyz9",
            "chat_id": "42",
        }
        self.assertNotIn("SECRET", notify.masked(discord))
        self.assertNotIn("SECRET", notify.masked(telegram))

    def test_payloads_per_channel_type(self) -> None:
        tg = {"name": "t", "type": "telegram", "bot_token": "1:abc", "chat_id": "42"}
        url, body, _, _ = notify.payload_for(tg, "run.done", "Done", "ok", "success")
        self.assertTrue(url.startswith("https://api.telegram.org/bot1:abc/"))
        self.assertEqual(json.loads(body)["chat_id"], "42")
        ntfy = {"name": "n", "type": "ntfy", "url": "https://ntfy.sh/topic"}
        _, body, ctype, headers = notify.payload_for(ntfy, "credit.low", "Lów crédit", "msg", "warning")
        self.assertEqual((body, headers["Priority"]), (b"msg", "high"))
        headers["Title"].encode("latin-1")  # header values must be latin-1 safe
        hook = {"name": "w", "type": "webhook", "url": "https://x.example"}
        self.assertEqual(json.loads(notify.payload_for(hook, "test", "T", "", "info")[1])["event"], "test")
        discord = {"name": "d", "type": "discord", "url": "https://discord.com/api/webhooks/1/x"}
        self.assertEqual(
            json.loads(notify.payload_for(discord, "test", "T", "", "info")[1])["allowed_mentions"], {"parse": []}
        )

    def test_send_filters_by_event_and_reports_failures_without_raising(self) -> None:
        channels = [
            {"name": "all", "type": "webhook", "url": "https://a.example", "events": ["*"]},
            {"name": "runs", "type": "webhook", "url": "https://b.example", "events": ["run.done"]},
        ]
        with mock.patch.object(notify, "_request", side_effect=[None, OSError("boom https://a.example")]) as req:
            results = notify.send("credit.low", "t", channels=channels)
            self.assertEqual(results, [("all", True, "")])
            results = notify.send("run.done", "t", channels=channels[1:])
        self.assertEqual(results, [("runs", False, "OSError")])
        self.assertEqual(req.call_count, 2)

    def test_watch_reports_long_running_once_and_stopped_apps(self) -> None:
        apps = [("p", "ap-1", "m-gpux-jupyter", "deployed")]
        state, events = notify_plugin.diff_apps({}, apps, now=1000.0, long_running=3600)
        self.assertEqual(events, [])
        state, events = notify_plugin.diff_apps(state, apps, now=1000.0 + 3700, long_running=3600)
        self.assertEqual([e[0] for e in events], ["app.long_running"])
        state, events = notify_plugin.diff_apps(state, apps, now=1000.0 + 7200, long_running=3600)
        self.assertEqual(events, [])
        state, events = notify_plugin.diff_apps(state, [], now=1000.0 + 7300, long_running=3600)
        self.assertEqual([e[0] for e in events], ["app.stopped"])
        self.assertEqual(state, {})

    def test_credit_alerts_fire_once_per_month(self) -> None:
        with mock.patch("m_gpux.core.budget.budget_for", side_effect=lambda p: 10.0 if p == "b" else None):
            warned, events = notify_plugin.credit_events(
                [("a", 27.0, 3.0), ("b", 12.0, 0.0), ("c", 1.0, 29.0)], 5.0, {}, "2026-11"
            )
            self.assertEqual(sorted(e[0] for e in events), ["budget.over", "credit.low"])
            _, again = notify_plugin.credit_events([("a", 28.0, 2.0)], 5.0, warned, "2026-11")
            _, next_month = notify_plugin.credit_events([("a", 28.0, 2.0)], 5.0, warned, "2026-12")
        self.assertEqual((again, len(next_month)), ([], 1))


class SecretsTests(unittest.TestCase):
    def test_dotenv_parsing(self) -> None:
        text = '# c\nexport A=1\nB="two words"\nC=3 # note\nbad line\n9X=no\n'
        self.assertEqual(secrets_plugin.parse_dotenv(text), {"A": "1", "B": "two words", "C": "3"})

    def test_values_come_from_dotenv_then_env_and_never_from_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("HF_TOKEN=from-file\n")
            with mock.patch.dict("os.environ", {"WANDB_API_KEY": "from-env"}):
                values = secrets_plugin.collect_values(["HF_TOKEN", "WANDB_API_KEY"], env_file, prompt=False)
                self.assertEqual(values, {"HF_TOKEN": "from-file", "WANDB_API_KEY": "from-env"})
                with self.assertRaises(typer.BadParameter):
                    secrets_plugin.collect_values(["HF_TOKEN=leak"], None, prompt=False)
                with self.assertRaises(typer.BadParameter):
                    secrets_plugin.collect_values(["MISSING_X"], None, prompt=False)

    def test_sync_merges_existing_and_creates_missing_without_printing_values(self) -> None:
        listed = {"p1": ["hf"], "p2": []}
        current = {}

        def fake_for_each(profiles, action, **_):
            out = {}
            for p in profiles:
                current["profile"] = p
                out[p] = action(p, object())
            return out

        secret_cls = mock.MagicMock()
        secret_cls.objects.list.side_effect = lambda client: [
            SimpleNamespace(name=n) for n in listed[current["profile"]]
        ]
        with (
            mock.patch.object(secrets_plugin, "resolve_targets", return_value=["p1", "p2"]),
            mock.patch.object(secrets_plugin, "for_each", side_effect=fake_for_each),
            mock.patch("modal.Secret", secret_cls),
            mock.patch.dict("os.environ", {"HF_TOKEN": "hf_supersecret"}),
        ):
            result = runner.invoke(app, ["secrets", "sync", "hf", "HF_TOKEN", "--no-prompt"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn("hf_supersecret", result.output)
        secret_cls.from_name.return_value.update.assert_called_once_with({"HF_TOKEN": "hf_supersecret"})
        secret_cls.objects.create.assert_called_once_with("hf", {"HF_TOKEN": "hf_supersecret"}, client=mock.ANY)


class RouterTests(unittest.TestCase):
    def test_free_quota_first_then_modal_and_reasons_for_the_rest(self) -> None:
        kaggle_rows = [
            {"name": "k1", "quota": {"gpu": {"remaining": 20.0}}, "live": []},
            {"name": "k2", "quota": {"gpu": {"remaining": 0.5}}, "live": []},
            {"name": "k3", "quota": {"gpu": {"remaining": 30.0}}, "live": [{}, {}]},
        ]
        plan = router.plan(
            "T4", 2, kaggle_rows=kaggle_rows, colab_rows=[], modal_balances=[("m1", 5.0, 25.0), ("m2", 30.0, 0.0)]
        )
        self.assertEqual([(c["platform"], c["account"]) for c in plan if c["ok"]], [("kaggle", "k1"), ("modal", "m1")])
        notes = {c["account"]: c["note"] for c in plan if not c["ok"]}
        self.assertIn("< 2 h", notes["k2"])
        self.assertIn("slots busy", notes["k3"])
        self.assertIn("needed", notes["m2"])

    def test_gpus_a_platform_lacks_are_explained(self) -> None:
        plan = router.plan("H100", 1, where="kaggle", kaggle_rows=[{"name": "k", "quota": {"gpu": {"remaining": 30}}}])
        self.assertFalse(plan[0]["ok"])
        self.assertIn("Kaggle offers", plan[0]["note"])
        meta = router.kaggle_metadata("me", "mgpux-train", "train.py", "T4")
        self.assertEqual(
            (meta["id"], meta["machine_shape"], meta["enable_gpu"]), ("me/mgpux-train", "NvidiaTeslaT4", True)
        )


class VolumeTests(unittest.TestCase):
    def test_usage_is_grouped_by_top_level_entry(self) -> None:
        files = [
            {"path": "ckpt/a.pt", "type": "file", "size": 300},
            {"path": "ckpt/b.pt", "type": "file", "size": 200},
            {"path": "ckpt", "type": "directory", "size": 0},
            {"path": "notes.txt", "type": "file", "size": 10},
        ]
        self.assertEqual(volume_plugin.summarize_usage(files), [("ckpt", 500, 2), ("notes.txt", 10, 1)])
        self.assertEqual(volume_plugin.human_size(1536), "1.5 KB")


class RunnerTests(unittest.TestCase):
    def test_assume_yes_never_prompts_and_pins_the_profile(self) -> None:
        from m_gpux.core import runner as core_runner

        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with (
                    mock.patch.object(core_runner.Prompt, "ask", side_effect=AssertionError("prompted")),
                    mock.patch.object(core_runner.subprocess, "run", return_value=mock.Mock(returncode=0)) as run,
                ):
                    core_runner.execute_modal_temp_script("import modal\n", "test", profile="p9", assume_yes=True)
                self.assertFalse(Path(tmp, "modal_runner.py").exists())
            finally:
                os.chdir(cwd)
        self.assertEqual(run.call_args.kwargs["env"]["MODAL_PROFILE"], "p9")


if __name__ == "__main__":
    unittest.main()
