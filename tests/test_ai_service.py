"""
Tests for agent_station_core.ai_service.list_ai_models() (issue #17):
callers must be able to tell a live LiteLLM gateway read apart from the
hardcoded fallback list returned when the proxy is unreachable.
"""

import asyncio
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401


class FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class FakeAsyncClient:
    """Stands in for httpx.AsyncClient -- the real module is a MagicMock in
    this test environment (see tests/stubs.py), which doesn't support the
    async context manager protocol `async with httpx.AsyncClient() as c:`
    relies on."""

    result = None  # FakeResponse, or an Exception instance to raise

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *args, **kwargs):
        if isinstance(FakeAsyncClient.result, Exception):
            raise FakeAsyncClient.result
        return FakeAsyncClient.result


class TestListAiModels(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.ai_service as ai_service
        self.ai_service = ai_service
        self._orig_async_client = ai_service.httpx.AsyncClient
        ai_service.httpx.AsyncClient = FakeAsyncClient

    def tearDown(self):
        self.ai_service.httpx.AsyncClient = self._orig_async_client
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    def test_live_gateway_returns_models_and_live_true(self):
        FakeAsyncClient.result = FakeResponse(200, {"data": [{"id": "coder-smart"}, {"id": "claude"}]})
        models, live = asyncio.run(self.ai_service.list_ai_models())
        self.assertEqual(models, ["coder-smart", "claude"])
        self.assertTrue(live)

    def test_gateway_unreachable_returns_fallback_and_live_false(self):
        FakeAsyncClient.result = ConnectionError("connection refused")
        models, live = asyncio.run(self.ai_service.list_ai_models())
        self.assertFalse(live)
        self.assertGreater(len(models), 0)

    def test_non_200_response_returns_fallback_and_live_false(self):
        FakeAsyncClient.result = FakeResponse(500, {})
        models, live = asyncio.run(self.ai_service.list_ai_models())
        self.assertFalse(live)
        self.assertGreater(len(models), 0)


class TestDiscordModelsCommandLabelsFallback(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "discord-agent-bot"))
        import discord_bot
        self.discord_bot = discord_bot
        self.discord_bot.ALLOWED_USER_ID = None
        import agent_station_core.ai_service as ai_service
        self.ai_service = ai_service
        self._orig = ai_service.httpx.AsyncClient
        ai_service.httpx.AsyncClient = FakeAsyncClient

    def tearDown(self):
        self.ai_service.httpx.AsyncClient = self._orig
        if str(ROOT_DIR / "discord-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "discord-agent-bot"))

    def test_models_cmd_labels_fallback_when_gateway_unreachable(self):
        class DummyChannel:
            id = 111

        class DummyAuthor:
            id = "1"

        class DummyCtx:
            channel = DummyChannel()
            author = DummyAuthor()

            def __init__(self):
                self.replies = []

            async def reply(self, content=None, **kwargs):
                self.replies.append(content)

        FakeAsyncClient.result = ConnectionError("connection refused")
        ctx = DummyCtx()
        asyncio.run(self.discord_bot.models_cmd(ctx))
        self.assertTrue(any("Fallback AI Models" in r for r in ctx.replies))

    def test_models_cmd_labels_live_when_gateway_reachable(self):
        FakeAsyncClient.result = FakeResponse(200, {"data": [{"id": "coder-smart"}]})
        class DummyChannel:
            id = 222

        class DummyAuthor:
            id = "1"

        class DummyCtx:
            channel = DummyChannel()
            author = DummyAuthor()

            def __init__(self):
                self.replies = []

            async def reply(self, content=None, **kwargs):
                self.replies.append(content)

        ctx = DummyCtx()
        asyncio.run(self.discord_bot.models_cmd(ctx))
        self.assertTrue(any("Active AI Models" in r and "Fallback" not in r for r in ctx.replies))


if __name__ == "__main__":
    unittest.main()
