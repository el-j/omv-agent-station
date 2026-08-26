"""
Tests for the Discord bot's /cancel command and task_registry integration
(issue #12: Discord/Signal /cancel parity with Telegram).

discord.py schedules each incoming event as its own asyncio.Task (verified
against discord.py's Client._schedule_event), so unlike the Telegram bot,
Discord was never at risk of a long /task run freezing the whole bot. The
real gap this closes is different: with no registry, two overlapping
/task invocations in the same channel could race on the same git working
directory (concurrent checkout -B/add/commit/push), and a stuck run had no
way to be stopped short of restarting the bot.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401


class DummyReplyMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, content, **kwargs):
        self.edits.append(content)


class DummyChannel:
    def __init__(self, cid):
        self.id = cid


class DummyAuthor:
    def __init__(self, uid):
        self.id = uid


class DummyContext:
    def __init__(self, channel_id, uid="1"):
        self.channel = DummyChannel(channel_id)
        self.author = DummyAuthor(uid)
        self.message = MagicMock(id=999)
        self.replies = []

    async def reply(self, content=None, **kwargs):
        self.replies.append(content)
        return DummyReplyMessage()


class TestDiscordCancelCommand(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "discord-agent-bot"))
        import discord_bot
        import agent_station_core.task_registry as task_registry
        self.discord_bot = discord_bot
        self.task_registry = task_registry
        self.task_registry._active.clear()
        self.discord_bot.ALLOWED_USER_ID = None

    def tearDown(self):
        self.task_registry._active.clear()
        if str(ROOT_DIR / "discord-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "discord-agent-bot"))

    def test_cancel_with_nothing_running_replies_informatively(self):
        async def scenario():
            ctx = DummyContext(channel_id=111)
            await self.discord_bot.cancel_cmd(ctx)
            self.assertTrue(any("Nothing is currently running" in r for r in ctx.replies))

        asyncio.run(scenario())

    def test_exec_launches_in_background_and_cancel_stops_it(self):
        async def scenario():
            ctx = DummyContext(channel_id=222)

            release = asyncio.Event()

            class FakeProc:
                def __init__(self):
                    self.returncode = None
                    self.killed = False

                def kill(self):
                    self.killed = True
                    self.returncode = -9

                async def communicate(self):
                    await release.wait()
                    return b"", b""

            fake_proc = FakeProc()

            async def fake_create_subprocess_shell(*args, **kwargs):
                return fake_proc

            orig = asyncio.create_subprocess_shell
            asyncio.create_subprocess_shell = fake_create_subprocess_shell
            try:
                await asyncio.wait_for(self.discord_bot.exec_cmd(ctx, shell_cmd="sleep 999"), timeout=1.0)

                for _ in range(100):
                    entry = self.task_registry.get("222", None)
                    if entry and entry.proc is not None:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("background exec task never attached its subprocess in time")

                cancel_ctx = DummyContext(channel_id=222)
                await asyncio.wait_for(self.discord_bot.cancel_cmd(cancel_ctx), timeout=1.0)
                await asyncio.sleep(0.05)

                self.assertTrue(fake_proc.killed)
                self.assertIsNone(self.task_registry.get("222", None))
            finally:
                asyncio.create_subprocess_shell = orig
                release.set()

        asyncio.run(scenario())

    def test_exec_rejects_overlapping_command_in_same_channel(self):
        async def scenario():
            ctx = DummyContext(channel_id=333)

            async def fake_create_subprocess_shell(*args, **kwargs):
                fake = MagicMock()
                fake.returncode = None

                async def never_returns():
                    await asyncio.sleep(10)
                    return b"", b""

                fake.communicate = AsyncMock(side_effect=never_returns)
                return fake

            orig = asyncio.create_subprocess_shell
            asyncio.create_subprocess_shell = fake_create_subprocess_shell
            try:
                await asyncio.wait_for(self.discord_bot.exec_cmd(ctx, shell_cmd="sleep 999"), timeout=1.0)

                second_ctx = DummyContext(channel_id=333)
                await asyncio.wait_for(self.discord_bot.exec_cmd(second_ctx, shell_cmd="ls"), timeout=1.0)

                self.assertTrue(any("already running" in r for r in second_ctx.replies))
            finally:
                asyncio.create_subprocess_shell = orig
                await self.task_registry.cancel("333", None)

        asyncio.run(scenario())

    def test_different_channels_are_isolated(self):
        async def scenario():
            t1 = asyncio.create_task(asyncio.sleep(10))
            self.task_registry.start("444", None, label="chan-a", asyncio_task=t1)

            ctx_b = DummyContext(channel_id=555)
            await self.discord_bot.cancel_cmd(ctx_b)
            self.assertTrue(any("Nothing is currently running" in r for r in ctx_b.replies))

            self.assertIsNotNone(self.task_registry.get("444", None))
            await self.task_registry.cancel("444", None)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
