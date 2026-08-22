"""
Black-box testing suite for OMV Agent Station Stack.
Treats all scripts, packaging tools, and security barriers as black-box systems.
"""

import os
import sys
import json
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path

# Load test isolation stubs
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401

class TestBlackboxSecurityAndSanitization(unittest.TestCase):
    """Black-box security, injection, and path traversal tests."""

    def test_path_traversal_attacks_prevented(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        try:
            import bot
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir) / "workspace"
                workspace.mkdir()
                
                # Malicious inputs
                malicious_inputs = [
                    "../../etc/passwd",
                    "../../../root/.ssh/id_rsa",
                    "/etc/shadow",
                    "/var/run/docker.sock",
                    "../workspace",
                    "..",
                    "....//....//etc",
                    "/",
                ]
                for evil in malicious_inputs:
                    res = bot.sanitize_project_path(workspace, evil)
                    self.assertIsNone(res, f"Path traversal attack '{evil}' was NOT blocked!")
                
                # Valid subprojects
                valid_project = workspace / "my-cool-project"
                valid_project.mkdir()
                res = bot.sanitize_project_path(workspace, "my-cool-project")
                self.assertIsNotNone(res)
                self.assertEqual(res, valid_project.resolve())
        finally:
            if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
                sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))

    def test_telegram_authorization_blackbox(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        try:
            import bot
            
            class DummyUser:
                def __init__(self, uid):
                    self.id = uid

            class DummyUpdate:
                def __init__(self, uid):
                    self.effective_user = DummyUser(uid) if uid is not None else None

            # Test when ALLOWED_USER_ID is set
            bot.ALLOWED_USER_ID = "987654321"
            self.assertTrue(bot.authorized(DummyUpdate("987654321")))
            self.assertFalse(bot.authorized(DummyUpdate("111111111")))
            self.assertFalse(bot.authorized(DummyUpdate(None)))
            self.assertFalse(bot.authorized(DummyUpdate("9876543210")))
        finally:
            if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
                sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))

    def test_discord_authorization_blackbox(self):
        sys.path.insert(0, str(ROOT_DIR / "discord-agent-bot"))
        try:
            import discord_bot
            
            class DummyAuthor:
                def __init__(self, uid):
                    self.id = uid

            class DummyContext:
                def __init__(self, uid):
                    self.author = DummyAuthor(uid) if uid is not None else None

            discord_bot.ALLOWED_USER_ID = "555666777"
            self.assertTrue(discord_bot.is_authorized(DummyContext("555666777")))
            self.assertFalse(discord_bot.is_authorized(DummyContext("999999999")))
            self.assertFalse(discord_bot.is_authorized(DummyContext(None)))
        finally:
            if str(ROOT_DIR / "discord-agent-bot") in sys.path:
                sys.path.remove(str(ROOT_DIR / "discord-agent-bot"))


class TestBlackboxCLIAndPackaging(unittest.TestCase):
    """Black-box testing for CLI lifecycle helper and Debian packaging."""

    def test_debian_package_structure_and_permissions(self):
        deb_script = ROOT_DIR / "build-deb.sh"
        self.assertTrue(deb_script.exists())
        
        # Build deb in isolated environment
        res = subprocess.run([str(deb_script)], cwd=str(ROOT_DIR), capture_output=True, text=True)  # nosec B603,B607
        self.assertEqual(res.returncode, 0, f"build-deb.sh failed: {res.stderr}")
        
        deb_file = ROOT_DIR / "openmediavault-agent-station_1.0.0_all.deb"
        self.assertTrue(deb_file.exists(), "Debian package must exist after build")
        self.assertGreater(deb_file.stat().st_size, 5000, "Package size should be substantial")

    def test_cli_helper_missing_config_behavior(self):
        cli_bin = ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station"
        self.assertTrue(cli_bin.exists())
        
        # Test help command
        res = subprocess.run([str(cli_bin), "help"], capture_output=True, text=True)  # nosec B603,B607
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage:", res.stdout)

    def test_cli_apply_generates_valid_env_blackbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "etc"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "test-config.json"
            stack_dir = Path(tmpdir) / "stack"
            stack_dir.mkdir(parents=True)
            
            test_config = {
                "enable": False,
                "data_dir": f"{tmpdir}/data",
                "chat_service": "telegram",
                "gemini_api_key": "test-gemini-key",
                "anthropic_api_key": "test-anthropic-key",
                "github_token": "test-github-token",
                "git_author_name": "Test Bot",
                "git_author_email": "bot@test.local",
                "telegram_bot_token": "123456:ABC-DEF",
                "telegram_allowed_user_id": "12345678"
            }
            config_file.write_text(json.dumps(test_config), encoding="utf-8")
            
            cli_bin = ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station"
            
            env = os.environ.copy()
            env["CONFIG_FILE"] = str(config_file)
            env["STACK_DIR"] = str(stack_dir)
            
            res = subprocess.run(["bash", str(cli_bin), "apply"], env=env, cwd=str(ROOT_DIR), capture_output=True, text=True)  # nosec B603,B607
            self.assertEqual(res.returncode, 0)
            
            # Verify directories were created
            self.assertTrue((Path(tmpdir) / "data" / "obsidian").exists())
            self.assertTrue((Path(tmpdir) / "data" / "workspace").exists())
            self.assertTrue((Path(tmpdir) / "data" / "ssh").exists())
            
            # Verify generated .env file
            env_out = (stack_dir / ".env").read_text()
            self.assertIn("GEMINI_API_KEY=test-gemini-key", env_out)
            self.assertIn("GIT_AUTHOR_NAME=Test Bot", env_out)


class TestBlackboxRouterRedundancy(unittest.TestCase):
    """Black-box tests for LiteLLM fallback chains."""

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

if __name__ == "__main__":
    unittest.main()
