"""
Tests for agent_station_core.task_service (issue #19): run_autonomous_task,
run_claude_cli, and run_shell_exec spawn agent subprocesses and had no test
coverage at all. All subprocess creation is mocked -- no real network or
process access.
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401

# run_autonomous_task() unconditionally checks Path("/root/.anthropic/token").exists()
# before ever touching the (mocked) subprocess. On a real developer machine that
# path just doesn't exist, so .exists() returns False -- but on GitHub Actions'
# non-root runner, /root isn't traversable at all, and Python 3.12+ no longer
# swallows PermissionError inside Path.exists() (only FileNotFoundError/
# NotADirectoryError), so it raises instead. That's a real, already-handled
# outcome in production (the function's own try/except catches it and returns
# it as an error) -- but it isn't what these tests are exercising, so pin this
# one lookup to "doesn't exist" everywhere and let every other Path.exists()
# call behave normally.
_real_path_exists = Path.exists


def _fake_path_exists(self, *args, **kwargs):
    if str(self) == "/root/.anthropic/token":
        return False
    return _real_path_exists(self, *args, **kwargs)


class FakeProc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


class TestTaskService(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.task_service as task_service
        self.task_service = task_service
        self._orig_exec = asyncio.create_subprocess_exec
        self._orig_shell = asyncio.create_subprocess_shell
        self._path_exists_patcher = patch.object(Path, "exists", _fake_path_exists)
        self._path_exists_patcher.start()

    def tearDown(self):
        self._path_exists_patcher.stop()
        asyncio.create_subprocess_exec = self._orig_exec
        asyncio.create_subprocess_shell = self._orig_shell
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    # -- run_autonomous_task --------------------------------------------

    def test_run_autonomous_task_success_in_git_repo_checks_out_and_pushes(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmpdir:
                project_dir = Path(tmpdir)
                (project_dir / ".git").mkdir()

                calls = []
                attached = []

                async def fake_exec(*args, **kwargs):
                    calls.append(list(args))
                    if args[0] == self.task_service.AIDER_BIN:
                        return FakeProc(returncode=0, stdout=b"Applied edit to foo.py")
                    return FakeProc(returncode=0)

                asyncio.create_subprocess_exec = fake_exec
                res = await self.task_service.run_autonomous_task(
                    project_dir, "add tests", "task_1", "agent/task_1",
                    on_proc=lambda p: attached.append(p),
                )

                self.assertTrue(res["success"])
                self.assertIn("Applied edit", res["summary"])
                self.assertTrue(any(c[:2] == [self.task_service.GIT_BIN, "checkout"] for c in calls))
                self.assertTrue(any(c[:2] == [self.task_service.GIT_BIN, "push"] for c in calls))
                self.assertEqual(len(attached), 1)

        asyncio.run(scenario())

    def test_run_autonomous_task_non_git_dir_skips_checkout_and_push(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmpdir:
                project_dir = Path(tmpdir)  # no .git

                calls = []

                async def fake_exec(*args, **kwargs):
                    calls.append(list(args))
                    return FakeProc(returncode=0, stdout=b"done")

                asyncio.create_subprocess_exec = fake_exec
                res = await self.task_service.run_autonomous_task(project_dir, "add tests", "task_2", "agent/task_2")

                self.assertTrue(res["success"])
                self.assertFalse(any(self.task_service.GIT_BIN in c for c in calls))

        asyncio.run(scenario())

    def test_run_autonomous_task_reports_failure_on_nonzero_exit(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmpdir:
                project_dir = Path(tmpdir)

                async def fake_exec(*args, **kwargs):
                    return FakeProc(returncode=1, stderr=b"aider crashed")

                asyncio.create_subprocess_exec = fake_exec
                res = await self.task_service.run_autonomous_task(project_dir, "x", "task_3", "agent/task_3")

                self.assertFalse(res["success"])
                self.assertIn("crashed", res["summary"])

        asyncio.run(scenario())

    def test_run_autonomous_task_returns_error_dict_on_exception(self):
        async def scenario():
            async def fake_exec(*args, **kwargs):
                raise OSError("no such binary")

            asyncio.create_subprocess_exec = fake_exec
            res = await self.task_service.run_autonomous_task(Path("/nonexistent"), "x", "task_4", "agent/task_4")

            self.assertFalse(res["success"])
            self.assertIn("no such binary", res["error"])

        asyncio.run(scenario())

    # -- run_claude_cli ---------------------------------------------------

    def test_run_claude_cli_success(self):
        async def scenario():
            async def fake_exec(*args, **kwargs):
                return FakeProc(returncode=0, stdout=b"Here is the fix")

            asyncio.create_subprocess_exec = fake_exec
            res = await self.task_service.run_claude_cli(Path("/tmp"), "fix the bug")

            self.assertTrue(res["success"])
            self.assertEqual(res["output"], "Here is the fix")

        asyncio.run(scenario())

    def test_run_claude_cli_not_installed(self):
        async def scenario():
            async def fake_exec(*args, **kwargs):
                raise FileNotFoundError()

            asyncio.create_subprocess_exec = fake_exec
            res = await self.task_service.run_claude_cli(Path("/tmp"), "fix the bug")

            self.assertFalse(res["success"])
            self.assertIn("not installed", res["error"])

        asyncio.run(scenario())

    def test_run_claude_cli_invokes_on_proc_callback(self):
        async def scenario():
            fake = FakeProc(returncode=0, stdout=b"ok")

            async def fake_exec(*args, **kwargs):
                return fake

            asyncio.create_subprocess_exec = fake_exec
            attached = []
            await self.task_service.run_claude_cli(Path("/tmp"), "x", on_proc=lambda p: attached.append(p))

            self.assertEqual(attached, [fake])

        asyncio.run(scenario())

    # -- run_shell_exec ----------------------------------------------------

    def test_run_shell_exec_success(self):
        async def scenario():
            async def fake_shell(*args, **kwargs):
                return FakeProc(returncode=0, stdout=b"hello\n")

            asyncio.create_subprocess_shell = fake_shell
            res = await self.task_service.run_shell_exec("echo hello")

            self.assertTrue(res["success"])
            self.assertIn("hello", res["output"])

        asyncio.run(scenario())

    def test_run_shell_exec_nonzero_exit_still_returns_output(self):
        async def scenario():
            async def fake_shell(*args, **kwargs):
                return FakeProc(returncode=1, stderr=b"command not found")

            asyncio.create_subprocess_shell = fake_shell
            res = await self.task_service.run_shell_exec("bogus-command")

            self.assertFalse(res["success"])
            self.assertIn("command not found", res["output"])

        asyncio.run(scenario())

    def test_run_shell_exec_empty_output_returns_placeholder(self):
        async def scenario():
            async def fake_shell(*args, **kwargs):
                return FakeProc(returncode=0, stdout=b"", stderr=b"")

            asyncio.create_subprocess_shell = fake_shell
            res = await self.task_service.run_shell_exec("true")

            self.assertEqual(res["output"], "(No output)")

        asyncio.run(scenario())

    def test_run_shell_exec_returns_error_dict_on_exception(self):
        async def scenario():
            async def fake_shell(*args, **kwargs):
                raise RuntimeError("boom")

            asyncio.create_subprocess_shell = fake_shell
            res = await self.task_service.run_shell_exec("anything")

            self.assertFalse(res["success"])
            self.assertIn("boom", res["error"])

        asyncio.run(scenario())

    def test_run_claude_cli_returns_error_dict_on_unexpected_exception(self):
        async def scenario():
            async def fake_exec(*args, **kwargs):
                raise RuntimeError("kernel said no")

            asyncio.create_subprocess_exec = fake_exec
            res = await self.task_service.run_claude_cli(Path("/tmp"), "hi")

            self.assertFalse(res["success"])
            self.assertIn("kernel said no", res["error"])

        asyncio.run(scenario())

    # -- agent credential passthrough ------------------------------------

    def test_autonomous_task_forwards_mounted_anthropic_token(self):
        """The OMV plugin mounts the Claude credential at /root/.anthropic/token;
        if it stops being forwarded to aider, every agent run silently loses
        access to the Anthropic-backed models."""
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "token"
            token_file.write_text("sk-ant-test\n")

            def token_exists(self, *args, **kwargs):
                if str(self) == "/root/.anthropic/token":
                    return True
                return _real_path_exists(self, *args, **kwargs)

            def token_read(self, *args, **kwargs):
                if str(self) == "/root/.anthropic/token":
                    return "sk-ant-test\n"
                return token_file.read_text()

            async def scenario():
                calls = []

                async def fake_exec(*args, **kwargs):
                    calls.append(list(args))
                    return FakeProc(returncode=0, stdout=b"ok")

                asyncio.create_subprocess_exec = fake_exec
                await self.task_service.run_autonomous_task(
                    Path(tmpdir), "x", "task_tok", "agent/task_tok")
                aider_call = next(c for c in calls if c[0] == self.task_service.AIDER_BIN)
                self.assertIn("--anthropic-api-key", aider_call)
                self.assertEqual(aider_call[aider_call.index("--anthropic-api-key") + 1], "sk-ant-test")

            with patch.object(Path, "exists", token_exists), \
                    patch.object(Path, "read_text", token_read):
                asyncio.run(scenario())

    # -- telemetry --------------------------------------------------------

    def test_get_ram_usage_parses_proc_meminfo(self):
        import builtins
        meminfo = "MemTotal:       2048000 kB\nMemFree:  100000 kB\nMemAvailable:   1024000 kB\n"
        real_open = builtins.open

        def fake_open(path, *args, **kwargs):
            if path == "/proc/meminfo":
                import io
                return io.StringIO(meminfo)
            return real_open(path, *args, **kwargs)

        with patch.object(builtins, "open", fake_open):
            self.assertEqual(self.task_service.get_ram_usage(), "1000 MB used of 2000 MB (50%)")

    def test_get_ram_usage_returns_na_when_proc_is_unavailable(self):
        import builtins
        real_open = builtins.open

        def fake_open(path, *args, **kwargs):
            if path == "/proc/meminfo":
                raise FileNotFoundError(path)
            return real_open(path, *args, **kwargs)

        with patch.object(builtins, "open", fake_open):
            self.assertEqual(self.task_service.get_ram_usage(), "N/A")

    def test_get_system_status_collects_all_four_metrics(self):
        outputs = {
            self.task_service.TMUX_BIN: "agent: 1 windows",
            self.task_service.UPTIME_BIN: "up 3 days,  1 user",
            self.task_service.DF_BIN: "Filesystem Size Used Avail Use%\n/dev/sda1 100G 50G 50G 50% /data",
        }

        def fake_check_output(args, **kwargs):
            return outputs[args[0]]

        with patch.object(self.task_service.subprocess, "check_output", fake_check_output):
            status = self.task_service.get_system_status()

        self.assertEqual(status["tmux"], "agent: 1 windows")
        self.assertEqual(status["uptime"], "up 3 days,  1 user")
        self.assertIn("/dev/sda1", status["disk"])
        self.assertIn(status["ram"], (status["ram"],))

    def test_get_system_status_degrades_gracefully_when_binaries_missing(self):
        def fake_check_output(args, **kwargs):
            raise FileNotFoundError(args[0])

        with patch.object(self.task_service.subprocess, "check_output", fake_check_output):
            status = self.task_service.get_system_status()

        self.assertEqual(status["tmux"], "No active tmux sessions.")
        self.assertEqual(status["uptime"], "N/A")
        self.assertEqual(status["disk"], "N/A")


if __name__ == "__main__":
    unittest.main()
