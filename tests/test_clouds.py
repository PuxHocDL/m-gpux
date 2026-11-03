from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tomlkit

from m_gpux.core import colab
from m_gpux.core import kaggle as kz

ROOT = Path(__file__).resolve().parents[1]


def completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class KaggleZooTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.zoo = Path(self.tmp.name) / "zoo.json"
        patcher = mock.patch.object(kz, "ZOO_PATH", self.zoo)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.zoo.write_text(
            json.dumps(
                {
                    "accounts": {
                        "me": {"token": None, "team": "Đội A", "default": True, "note": "máy chính"},
                        "mate": {"token": "KGAT_secret_1234", "team": "Đội A", "no_submit": ["comp-x"]},
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_accounts_hide_tokens_and_know_machine_credentials(self) -> None:
        me, mate = kz.accounts()
        self.assertTrue(me.uses_machine_credentials)
        self.assertFalse(mate.uses_machine_credentials)
        self.assertNotIn("KGAT_secret", json.dumps([me.public(), mate.public()]))
        self.assertEqual(mate.public()["credentials"], "token …1234")

    def test_env_sets_or_clears_the_token(self) -> None:
        me, mate = kz.accounts()
        with mock.patch.dict(os.environ, {"KAGGLE_API_TOKEN": "inherited"}):
            self.assertNotIn("KAGGLE_API_TOKEN", kz.env_for(me))
            self.assertEqual(kz.env_for(mate)["KAGGLE_API_TOKEN"], "KGAT_secret_1234")

    def test_no_submit_is_enforced(self) -> None:
        mate = kz.get_account("MATE")
        with self.assertRaises(kz.KaggleError):
            kz.check_submit_allowed(mate, ["competitions", "submit", "comp-x", "-f", "s.csv", "-m", "x"])
        kz.check_submit_allowed(mate, ["competitions", "submit", "other", "-f", "s.csv"])
        kz.check_submit_allowed(mate, ["kernels", "push", "-p", "."])

    def test_save_keeps_order_and_unicode(self) -> None:
        zoo = kz.load_zoo()
        zoo["accounts"]["new"] = {"token": "KGAT_x", "note": "ghi chú"}
        kz.save_zoo(zoo)
        text = self.zoo.read_text(encoding="utf-8")
        self.assertIn("ghi chú", text)
        self.assertEqual(list(json.loads(text)["accounts"]), ["me", "mate", "new"])

    def test_push_as_another_account_rewrites_a_copy_only(self) -> None:
        folder = Path(self.tmp.name) / "my-kernel"
        folder.mkdir()
        meta = {"id": "me/my-kernel", "title": "my-kernel", "code_file": "k.ipynb"}
        (folder / "kernel-metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        (folder / "k.ipynb").write_text("{}", encoding="utf-8")
        pushed_ids = []

        def fake_run(account, args, **kwargs):
            pushed = Path(args[args.index("-p") + 1])
            pushed_ids.append(json.loads((pushed / "kernel-metadata.json").read_text(encoding="utf-8"))["id"])
            self.assertTrue((pushed / "k.ipynb").is_file())
            return completed("Kernel version 7 successfully pushed.")

        with mock.patch.object(kz, "run", side_effect=fake_run):
            result = kz.push_kernel(kz.get_account("mate"), folder)
        self.assertEqual(pushed_ids, ["mate/my-kernel"])
        self.assertEqual((result["ref"], result["version"]), ("mate/my-kernel", 7))
        self.assertEqual(
            json.loads((folder / "kernel-metadata.json").read_text(encoding="utf-8"))["id"], "me/my-kernel"
        )

    def test_push_reports_cli_errors_even_with_exit_code_zero(self) -> None:
        folder = Path(self.tmp.name) / "k2"
        folder.mkdir()
        (folder / "kernel-metadata.json").write_text(json.dumps({"id": "me/k2"}), encoding="utf-8")
        with mock.patch.object(kz, "run", return_value=completed("Kernel push error: Notebook not found")):
            with self.assertRaisesRegex(kz.KaggleError, "not found"):
                kz.push_kernel(kz.get_account("me"), folder)

    def test_auto_picks_most_gpu_hours_with_a_free_slot(self) -> None:
        def row(name, left, live=0, error=None):
            return {"name": name, "error": error, "live": [{}] * live, "quota": {"gpu": {"remaining": left}}}

        rows = [row("busy", 40, live=2), row("rich", 30), row("poor", 5), row("broken", 50, error="x")]
        self.assertEqual(kz.pick_account(rows), "rich")
        self.assertIsNone(kz.pick_account([row("empty", 0)]))

    def test_quota_parses_hours_and_marks_utc(self) -> None:
        payload = '[{"resource": "GPU", "used": "1.25h", "remaining": "28.75h", "total": "30.00h", "refreshAt": "2026-11-07T00:00:00"}]'
        with mock.patch.object(kz, "run", return_value=completed(payload)):
            q = kz.quota(kz.get_account("me"))
        self.assertEqual(
            q["gpu"], {"used": 1.25, "remaining": 28.75, "total": 30.0, "refresh_at": "2026-11-07T00:00:00Z"}
        )


class ColabTests(unittest.TestCase):
    def test_session_lines_are_parsed(self) -> None:
        text = (
            "[trainer] https://x.colab.dev | Hardware: A100 | Shape: High-RAM | Variant: GPU | Status: IDLE\n"
            "[?] https://y.colab.dev | Hardware: T4 | Shape: Standard | Variant: GPU\n"
        )
        with mock.patch.object(colab, "run", return_value=completed(text)):
            rows = colab.sessions("main")
        self.assertEqual(
            [(r["name"], r["hardware"], r["shape"], r["status"]) for r in rows],
            [("trainer", "A100", "High-RAM", "IDLE"), (None, "T4", "Standard", None)],
        )

    def test_usage_is_parsed_and_update_banner_ignored(self) -> None:
        text = (
            "[colab] A new version of Colab CLI is available: 0.7.5 (current: 0.7.4)\n"
            "Current balance: 52.07 compute units\nUsage rate: 1.76/hr\nActive assignments: 1\n"
        )
        with mock.patch.object(colab, "run", return_value=completed(text)):
            self.assertEqual(colab.usage("main"), {"balance": 52.07, "rate": 1.76, "active": 1})

    def test_expired_login_is_reported_not_prompted(self) -> None:
        text = "To authorize colab-cli, visit this URL\nEnter the authorization code: EOF when reading a line"
        with mock.patch.object(colab, "run", return_value=completed(text)):
            with self.assertRaisesRegex(colab.ColabError, "colab login acc2"):
                colab.usage("acc2")

    def test_background_calls_refuse_accounts_without_a_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            accounts_dir = Path(tmp) / ".colab_accounts"
            (accounts_dir / "fresh").mkdir(parents=True)
            with (
                mock.patch.object(colab, "ACCOUNTS_DIR", accounts_dir),
                mock.patch.object(colab, "executable", return_value="colab"),
                mock.patch.object(colab.subprocess, "run") as run,
            ):
                with self.assertRaisesRegex(colab.ColabError, "not logged in"):
                    colab.run("fresh", ["usage"])
                run.assert_not_called()

    def test_each_account_gets_its_own_home_and_the_windows_shim(self) -> None:
        env = colab.env_for("work")
        home = str(colab.ACCOUNTS_DIR / "work")
        if os.name == "nt":
            self.assertEqual(env["USERPROFILE"], home)
            self.assertNotIn("HOME", env)
            self.assertTrue(env["PYTHONPATH"].startswith(str(colab.SHIM_DIR)))
        else:
            self.assertEqual(env["HOME"], home)

    def test_shim_ships_in_the_wheel(self) -> None:
        self.assertTrue((colab.SHIM_DIR / "termios.py").is_file())
        self.assertTrue((colab.SHIM_DIR / "tty.py").is_file())
        pyproject = tomlkit.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn("colab_shim/*.py", pyproject["tool"]["setuptools"]["package-data"]["m_gpux.core"])

    def test_auto_picks_most_compute_units(self) -> None:
        rows = [
            {"name": "main", "usage": {"balance": 10.0}, "error": None},
            {"name": "acc2", "usage": {"balance": 90.0}, "error": None},
            {"name": "acc3", "usage": None, "error": "expired"},
        ]
        self.assertEqual(colab.pick_account(rows), "acc2")

    def test_account_names_are_validated(self) -> None:
        for bad in ("", "../x", "a b", "x" * 41):
            with self.assertRaises(colab.ColabError):
                colab.validate_name(bad)
        self.assertEqual(colab.validate_name("work-2"), "work-2")


if __name__ == "__main__":
    unittest.main()
