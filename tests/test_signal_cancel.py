"""
Tests for the Signal bot's /cancel command and task_registry integration
(issue #12: Discord/Signal /cancel parity with Telegram).

Signal's WS listener already dispatches each incoming message via its own
asyncio.create_task (signal_bot.py's signal_event_listener), so -- like
Discord -- it was never at risk of a long /task run freezing the whole bot.
What was missing: no way to cancel a stuck run, and no guard against a
second /task from the same sender racing the first one on the same git
working directory.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs


class TestSignalCancelCommand(unittest.TestCase):
    def setUp(self):
        stubs.purge_bot_modules("core", "handlers", "signal_bot")
        sys.path.insert(0, str(ROOT_DIR / "signal-agent-bot"))
        import signal_bot
        import core.security as core_security
        import handlers.system as system
        import agent_station_core.task_registry as task_registry
        self.signal_bot = signal_bot
        self.system = system
        self.task_registry = task_registry
        self.task_registry._active.clear()
        core_security.SIGNAL_ALLOWED_NUMBER = ""

        self.sent = []

        async def fake_send(recipient, message):
            self.sent.append((recipient, message))

        # send_signal_message is imported independently into signal_bot.py
        # (for the unauthorized-access reply) and handlers/system.py (for
        # /cancel and /exec) -- patch both.
        self._send_modules = [signal_bot, system]
        self._orig_send = {mod: mod.send_signal_message for mod in self._send_modules}
        for mod in self._send_modules:
            mod.send_signal_message = fake_send

    def tearDown(self):
        for mod, orig in self._orig_send.items():
            mod.send_signal_message = orig
        self.task_registry._active.clear()
        if str(ROOT_DIR / "signal-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "signal-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "signal_bot")

    def test_cancel_with_nothing_running_replies_informatively(self):
        async def scenario():
            await self.signal_bot.handle_signal_command("+15550000001", "/cancel")
            self.assertTrue(any("Nothing is currently running" in m for _, m in self.sent))

        asyncio.run(scenario())

    def test_exec_launches_in_background_and_cancel_stops_it(self):
        async def scenario():
            sender = "+15550000002"
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
                await asyncio.wait_for(self.signal_bot.handle_signal_command(sender, "/exec sleep 999"), timeout=1.0)

                for _ in range(100):
                    entry = self.task_registry.get(sender)
                    if entry and entry.proc is not None:
                        break
                    await asyncio.sleep(0.01)
                else:
                    self.fail("background exec task never attached its subprocess in time")

                await asyncio.wait_for(self.signal_bot.handle_signal_command(sender, "/cancel"), timeout=1.0)
                await asyncio.sleep(0.05)

                self.assertTrue(fake_proc.killed)
                self.assertIsNone(self.task_registry.get(sender))
            finally:
                asyncio.create_subprocess_shell = orig
                release.set()

        asyncio.run(scenario())

    def test_exec_rejects_overlapping_command_from_same_sender(self):
        async def scenario():
            sender = "+15550000003"

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
                await asyncio.wait_for(self.signal_bot.handle_signal_command(sender, "/exec sleep 999"), timeout=1.0)
                await asyncio.wait_for(self.signal_bot.handle_signal_command(sender, "/exec ls"), timeout=1.0)

                self.assertTrue(any("already running" in m for _, m in self.sent))
            finally:
                asyncio.create_subprocess_shell = orig
                await self.task_registry.cancel(sender)

        asyncio.run(scenario())

    def test_different_senders_are_isolated(self):
        async def scenario():
            t1 = asyncio.create_task(asyncio.sleep(10))
            self.task_registry.start("+15550000004", label="sender-a", asyncio_task=t1)

            await self.signal_bot.handle_signal_command("+15550000005", "/cancel")
            self.assertTrue(any("Nothing is currently running" in m for _, m in self.sent))

            self.assertIsNotNone(self.task_registry.get("+15550000004"))
            await self.task_registry.cancel("+15550000004")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
