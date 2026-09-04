"""
Tests for the Signal bot's file-upload-to-GitHub feature (issue #29) and the
newly wired /bind + /unbind commands (issue #16) it depends on for project
resolution.

Since issue #22 split signal_bot.py into handlers/*.py modules, WORKSPACE and
send_signal_message must be patched on the specific submodule that owns each
reference (see tests/test_signal_handlers.py's module docstring for why).
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs


class TestSignalBindUnbind(unittest.TestCase):
    def setUp(self):
        stubs.purge_bot_modules("core", "handlers", "signal_bot")
        sys.path.insert(0, str(ROOT_DIR / "signal-agent-bot"))
        import signal_bot
        import core.security as core_security
        import handlers.git_ops as git_ops
        import handlers.topics as topics
        import agent_station_core.topics_service as topics_service
        self.signal_bot = signal_bot
        self.git_ops = git_ops
        self.topics = topics
        self.topics_service = topics_service
        core_security.SIGNAL_ALLOWED_NUMBER = ""

        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.project_dir = self.workspace / "myproj"
        (self.project_dir / ".git").mkdir(parents=True)
        for mod in (self.git_ops, self.topics):
            mod.WORKSPACE = self.workspace
        self.topics_service.WORKSPACE = self.workspace
        self.topics_service.TOPICS_FILE = self.workspace / ".agent_topics.json"

        self.sent = []

        async def fake_send(recipient, message):
            self.sent.append((recipient, message))

        self._send_modules = [signal_bot, git_ops, topics]
        self._orig_send = {mod: mod.send_signal_message for mod in self._send_modules}
        for mod in self._send_modules:
            mod.send_signal_message = fake_send

    def tearDown(self):
        for mod, orig in self._orig_send.items():
            mod.send_signal_message = orig
        self._tmpdir.cleanup()
        if str(ROOT_DIR / "signal-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "signal-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "signal_bot")

    def test_bind_then_status_shows_bound_project(self):
        async def scenario():
            sender = "+15550001111"
            await self.signal_bot.handle_signal_command(sender, "/bind myproj")
            self.assertTrue(any("Bound" in m for _, m in self.sent))

            self.sent.clear()
            await self.signal_bot.handle_signal_command(sender, "/bind")
            self.assertTrue(any("myproj" in m for _, m in self.sent))

        asyncio.run(scenario())

    def test_bind_unknown_project_rejected(self):
        async def scenario():
            sender = "+15550001112"
            await self.signal_bot.handle_signal_command(sender, "/bind doesnotexist")
            self.assertTrue(any("not found" in m for _, m in self.sent))

        asyncio.run(scenario())

    def test_unbind_clears_binding(self):
        async def scenario():
            sender = "+15550001114"
            await self.signal_bot.handle_signal_command(sender, "/bind myproj")
            self.assertEqual(self.topics_service.get_bound_project(sender, None), "myproj")
            await self.signal_bot.handle_signal_command(sender, "/unbind")
            self.assertIsNone(self.topics_service.get_bound_project(sender, None))

        asyncio.run(scenario())

    def test_pull_falls_back_to_bound_project(self):
        async def scenario():
            sender = "+15550001115"
            await self.signal_bot.handle_signal_command(sender, "/bind myproj")
            self.sent.clear()

            async def fake_git_pull_repo(proj):
                return {"success": True, "output": f"pulled {proj}"}

            orig = self.git_ops.git_pull_repo
            self.git_ops.git_pull_repo = fake_git_pull_repo
            try:
                await self.signal_bot.handle_signal_command(sender, "/pull")
                self.assertTrue(any("myproj" in m for _, m in self.sent))
            finally:
                self.git_ops.git_pull_repo = orig

        asyncio.run(scenario())


class TestSignalFileUpload(unittest.TestCase):
    def setUp(self):
        stubs.purge_bot_modules("core", "handlers", "signal_bot")
        sys.path.insert(0, str(ROOT_DIR / "signal-agent-bot"))
        import signal_bot
        import core.security as core_security
        import handlers.upload as upload
        import agent_station_core.task_registry as task_registry
        import agent_station_core.topics_service as topics_service
        self.signal_bot = signal_bot
        self.upload = upload
        self.task_registry = task_registry
        self.topics_service = topics_service
        self.task_registry._active.clear()
        core_security.SIGNAL_ALLOWED_NUMBER = ""

        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.project_dir = self.workspace / "myproj"
        (self.project_dir / ".git").mkdir(parents=True)
        self.upload.WORKSPACE = self.workspace
        self.topics_service.WORKSPACE = self.workspace
        self.topics_service.TOPICS_FILE = self.workspace / ".agent_topics.json"

        self.sent = []

        async def fake_send(recipient, message):
            self.sent.append((recipient, message))

        self._orig_send = upload.send_signal_message
        upload.send_signal_message = fake_send

    def tearDown(self):
        self.upload.send_signal_message = self._orig_send
        self.task_registry._active.clear()
        self._tmpdir.cleanup()
        if str(ROOT_DIR / "signal-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "signal-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "signal_bot")

    def test_rejects_when_no_project_bound(self):
        async def scenario():
            sender = "+15550002001"
            await self.upload.handle_signal_upload(sender, {"id": "att-1", "filename": "x.txt", "size": 10}, None)
            self.assertTrue(any("No project bound" in m for _, m in self.sent))
            self.assertIsNone(self.task_registry.get(sender))

        asyncio.run(scenario())

    def test_rejects_oversized_attachment(self):
        async def scenario():
            sender = "+15550002002"
            self.topics_service.set_bound_project(sender, None, "myproj")
            big_size = self.upload.MAX_UPLOAD_BYTES + 1
            await self.upload.handle_signal_upload(sender, {"id": "att-1", "filename": "x.txt", "size": big_size}, None)
            self.assertTrue(any("max upload size" in m for _, m in self.sent))
            self.assertIsNone(self.task_registry.get(sender))

        asyncio.run(scenario())

    def test_rejects_path_traversal_caption(self):
        async def scenario():
            sender = "+15550002003"
            self.topics_service.set_bound_project(sender, None, "myproj")
            await self.upload.handle_signal_upload(
                sender, {"id": "att-1", "filename": "x.txt", "size": 10}, "../../etc/passwd"
            )
            self.assertTrue(any("Invalid target path" in m for _, m in self.sent))
            self.assertIsNone(self.task_registry.get(sender))

        asyncio.run(scenario())

    def test_full_upload_flow_downloads_commits_and_pushes(self):
        async def scenario():
            sender = "+15550002004"
            self.topics_service.set_bound_project(sender, None, "myproj")

            async def fake_download(attachment_id):
                self.assertEqual(attachment_id, "att-42")
                return b"hello world"

            orig_download = self.upload.download_signal_attachment
            self.upload.download_signal_attachment = fake_download

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
                git_args = list(args[1:])
                git_calls.append(git_args)
                return FakeGitProc(git_args)

            orig_exec = asyncio.create_subprocess_exec
            asyncio.create_subprocess_exec = fake_create_subprocess_exec
            try:
                await asyncio.wait_for(
                    self.upload.handle_signal_upload(
                        sender, {"id": "att-42", "filename": "notes.txt", "size": 11}, "docs/notes.txt"
                    ),
                    timeout=1.0,
                )
                for _ in range(100):
                    if self.task_registry.get(sender) is None:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("upload task never finished")

                written = self.project_dir / "docs" / "notes.txt"
                self.assertTrue(written.exists())
                self.assertEqual(written.read_bytes(), b"hello world")
                self.assertTrue(any(c[:2] == ["checkout", "-B"] for c in git_calls))
                self.assertTrue(any("File Uploaded" in m for _, m in self.sent))
            finally:
                asyncio.create_subprocess_exec = orig_exec
                self.upload.download_signal_attachment = orig_download

        asyncio.run(scenario())

    def test_rejects_overlapping_upload_from_same_sender(self):
        async def scenario():
            sender = "+15550002005"
            self.topics_service.set_bound_project(sender, None, "myproj")
            t = asyncio.create_task(asyncio.sleep(10))
            self.task_registry.start(sender, label="existing", asyncio_task=t)
            try:
                await self.upload.handle_signal_upload(
                    sender, {"id": "att-1", "filename": "x.txt", "size": 10}, None
                )
                self.assertTrue(any("already running" in m for _, m in self.sent))
            finally:
                await self.task_registry.cancel(sender)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
