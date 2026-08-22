"""
Configuration and YAML validation tests for OMV AI Orchestrator Stack.
"""

import unittest
import yaml
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

class TestConfig(unittest.TestCase):
    def test_litellm_config_syntax(self):
        config_path = ROOT_DIR / "litellm" / "config.yaml"
        self.assertTrue(config_path.exists(), "litellm/config.yaml must exist")
        
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        self.assertIn("model_list", data)
        self.assertIn("router_settings", data)
        self.assertIn("general_settings", data)
        
        model_names = [m["model_name"] for m in data["model_list"]]
        
        # Check core models are present
        self.assertIn("gemini-3.7-flash", model_names)
        self.assertIn("gemini-3.7-pro", model_names)
        self.assertIn("claude-3-7-sonnet-direct", model_names)
        self.assertIn("claude-3-7-sonnet-vertex", model_names)
        self.assertIn("github-gpt-4o", model_names)
        self.assertIn("github-o1", model_names)
        self.assertIn("coder-fast", model_names)
        self.assertIn("coder-smart", model_names)
        self.assertIn("reasoning-heavy", model_names)

    def test_docker_compose_syntax(self):
        compose_path = ROOT_DIR / "docker-compose.yml"
        self.assertTrue(compose_path.exists())
        
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        self.assertIn("services", data)
        services = data["services"]
        self.assertIn("litellm", services)
        self.assertIn("syncthing", services)
        self.assertIn("telegram-bot", services)
        self.assertIn("web-terminal", services)
        self.assertIn("signal-bot", services)
        self.assertIn("discord-bot", services)

    def test_env_example_complete(self):
        env_path = ROOT_DIR / "env.example"
        self.assertTrue(env_path.exists())
        content = env_path.read_text()
        
        self.assertIn("GEMINI_API_KEY", content)
        self.assertIn("ANTHROPIC_API_KEY", content)
        self.assertIn("GITHUB_TOKEN", content)
        self.assertIn("TELEGRAM_BOT_TOKEN", content)
        self.assertIn("SIGNAL_PHONE_NUMBER", content)
        self.assertIn("GIT_AUTHOR_NAME", content)

if __name__ == "__main__":
    unittest.main()
