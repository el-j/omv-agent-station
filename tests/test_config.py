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

    def test_omv_datamodel_schema_validity(self):
        import json
        datamodel_dir = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "datamodels"
        self.assertTrue(datamodel_dir.exists())
        
        for json_file in datamodel_dir.glob("*.json"):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.assertIn("type", data, f"{json_file.name} missing 'type'")
            self.assertIn("id", data, f"{json_file.name} missing 'id'")
            self.assertEqual(json_file.stem, data["id"], f"Filename {json_file.name} must match id {data['id']}")
            
            if data["type"] == "config":
                self.assertIn("query", data)
                self.assertIn("properties", data)
            elif data["type"] == "rpc":
                self.assertIn("params", data, f"RPC datamodel {json_file.name} MUST have 'params' attribute")
                self.assertIn("properties", data["params"])

    def test_workbench_yaml_schema_validity(self):
        import uuid
        workbench_dir = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "workbench"
        
        # 1. Navigation items
        nav_dir = workbench_dir / "navigation.d"
        for nav_file in nav_dir.glob("*.yaml"):
            with open(nav_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertEqual(data.get("type"), "navigation-item", f"{nav_file.name} must be type: navigation-item")
            nav_data = data.get("data", {})
            self.assertIn("path", nav_data, f"{nav_file.name} missing path")
            self.assertIn("text", nav_data, f"{nav_file.name} missing text")
            if nav_file.stem == "agentstation":
                self.assertNotIn("url", nav_data, "Root navigation item must NOT have a url field (acts as container group)")
            else:
                self.assertIn("url", nav_data, f"Submenu {nav_file.name} must have a url field")

        # 2. Routes
        route_dir = workbench_dir / "route.d"
        for route_file in route_dir.glob("*.yaml"):
            with open(route_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertEqual(data.get("type"), "route", f"{route_file.name} must be type: route")
            route_data = data.get("data", {})
            self.assertIn("url", route_data)
            self.assertIn("component", route_data)

        # 3. Dashboard Widget
        dash_dir = workbench_dir / "dashboard.d"
        for dash_file in dash_dir.glob("*.yaml"):
            with open(dash_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertEqual(data.get("type"), "dashboard-widget", f"{dash_file.name} must be type: dashboard-widget")
            dash_data = data.get("data", {})
            self.assertIn("id", dash_data)
            # Verify UUID format
            val_uuid = uuid.UUID(str(dash_data["id"]))
            self.assertIsNotNone(val_uuid)
            self.assertEqual(dash_data.get("type"), "grid")

if __name__ == "__main__":
    unittest.main()

