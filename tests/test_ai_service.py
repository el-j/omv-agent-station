"""
Tests for agent_station_core.ai_service.list_ai_models() (issue #17):
callers must be able to tell a live LiteLLM gateway read apart from the
hardcoded fallback list returned when the proxy is unreachable.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs


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


class TestQueryAiModel(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.ai_service as ai_service
        self.ai_service = ai_service
        self._orig_create = ai_service.ai_client.chat.completions.create

    def tearDown(self):
        self.ai_service.ai_client.chat.completions.create = self._orig_create
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    def test_success_returns_answer_and_model(self):
        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content="The answer is 42."))]
        self.ai_service.ai_client.chat.completions.create = AsyncMock(return_value=fake_response)

        res = asyncio.run(self.ai_service.query_ai_model("what is the answer?", model="coder-smart"))

        self.assertTrue(res["success"])
        self.assertEqual(res["answer"], "The answer is 42.")
        self.assertEqual(res["model"], "coder-smart")

    def test_empty_content_falls_back_to_placeholder(self):
        fake_response = MagicMock()
        fake_response.choices = [MagicMock(message=MagicMock(content=None))]
        self.ai_service.ai_client.chat.completions.create = AsyncMock(return_value=fake_response)

        res = asyncio.run(self.ai_service.query_ai_model("hello"))

        self.assertTrue(res["success"])
        self.assertEqual(res["answer"], "No response received.")

    def test_failure_returns_error_dict(self):
        self.ai_service.ai_client.chat.completions.create = AsyncMock(side_effect=ConnectionError("gateway down"))

        res = asyncio.run(self.ai_service.query_ai_model("hello", model="reasoning-heavy"))

        self.assertFalse(res["success"])
        self.assertIn("gateway down", res["error"])
        self.assertEqual(res["model"], "reasoning-heavy")


class TestDiscordModelsCommandLabelsFallback(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "discord-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "discord_bot")
        import discord_bot
        import core.security as core_security
        self.discord_bot = discord_bot
        core_security.ALLOWED_USER_ID = None
        import agent_station_core.ai_service as ai_service
        self.ai_service = ai_service
        self._orig = ai_service.httpx.AsyncClient
        ai_service.httpx.AsyncClient = FakeAsyncClient

    def tearDown(self):
        self.ai_service.httpx.AsyncClient = self._orig
        if str(ROOT_DIR / "discord-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "discord-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "discord_bot")

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


class TestGetModelhelpMarkdown(unittest.TestCase):
    """Regression coverage for issue #68: /modelhelp used to be a hand-maintained
    string that went stale every time litellm/config.yaml changed (this already
    happened once, per issue #13). It's now generated live from the config, so
    these tests mostly guard against the generator throwing or silently
    producing something that doesn't reflect the real file."""

    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.ai_service as ai_service
        self.ai_service = ai_service

    def tearDown(self):
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    def test_generation_does_not_throw_and_covers_every_model_group(self):
        import yaml
        config = yaml.safe_load((ROOT_DIR / "litellm" / "config.yaml").read_text(encoding="utf-8"))
        model_names = {d["model_name"] for d in config["model_list"]}

        text = self.ai_service.get_modelhelp_markdown()

        self.assertIsInstance(text, str)
        for name in model_names:
            self.assertIn(name, text, f"/modelhelp output is missing model_name group '{name}'")

    def test_generation_reflects_concrete_real_values(self):
        """A couple of hand-checked assertions so a generator that silently
        produces garbage (e.g. empty pools everywhere) can't pass the
        group-coverage check above vacuously."""
        text = self.ai_service.get_modelhelp_markdown()
        self.assertIn("coder-smart", text)
        self.assertIn("openrouter/poolside/laguna-s-2.1:free", text)
        self.assertIn("anthropic/claude-3-7-sonnet-20250219", text)
        # Router-level fallback chain for coder-smart, read straight out of
        # router_settings.fallbacks -- not hand-maintained anywhere.
        self.assertIn("gemini-3.7-pro", text)

    def test_missing_config_file_falls_back_gracefully(self):
        orig = self.ai_service._find_litellm_config_path
        self.ai_service._find_litellm_config_path = lambda: None
        try:
            text = self.ai_service.get_modelhelp_markdown()
            self.assertIsInstance(text, str)
            self.assertGreater(len(text), 0)
        finally:
            self.ai_service._find_litellm_config_path = orig


if __name__ == "__main__":
    unittest.main()
