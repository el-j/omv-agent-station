"""
Tests for agent_station_core.upload_service and the topics_service fix it
depends on (issue #29: Discord/Signal file upload to GitHub parity, plus the
get_bound_project None-thread bug it uncovered in agent_station_core).
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401


class TestUploadCaptionParsing(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.upload_service as upload_service
        self.upload_service = upload_service

    def tearDown(self):
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    def test_no_caption_returns_none_none(self):
        self.assertEqual(self.upload_service.parse_upload_caption(None), (None, None))
        self.assertEqual(self.upload_service.parse_upload_caption("   "), (None, None))

    def test_bare_path_caption(self):
        self.assertEqual(self.upload_service.parse_upload_caption("docs/notes.md"), (None, "docs/notes.md"))

    def test_project_override_syntax(self):
        self.assertEqual(
            self.upload_service.parse_upload_caption("myapi: docs/notes.md"),
            ("myapi", "docs/notes.md"),
        )

    def test_parse_github_owner_repo_https(self):
        self.assertEqual(
            self.upload_service.parse_github_owner_repo("https://github.com/el-j/omv-agent-station.git"),
            ("el-j", "omv-agent-station"),
        )

    def test_parse_github_owner_repo_ssh(self):
        self.assertEqual(
            self.upload_service.parse_github_owner_repo("git@github.com:el-j/omv-agent-station.git"),
            ("el-j", "omv-agent-station"),
        )

    def test_build_compare_url_none_owner_repo(self):
        self.assertIsNone(self.upload_service.build_compare_url(None, "main", "upload/x"))

    def test_build_compare_url(self):
        url = self.upload_service.build_compare_url(("el-j", "omv-agent-station"), "main", "upload/20260101_000000")
        self.assertEqual(url, "https://github.com/el-j/omv-agent-station/compare/main...upload/20260101_000000?expand=1")


class TestRunRepoUpload(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.upload_service as upload_service
        self.upload_service = upload_service

    def tearDown(self):
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    def test_writes_file_and_runs_expected_git_sequence(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmpdir:
                project_dir = Path(tmpdir)

                git_calls = []

                class FakeGitProc:
                    def __init__(self, args):
                        self.args = args
                        self.returncode = 0

                    async def communicate(self):
                        if self.args[:2] == ["rev-parse", "--abbrev-ref"]:
                            return b"main\n", b""
                        if self.args[0] == "remote":
                            return b"https://github.com/el-j/omv-agent-station.git\n", b""
                        return b"", b""

                async def fake_create_subprocess_exec(*args, **kwargs):
                    git_args = list(args[1:])  # drop GIT_BIN
                    git_calls.append(git_args)
                    return FakeGitProc(git_args)

                orig = asyncio.create_subprocess_exec
                asyncio.create_subprocess_exec = fake_create_subprocess_exec
                attached = []
                try:
                    target_path = project_dir / "docs" / "report.pdf"
                    res = await self.upload_service.run_repo_upload(
                        project_dir, target_path, b"%PDF-fake-content",
                        "chore(upload): add docs/report.pdf",
                        on_proc=lambda proc: attached.append(proc),
                    )
                finally:
                    asyncio.create_subprocess_exec = orig

                self.assertTrue(res["success"])
                self.assertTrue(res["branch"].startswith("upload/"))
                self.assertEqual(res["base_branch"], "main")
                self.assertEqual(res["relative_path"], "docs/report.pdf")
                self.assertEqual(res["owner_repo"], ("el-j", "omv-agent-station"))
                self.assertTrue(target_path.exists())
                self.assertEqual(target_path.read_bytes(), b"%PDF-fake-content")
                self.assertTrue(len(attached) > 0)

                self.assertTrue(any(c[:2] == ["checkout", "-B"] for c in git_calls))
                self.assertTrue(any(c[0] == "add" for c in git_calls))
                self.assertTrue(any(c[0] == "commit" for c in git_calls))
                push_call = next(c for c in git_calls if c[0] == "push")
                self.assertEqual(push_call[1:3], ["-u", "origin"])
                self.assertTrue(push_call[3].startswith("upload/"))

        asyncio.run(scenario())

    def test_commit_failure_returns_error_without_pushing(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmpdir:
                project_dir = Path(tmpdir)
                git_calls = []

                class FakeGitProc:
                    def __init__(self, args):
                        self.args = args
                        self.returncode = 1 if args[0] == "commit" else 0

                    async def communicate(self):
                        if self.args[0] == "commit":
                            return b"", b"nothing to commit"
                        return b"", b""

                async def fake_create_subprocess_exec(*args, **kwargs):
                    git_args = list(args[1:])
                    git_calls.append(git_args)
                    return FakeGitProc(git_args)

                orig = asyncio.create_subprocess_exec
                asyncio.create_subprocess_exec = fake_create_subprocess_exec
                try:
                    target_path = project_dir / "notes.md"
                    res = await self.upload_service.run_repo_upload(
                        project_dir, target_path, b"hello", "chore(upload): add notes.md"
                    )
                finally:
                    asyncio.create_subprocess_exec = orig

                self.assertFalse(res["success"])
                self.assertIn("commit failed", res["error"])
                self.assertFalse(any(c[0] == "push" for c in git_calls))

        asyncio.run(scenario())


class TestGetBoundProjectNoneThread(unittest.TestCase):
    """Regression test for a real bug: get_bound_project() used to short-circuit
    to None whenever thread_id was falsy, so a binding stored for a plain
    Discord channel (no Thread) or a Signal sender (no thread concept at all)
    could be set but never read back."""

    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.topics_service as topics_service
        self.topics_service = topics_service
        self._tmpdir = tempfile.TemporaryDirectory()
        self.topics_service.TOPICS_FILE = Path(self._tmpdir.name) / ".agent_topics.json"

    def tearDown(self):
        self._tmpdir.cleanup()
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    def test_binding_with_none_thread_id_is_retrievable(self):
        self.topics_service.set_bound_project("555", None, "myproj")
        self.assertEqual(self.topics_service.get_bound_project("555", None), "myproj")

    def test_unbound_none_thread_id_returns_none(self):
        self.assertIsNone(self.topics_service.get_bound_project("999", None))

    def test_remove_bound_project_with_none_thread_id(self):
        self.topics_service.set_bound_project("555", None, "myproj")
        self.topics_service.remove_bound_project("555", None)
        self.assertIsNone(self.topics_service.get_bound_project("555", None))


if __name__ == "__main__":
    unittest.main()
