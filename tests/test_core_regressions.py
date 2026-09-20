from __future__ import annotations

import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from m_gpux.core.profiles import activate_profile, select_profile
from m_gpux.core.state import _write_json
from m_gpux.plugins.dev import devbox


class StateWriteTests(unittest.TestCase):
    def test_json_write_is_complete_and_leaves_no_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"
            _write_json(target, {"b": 2, "a": [1, 2, 3]})

            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"a": [1, 2, 3], "b": 2})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])


class ProfileActivationTests(unittest.TestCase):
    @mock.patch("m_gpux.core.profiles.load_profiles", return_value=[("Tool1", False)])
    def test_modal_profile_env_resolves_configured_case(self, _profiles: mock.Mock) -> None:
        with mock.patch.dict(os.environ, {"MODAL_PROFILE": "tool1"}):
            self.assertEqual(select_profile(), "Tool1")
            self.assertEqual(os.environ["MODAL_PROFILE"], "Tool1")

    @mock.patch("m_gpux.core.profiles.subprocess.run")
    def test_failed_activation_is_reported_to_caller(self, run: mock.Mock) -> None:
        run.return_value = SimpleNamespace(returncode=1, stderr="bad profile", stdout="")
        self.assertFalse(activate_profile("missing"))
        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    @mock.patch("m_gpux.core.profiles.subprocess.run", side_effect=FileNotFoundError("modal"))
    def test_missing_modal_executable_is_reported_to_caller(self, _run: mock.Mock) -> None:
        self.assertFalse(activate_profile("account"))


class DevboxSyncTests(unittest.TestCase):
    def test_pack_dir_excludes_ignored_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.txt").write_text("keep", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "secret").write_text("skip", encoding="utf-8")

            data, count = devbox.pack_dir(tmp, [".git"])
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
                names = {member.name for member in archive.getmembers()}

            self.assertEqual(count, 1)
            self.assertEqual(names, {"keep.txt"})

    def test_pull_never_extracts_outside_destination(self) -> None:
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            good = b"ok"
            good_info = tarfile.TarInfo("good.txt")
            good_info.size = len(good)
            archive.addfile(good_info, io.BytesIO(good))

            escaped = b"no"
            escaped_info = tarfile.TarInfo("../escaped.txt")
            escaped_info.size = len(escaped)
            archive.addfile(escaped_info, io.BytesIO(escaped))

            link = tarfile.TarInfo("link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../escaped.txt"
            archive.addfile(link)

        class Process:
            returncode = 0
            stderr = io.StringIO("")

            def wait(self):
                return 0

        class Filesystem:
            @staticmethod
            def read_bytes(_path: str) -> bytes:
                return payload.getvalue()

        class Sandbox:
            filesystem = Filesystem()

            @staticmethod
            def exec(*_args):
                return Process()

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "workspace"
            dest.mkdir()
            count = devbox.pull(Sandbox(), str(dest), [])

            self.assertEqual(count, 1)
            self.assertEqual((dest / "good.txt").read_text(encoding="utf-8"), "ok")
            self.assertFalse((Path(tmp) / "escaped.txt").exists())
            self.assertFalse((dest / "link").exists())


if __name__ == "__main__":
    unittest.main()
