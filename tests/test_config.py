"""
Configuration and YAML validation tests for OMV AI Orchestrator Stack.
"""

import re
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

    def test_openrouter_free_tier_models_are_wired_into_virtual_routers(self):
        """Free (":free"-suffixed) OpenRouter deployments must actually be part
        of coder-fast/coder-smart/reasoning-heavy's model_list, not just present
        somewhere in the file -- a standalone, unreferenced entry (like the
        pre-existing openrouter-auto model) is unreachable by default and
        defeats the point of a free tier."""
        config_path = ROOT_DIR / "litellm" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        deployments_by_group: dict[str, list[dict]] = {}
        for deployment in data["model_list"]:
            deployments_by_group.setdefault(deployment["model_name"], []).append(deployment)

        free_model_names = {
            name for name, deployments in deployments_by_group.items()
            if any(":free" in d["litellm_params"].get("model", "") for d in deployments)
        }
        self.assertTrue(free_model_names, "No ':free' OpenRouter model_list entries found in litellm/config.yaml")

        for router_name in ("coder-fast", "coder-smart", "reasoning-heavy"):
            router_models = [d["litellm_params"].get("model", "") for d in deployments_by_group[router_name]]
            self.assertTrue(
                any(":free" in m for m in router_models),
                f"'{router_name}' has no free OpenRouter deployment in its model_list -- "
                "it will never actually be tried, same mistake openrouter-auto made."
            )
            for m in [x for x in router_models if ":free" in x]:
                self.assertTrue(m.startswith("openrouter/"), f"Unexpected free model '{m}' not routed via openrouter/")

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
        self.assertIn("OPENROUTER_API_KEY", content)
        self.assertIn("MISTRAL_API_KEY", content)
        self.assertIn("DEEPSEEK_API_KEY", content)
        self.assertIn("TELEGRAM_BOT_TOKEN", content)
        self.assertIn("SIGNAL_PHONE_NUMBER", content)
        self.assertIn("DISCORD_BOT_TOKEN", content)
        self.assertIn("DISCORD_ALLOWED_USER_ID", content)
        self.assertIn("GIT_AUTHOR_NAME", content)

    def test_env_example_covers_every_litellm_env_var(self):
        """Regression coverage for issue #15: every os.environ/X reference in
        litellm/config.yaml must have a corresponding line in env.example, so
        adding a new provider there can't silently leave users unable to
        discover the variable that unlocks it."""
        config_path = ROOT_DIR / "litellm" / "config.yaml"
        config_text = config_path.read_text(encoding="utf-8")
        referenced_vars = set(re.findall(r"os\.environ/([A-Z0-9_]+)", config_text))
        self.assertTrue(referenced_vars, "Expected at least one os.environ/ reference in litellm/config.yaml")

        env_content = (ROOT_DIR / "env.example").read_text(encoding="utf-8")
        missing = sorted(v for v in referenced_vars if v not in env_content)
        self.assertEqual(missing, [], f"env.example is missing variables referenced by litellm/config.yaml: {missing}")

    def test_env_example_covers_every_python_env_var(self):
        """Regression coverage for issue #70: every os.environ.get/os.getenv/
        os.environ[...] key actually read by agent_station_core and the three
        bot entrypoints/handlers must have a corresponding entry in
        env.example, so a var the code reads silently can't stay undocumented
        the way WORKSPACE_PATH, SIGNAL_CLI_URL, and friends did."""
        scan_targets = [
            *(ROOT_DIR / "agent_station_core").glob("*.py"),
            ROOT_DIR / "telegram-agent-bot" / "bot.py",
            *(ROOT_DIR / "telegram-agent-bot" / "core").glob("*.py"),
            *(ROOT_DIR / "telegram-agent-bot" / "handlers").glob("*.py"),
            ROOT_DIR / "discord-agent-bot" / "discord_bot.py",
            ROOT_DIR / "signal-agent-bot" / "signal_bot.py",
        ]
        scan_targets = [p for p in scan_targets if p.exists()]
        self.assertTrue(scan_targets, "Expected to find at least one source file to scan")

        pattern = re.compile(
            r"os\.environ\.get\(\s*[\"']([A-Z0-9_]+)[\"']"
            r"|os\.getenv\(\s*[\"']([A-Z0-9_]+)[\"']"
            r"|os\.environ\[\s*[\"']([A-Z0-9_]+)[\"']\s*\]"
        )

        referenced_vars = set()
        for path in scan_targets:
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                referenced_vars.add(next(g for g in match.groups() if g))

        self.assertTrue(referenced_vars, "Expected at least one os.environ/os.getenv reference in the scanned files")

        env_content = (ROOT_DIR / "env.example").read_text(encoding="utf-8")
        missing = sorted(v for v in referenced_vars if v not in env_content)
        self.assertEqual(
            missing, [],
            f"env.example is missing variables read by agent_station_core/the bots: {missing}",
        )

    def test_omv_datamodel_schema_validity(self):
        import json
        datamodel_dir = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "datamodels"
        self.assertTrue(datamodel_dir.exists())
        
        for json_file in datamodel_dir.glob("*.json"):
            if json_file.name.startswith("."):
                continue
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
            if nav_file.name.startswith("."):
                continue
            with open(nav_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertEqual(data.get("type"), "navigation-item", f"{nav_file.name} must be type: navigation-item")
            nav_data = data.get("data", {})
            self.assertIn("path", nav_data, f"{nav_file.name} missing path")
            self.assertIn("text", nav_data, f"{nav_file.name} missing text")
            self.assertIn("url", nav_data, f"{nav_file.name} must have a url field")
            self.assertIn("permissions", nav_data, f"{nav_file.name} must have permissions specified")
            self.assertIn("role", nav_data["permissions"])

        # 2. Routes
        route_dir = workbench_dir / "route.d"
        for route_file in route_dir.glob("*.yaml"):
            if route_file.name.startswith("."):
                continue
            with open(route_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertEqual(data.get("type"), "route", f"{route_file.name} must be type: route")
            route_data = data.get("data", {})
            self.assertIn("url", route_data)
            # Routes can either define a component to render, or redirect to another route
            self.assertTrue(
                "component" in route_data or "redirectTo" in route_data,
                f"{route_file.name} must have either a 'component' or 'redirectTo' field"
            )

        # 3. Dashboard Widget
        dash_dir = workbench_dir / "dashboard.d"
        for dash_file in dash_dir.glob("*.yaml"):
            if dash_file.name.startswith("."):
                continue
            with open(dash_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertEqual(data.get("type"), "dashboard-widget", f"{dash_file.name} must be type: dashboard-widget")
            dash_data = data.get("data", {})
            self.assertIn("id", dash_data)
            # Verify UUID format
            val_uuid = uuid.UUID(str(dash_data["id"]))
            self.assertIsNotNone(val_uuid)
            self.assertEqual(dash_data.get("type"), "grid")

        # 4. Component Pages
        comp_dir = workbench_dir / "component.d"
        for comp_file in comp_dir.glob("*.yaml"):
            if comp_file.name.startswith("."):
                continue
            with open(comp_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.assertEqual(data.get("type"), "component", f"{comp_file.name} must be type: component")
            comp_data = data.get("data", {})
            self.assertIn("name", comp_data)
            self.assertIn("type", comp_data)
            self.assertIn("config", comp_data)

class TestDocsMatchCode(unittest.TestCase):
    """Regression coverage for issue #14: three doc-vs-code mismatches found
    in the 2026-08-26 audit pass."""

    def test_spec_filename_matches_vault_service(self):
        vault_service = (ROOT_DIR / "agent_station_core" / "vault_service.py").read_text(encoding="utf-8")
        self.assertIn('"project-spec.md"', vault_service)

        for doc_path in (ROOT_DIR / "README.md", ROOT_DIR / "OMV_AI_SERVER_HANDBOOK.md"):
            text = doc_path.read_text(encoding="utf-8")
            self.assertNotIn(
                "/spec.md", text,
                f"{doc_path.name} still references the wrong filename 'spec.md' -- "
                f"the code actually creates 'project-spec.md'",
            )

    def test_no_agent_log_md_claim_without_matching_code(self):
        for path in ROOT_DIR.rglob("*.md"):
            if "node_modules" in path.parts or path.name.startswith("."):
                continue
            self.assertNotIn(
                "agent-log.md", path.read_text(encoding="utf-8"),
                f"{path.relative_to(ROOT_DIR)} claims agents write to 'agent-log.md', "
                f"but no code anywhere creates or writes that file",
            )

    def test_status_ram_claim_matches_implementation(self):
        task_service = (ROOT_DIR / "agent_station_core" / "task_service.py").read_text(encoding="utf-8")
        self.assertIn("def get_ram_usage", task_service)
        self.assertIn('"ram":', task_service)

        telegram_system = (ROOT_DIR / "telegram-agent-bot" / "handlers" / "system.py").read_text(encoding="utf-8")
        self.assertIn("ram_out", telegram_system)

    def test_upload_feature_is_documented(self):
        """Regression coverage for issue #30: the file-upload-to-GitHub
        feature isn't a slash command, so it's invisible to a new user
        unless /help and the handbook explicitly call it out."""
        handbook = (ROOT_DIR / "OMV_AI_SERVER_HANDBOOK.md").read_text(encoding="utf-8")
        self.assertIn("upload/<timestamp>", handbook)

        for bot_file, marker in (
            ("telegram-agent-bot/handlers/system.py", "upload it into the bound project's repo"),
            ("discord-agent-bot/handlers/system.py", "destination path"),
            ("signal-agent-bot/handlers/system.py", "destination path"),
        ):
            text = (ROOT_DIR / bot_file).read_text(encoding="utf-8")
            self.assertIn(marker, text, f"{bot_file} doesn't mention the file-upload feature in its help text")


class TestCustomLlmEndpointReachable(unittest.TestCase):
    """Regression coverage for issue #74: litellm/config.yaml's "custom-llm"
    model reads os.environ/CUSTOM_API_BASE and os.environ/CUSTOM_API_KEY, and
    env.example documents both as a self-hosted OpenAI-compatible endpoint --
    but neither compose file previously forwarded them into the litellm
    container, and the plugin's write_env_file()/WebGUI never set them. Every
    install path must actually be able to populate these two variables."""

    def test_docker_compose_forwards_custom_llm_vars_to_litellm(self):
        compose_path = ROOT_DIR / "docker-compose.yml"
        with open(compose_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        litellm_env = data["services"]["litellm"]["environment"]
        joined = "\n".join(litellm_env)
        self.assertIn("CUSTOM_API_BASE", joined)
        self.assertIn("CUSTOM_API_KEY", joined)

    def test_omv_compose_template_forwards_custom_llm_vars_to_litellm(self):
        template_path = ROOT_DIR / "omv-compose-template.yaml"
        with open(template_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        litellm_env = data["services"]["litellm"]["environment"]
        joined = "\n".join(litellm_env)
        self.assertIn("CUSTOM_API_BASE", joined)
        self.assertIn("CUSTOM_API_KEY", joined)

    def test_write_env_file_emits_custom_llm_vars(self):
        script_text = (
            ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station"
        ).read_text(encoding="utf-8")
        self.assertIn("custom_api_base", script_text)
        self.assertIn("custom_api_key", script_text)
        self.assertIn("CUSTOM_API_BASE=", script_text)
        self.assertIn("CUSTOM_API_KEY=", script_text)

    def test_webgui_has_custom_llm_form_fields(self):
        form_path = (
            ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault"
            / "workbench" / "component.d" / "omv-services-agentstation-aimodels-form-page.yaml"
        )
        with open(form_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        field_names = {f.get("name") for f in data["data"]["config"]["fields"] if isinstance(f, dict)}
        self.assertIn("custom_api_base", field_names)
        self.assertIn("custom_api_key", field_names)

    def test_setsettings_datamodel_accepts_custom_llm_fields(self):
        import json
        datamodel_path = (
            ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault"
            / "datamodels" / "rpc.agentstation.setsettings.json"
        )
        with open(datamodel_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        properties = data["params"]["properties"]
        self.assertIn("custom_api_base", properties)
        self.assertIn("custom_api_key", properties)


if __name__ == "__main__":
    unittest.main()
