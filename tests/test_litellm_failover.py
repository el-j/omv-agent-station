"""
LiteLLM routing coverage, split into what each test actually proves.

TestLiteLLMConfigStaticAssertions parses litellm/config.yaml as text/YAML and
cross-checks it against the /modelhelp doc strings. It catches a fallback
target being renamed or deleted, but never runs LiteLLM -- it moved here from
tests/test_blackbox.py, where it was neither black-box nor about routing
behavior (GitHub issue #60).
"""

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestLiteLLMConfigStaticAssertions(unittest.TestCase):
    """Static consistency checks over litellm/config.yaml. No LiteLLM process runs."""

    def test_router_fallback_continuity(self):
        import yaml
        config_path = ROOT_DIR / "litellm" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        all_models = {m["model_name"] for m in data["model_list"]}
        fallbacks = data.get("router_settings", {}).get("fallbacks", [])

        for fb in fallbacks:
            for primary, secondary_list in fb.items():
                self.assertIn(primary, all_models, f"Fallback primary model '{primary}' not registered in model_list!")
                for sec in secondary_list:
                    self.assertIn(sec, all_models, f"Fallback target '{sec}' for '{primary}' not in model_list!")

    def test_modelhelp_text_matches_config_fallbacks(self):
        """Regression coverage for issue #13: /modelhelp's described fallback
        chains must match litellm/config.yaml's real router_settings.fallbacks,
        in both the agent_station_core copy (Discord/Signal) and Telegram's
        independent copy in handlers/ai_chat.py."""
        import yaml
        config_path = ROOT_DIR / "litellm" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        fallbacks = {}
        for fb in data["router_settings"]["fallbacks"]:
            fallbacks.update(fb)

        # Human-readable labels used in the doc text for each model_name that
        # appears in a fallback chain /modelhelp documents.
        label = {
            "gemini-3.7-pro": "Gemini 3.7 Pro",
            "gemini-3.7-flash": "Gemini 3.7 Flash",
            "gemini-2.5-flash": "Gemini 2.5 Flash",
            "github-gpt-4o": "GPT-4o",
            "github-deepseek-r1": "DeepSeek-R1",
            "github-o3-mini": "o3-mini",
        }

        sys.path.insert(0, str(ROOT_DIR))
        try:
            import agent_station_core.ai_service as ai_service
            shared_text = ai_service.get_modelhelp_markdown()
        finally:
            if str(ROOT_DIR) in sys.path:
                sys.path.remove(str(ROOT_DIR))

        telegram_text = (ROOT_DIR / "telegram-agent-bot" / "handlers" / "ai_chat.py").read_text(encoding="utf-8")

        for router in ("coder-smart", "reasoning-heavy"):
            chain = fallbacks[router]
            expected = " ➔ ".join(label[m] for m in chain)
            self.assertIn(expected, shared_text, f"agent_station_core modelhelp text out of sync with {router}'s real fallback chain")
            self.assertIn(expected, telegram_text, f"Telegram modelhelp text out of sync with {router}'s real fallback chain")


if __name__ == "__main__":
    unittest.main()
