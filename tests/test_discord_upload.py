"""
Tests for the Discord bot's file-upload-to-GitHub feature (issue #29:
Discord/Signal parity with Telegram's handlers/upload.py) and the /bind
plain-channel fix it depends on.
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401


class DummyReplyMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, content=None, **kwargs):
        self.edits.append(content)


class DummyAttachment:
    def __init__(self, filename="report.pdf", size=1024, content=b"%PDF-fake-content"):
        self.filename = filename
        self.size = size
        self._content = content
        self.read = AsyncMock(return_value=content)


class DummyChannel:
    def __init__(self, cid):
        self.id = cid


class DummyAuthor:
    def __init__(self, uid="1", bot=False):
        self.id = uid
        self.bot = bot


class DummyMessage:
    def __init__(self, channel_id, content="", attachments=None, uid="1"):
        self.channel = DummyChannel(channel_id)
        self.author = DummyAuthor(uid)
        self.content = content
        self.attachments = attachments or []
        self.replies = []

    async def reply(self, content=None, **kwargs):
        self.replies.append(content)
        return DummyReplyMessage()


class TestDiscordFileUpload(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "discord-agent-bot"))
        import discord_bot
        import agent_station_core.task_registry as task_registry
        import agent_station_core.topics_service as topics_service
        self.discord_bot = discord_bot
        self.task_registry = task_registry
        self.topics_service = topics_service
        self.task_registry._active.clear()
        self.discord_bot.ALLOWED_USER_ID = None

        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.project_dir = self.workspace / "myproj"
        (self.project_dir / ".git").mkdir(parents=True)
        self.discord_bot.WORKSPACE = self.workspace
        self.topics_service.WORKSPACE = self.workspace
        self.topics_service.TOPICS_FILE = self.workspace / ".agent_topics.json"

    def tearDown(self):
        self.task_registry._active.clear()
        self._tmpdir.cleanup()
        if str(ROOT_DIR / "discord-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "discord-agent-bot"))

    def test_rejects_when_no_project_bound(self):
        async def scenario():
            msg = DummyMessage(channel_id=111, attachments=[DummyAttachment()])
            await self.discord_bot.handle_discord_upload(msg)
            self.assertTrue(any("No project bound" in r for r in msg.replies))
            self.assertIsNone(self.task_registry.get("111", None))

        asyncio.run(scenario())

    def test_bind_then_upload_uses_bound_project_on_plain_channel(self):
        """Regression coverage: /bind on a plain (non-Thread) Discord channel
        used to be unrecoverable because get_bound_project() short-circuited
        on a falsy thread_id -- this exercises the real bind_cmd -> upload path."""

        async def scenario():
            class BindCtx:
                def __init__(self, channel_id):
                    self.channel = DummyChannel(channel_id)
                    self.author = DummyAuthor()
                    self.replies = []

                async def reply(self, content=None, **kwargs):
                    self.replies.append(content)

            ctx = BindCtx(channel_id=222)
            await self.discord_bot.bind_cmd(ctx, project_name="myproj")
            self.assertTrue(any("bound to project" in r for r in ctx.replies))

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

            orig = asyncio.create_subprocess_exec
            asyncio.create_subprocess_exec = fake_create_subprocess_exec
            try:
                msg = DummyMessage(channel_id=222, content="docs/report.pdf", attachments=[DummyAttachment()])
                await asyncio.wait_for(self.discord_bot.handle_discord_upload(msg), timeout=1.0)

                for _ in range(100):
                    if self.task_registry.get("222", None) is None:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("upload task never finished")

                written = self.project_dir / "docs" / "report.pdf"
                self.assertTrue(written.exists())
                self.assertEqual(written.read_bytes(), b"%PDF-fake-content")
                self.assertTrue(any(c[:2] == ["checkout", "-B"] for c in git_calls))
            finally:
                asyncio.create_subprocess_exec = orig

        asyncio.run(scenario())

    def test_rejects_oversized_attachment(self):
        async def scenario():
            self.topics_service.set_bound_project("333", None, "myproj")
            msg = DummyMessage(channel_id=333, attachments=[DummyAttachment(size=self.discord_bot.MAX_UPLOAD_BYTES + 1)])
            await self.discord_bot.handle_discord_upload(msg)
            self.assertTrue(any("max upload size" in r for r in msg.replies))
            self.assertIsNone(self.task_registry.get("333", None))

        asyncio.run(scenario())

    def test_rejects_path_traversal_caption(self):
        async def scenario():
            self.topics_service.set_bound_project("444", None, "myproj")
            msg = DummyMessage(channel_id=444, content="../../etc/passwd", attachments=[DummyAttachment()])
            await self.discord_bot.handle_discord_upload(msg)
            self.assertTrue(any("Invalid target path" in r for r in msg.replies))
            self.assertIsNone(self.task_registry.get("444", None))

        asyncio.run(scenario())

    def test_rejects_overlapping_upload_in_same_channel(self):
        async def scenario():
            self.topics_service.set_bound_project("555", None, "myproj")
            t = asyncio.create_task(asyncio.sleep(10))
            self.task_registry.start("555", None, label="existing", asyncio_task=t)
            try:
                msg = DummyMessage(channel_id=555, attachments=[DummyAttachment()])
                await self.discord_bot.handle_discord_upload(msg)
                self.assertTrue(any("already running" in r for r in msg.replies))
            finally:
                await self.task_registry.cancel("555", None)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
