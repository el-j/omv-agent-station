"""
Black-box tests for the Telegram bot's /cancel command and its task registry.

These guard the specific regression this feature fixes: python-telegram-bot
processes updates sequentially by default, so a handler that `await`s a
subprocess directly (the old /exec and /claude behavior) freezes the bot for
every other command -- including /cancel itself -- until that subprocess
exits. /exec, /task, and /claude must therefore launch their subprocess in a
background asyncio task and register it, so /cancel (and any other command)
keeps working immediately.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401


class DummyStatusMessage:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)


class DummyMessage:
    def __init__(self, thread_id=None):
        self.message_thread_id = thread_id
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return DummyStatusMessage()


class DummyChat:
    def __init__(self, cid):
        self.id = cid


class DummyUser:
    def __init__(self, uid):
        self.id = uid


class DummyUpdate:
    def __init__(self, cid, thread_id=None, uid="1"):
        self.effective_chat = DummyChat(cid)
        self.effective_message = DummyMessage(thread_id)
        self.effective_user = DummyUser(uid)


class DummyContext:
    def __init__(self, args=None):
        self.args = args or []


class TestTaskRegistry(unittest.TestCase):
    """Pure unit coverage of the chat-scoped active task registry."""

    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        import core.task_registry as task_registry
        self.task_registry = task_registry
        self.task_registry._active.clear()

    def tearDown(self):
        self.task_registry._active.clear()
        if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))

    def test_cancel_returns_none_when_nothing_running(self):
        result = asyncio.run(self.task_registry.cancel(1, None))
        self.assertIsNone(result)

    def test_cancel_kills_attached_proc_and_cancels_task(self):
        async def scenario():
            async def slow():
                await asyncio.sleep(10)

            t = asyncio.create_task(slow())
            self.task_registry.start(1, None, label="exec: sleep 10", asyncio_task=t)

            fake_proc = MagicMock()
            fake_proc.returncode = None
            self.task_registry.attach_proc(1, None, fake_proc)

            label = await self.task_registry.cancel(1, None)
            self.assertEqual(label, "exec: sleep 10")
            fake_proc.kill.assert_called_once()
            self.assertIsNone(self.task_registry.get(1, None))

            with self.assertRaises(asyncio.CancelledError):
                await t

        asyncio.run(scenario())

    def test_scopes_are_isolated_per_chat_and_thread(self):
        async def scenario():
            t1 = asyncio.create_task(asyncio.sleep(10))
            t2 = asyncio.create_task(asyncio.sleep(10))
            self.task_registry.start(1, None, label="chat-scope", asyncio_task=t1)
            self.task_registry.start(1, 42, label="topic-scope", asyncio_task=t2)

            self.assertEqual(self.task_registry.get(1, None).label, "chat-scope")
            self.assertEqual(self.task_registry.get(1, 42).label, "topic-scope")

            label = await self.task_registry.cancel(1, 42)
            self.assertEqual(label, "topic-scope")
            self.assertIsNotNone(self.task_registry.get(1, None))
            self.assertIsNone(self.task_registry.get(1, 42))

            await self.task_registry.cancel(1, None)

        asyncio.run(scenario())


class TestCancelCommandHandler(unittest.TestCase):
    """End-to-end handler behavior through handlers.system."""

    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        import handlers.system as system
        import core.task_registry as task_registry
        self.system = system
        self.task_registry = task_registry
        self.task_registry._active.clear()

    def tearDown(self):
        self.task_registry._active.clear()
        if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))

    def test_cancel_with_nothing_running_replies_informatively(self):
        async def scenario():
            update = DummyUpdate(cid=555)
            await self.system.cancel_cmd(update, DummyContext())
            self.assertTrue(any("Nothing is currently running" in r for r in update.effective_message.replies))

        asyncio.run(scenario())

    def test_exec_launches_in_background_and_cancel_stops_it(self):
        """Reproduces the reported bug: launch a long /exec, then prove /cancel
        (a "next command") is served immediately and actually stops the subprocess,
        instead of the bot hanging until the shell command finishes on its own."""

        async def scenario():
            update = DummyUpdate(cid=777)
            ctx = DummyContext(args=["sleep", "999"])

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
                # exec_cmd must return promptly even though the subprocess never
                # finishes on its own -- proving it isn't awaited inline.
                await asyncio.wait_for(self.system.exec_cmd(update, ctx), timeout=1.0)

                # Wait until the background task has actually spawned & attached its subprocess.
                for _ in range(100):
                    entry = self.task_registry.get(777, None)
                    if entry and entry.proc is not None:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("background exec task never attached its subprocess in time")

                # A brand new command in the same chat must be served right away.
                cancel_update = DummyUpdate(cid=777)
                await asyncio.wait_for(self.system.cancel_cmd(cancel_update, DummyContext()), timeout=1.0)

                await asyncio.sleep(0.05)

                self.assertTrue(fake_proc.killed, "expected /cancel to kill the running subprocess")
                self.assertIsNone(self.task_registry.get(777, None))
            finally:
                asyncio.create_subprocess_shell = orig
                release.set()

        asyncio.run(scenario())

    def test_exec_rejects_overlapping_command_in_same_scope(self):
        async def scenario():
            update = DummyUpdate(cid=888)
            ctx = DummyContext(args=["sleep", "999"])

            async def fake_create_subprocess_shell(*args, **kwargs):
                fake = MagicMock()
                fake.returncode = None
                fake.communicate = MagicMock(return_value=asyncio.sleep(10))
                return fake

            orig = asyncio.create_subprocess_shell
            asyncio.create_subprocess_shell = fake_create_subprocess_shell
            try:
                await asyncio.wait_for(self.system.exec_cmd(update, ctx), timeout=1.0)

                second_update = DummyUpdate(cid=888)
                await asyncio.wait_for(self.system.exec_cmd(second_update, DummyContext(args=["ls"])), timeout=1.0)

                self.assertTrue(any("already running" in r for r in second_update.effective_message.replies))
            finally:
                asyncio.create_subprocess_shell = orig
                await self.task_registry.cancel(888, None)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
