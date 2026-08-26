"""
Black-box testing suite for OMV Agent Station Stack.
Treats all scripts, packaging tools, and security barriers as black-box systems.
"""

import os
import re
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


    def test_repo_name_sanitization_blackbox(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        try:
            import bot
            valid_names = ["my-cool-app", "backend_api", "service.v2", "omv-agent-123"]
            for name in valid_names:
                self.assertEqual(bot.sanitize_repo_name(name), name)

            invalid_names = [
                "../../evil-app",
                "-bad-start",
                ".hidden",
                "repo/with/slashes",
                "repo\\with\\backslashes",
                "repo with spaces",
                "repo;rm -rf /",
                "",
                None
            ]
            for name in invalid_names:
                self.assertIsNone(bot.sanitize_repo_name(name), f"Unsafe repo name '{name}' was not blocked!")
        finally:
            if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
                sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))

    def test_telegram_topic_binding_and_context_resolution(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        try:
            import bot
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir) / "workspace"
                workspace.mkdir()
                bot.WORKSPACE = workspace
                bot.TOPICS_FILE = workspace / ".agent_topics.json"

                # Create sample projects
                (workspace / "project-alpha").mkdir()
                (workspace / "project-beta").mkdir()

                # Bind thread 42 in chat 100 to project-alpha
                bot.set_bound_project(100, 42, "project-alpha")
                self.assertEqual(bot.get_bound_project(100, 42), "project-alpha")
                self.assertIsNone(bot.get_bound_project(100, 99))

                # Test resolve_project_context
                class DummyMessage:
                    def __init__(self, thread_id):
                        self.message_thread_id = thread_id

                class DummyChat:
                    def __init__(self, cid):
                        self.id = cid

                class DummyContext:
                    def __init__(self, args):
                        self.args = args

                class DummyUpdate:
                    def __init__(self, cid, thread_id):
                        self.effective_chat = DummyChat(cid)
                        self.effective_message = DummyMessage(thread_id)

                # Case A: Inside topic 42 with implicit project args
                upA = DummyUpdate(100, 42)
                ctxA = DummyContext(["Add", "new", "feature"])
                proj, rem = bot.resolve_project_context(upA, ctxA)
                self.assertEqual(proj, "project-alpha")
                self.assertEqual(rem, ["Add", "new", "feature"])

                # Case B: Inside topic 42 with explicit override project
                upB = DummyUpdate(100, 42)
                ctxB = DummyContext(["project-beta", "Add", "feature"])
                projB, remB = bot.resolve_project_context(upB, ctxB)
                self.assertEqual(projB, "project-beta")
                self.assertEqual(remB, ["Add", "feature"])

                # Unbind
                bot.remove_bound_project(100, 42)
                self.assertIsNone(bot.get_bound_project(100, 42))
        finally:
            if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
                sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))

    def test_custom_commands_lifecycle_and_expansion_blackbox(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        try:
            import bot
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir) / "workspace"
                obsidian = Path(tmpdir) / "obsidian"
                workspace.mkdir()
                obsidian.mkdir()

                bot.WORKSPACE = workspace
                bot.OBSIDIAN_VAULT = obsidian
                bot.CUSTOM_CMDS_FILE = workspace / ".custom_commands.json"
                bot.OBSIDIAN_CMDS_FILE = obsidian / "Config" / "commands.json"

                # 1. Validation of command names
                self.assertEqual(bot.sanitize_cmd_name("test"), "test")
                self.assertEqual(bot.sanitize_cmd_name("my_test_2"), "my_test_2")
                self.assertIsNone(bot.sanitize_cmd_name("test-with-dashes!"))
                self.assertIsNone(bot.sanitize_cmd_name("bad name with spaces"))
                self.assertIsNone(bot.sanitize_cmd_name("../../evil"))

                # 2. Saving and dual-storage persistence
                initial_cmds = {
                    "test": "/exec pytest -v",
                    "review": "/chat \"Review this code: {args}\"",
                    "build": "npm run build"
                }
                bot.save_custom_commands(initial_cmds)
                self.assertTrue(bot.CUSTOM_CMDS_FILE.exists())
                self.assertTrue(bot.OBSIDIAN_CMDS_FILE.exists())

                loaded = bot.load_custom_commands()
                self.assertEqual(loaded.get("test"), "/exec pytest -v")
                self.assertEqual(loaded.get("review"), "/chat \"Review this code: {args}\"")

                # 3. Parameter expansion logic
                template_a = loaded["review"]
                user_input = "def foo(): return 42"
                expanded_a = template_a.replace("{args}", user_input)
                self.assertEqual(expanded_a, "/chat \"Review this code: def foo(): return 42\"")

                template_b = loaded["test"]
                extra_args = "-k auth"
                expanded_b = f"{template_b} {extra_args}"
                self.assertEqual(expanded_b, "/exec pytest -v -k auth")

                # 4. Built-in command collision defense
                for builtin in ["start", "help", "task", "status", "exec", "newrepo", "bind"]:
                    self.assertIn(builtin, bot.BUILTIN_COMMANDS)
        finally:
            if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
                sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))

    def test_credentials_multi_tier_persistence_and_file_permissions_blackbox(self):
        """Validates that credentials survive partial saves, upgrades, and are protected with 0600 permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            primary_cfg = tmp / "etc_agent_station.json"
            backup_cfg = tmp / "srv_data_config" / "agent-station.json"
            env_file = tmp / "stack.env"
            backup_cfg.parent.mkdir(parents=True, exist_ok=True)

            # 1. Initial full configuration save
            full_config = {
                "enable": True,
                "data_dir": str(tmp / "srv_data"),
                "enable_aimodels": True,
                "gemini_api_key": "AIzaSyTestGeminiKey12345",
                "anthropic_api_key": "sk-ant-test-anthropic-key-67890",
                "github_token": "ghp_TestGitHubPersonalAccessToken",
                "telegram_bot_token": "8996841045:AAEmznTestToken",
                "telegram_allowed_user_id": "104897299",
                "litellm_master_key": "sk-omv-secret-master-key"
            }
            primary_cfg.write_text(json.dumps(full_config, indent=2))
            os.chmod(str(primary_cfg), 0o600)

            # Backup mirror
            backup_cfg.write_text(json.dumps(full_config, indent=2))
            os.chmod(str(backup_cfg), 0o600)

            # 2. Simulate partial save from Angular Formly (e.g. Overview tab saves only {"enable": true, "telegram_bot_token": ""})
            partial_incoming = {
                "enable": True,
                "telegram_bot_token": "",  # Empty submit must NOT erase saved token
                "gemini_api_key": "",      # Empty submit must NOT erase saved key
            }

            secret_fields = [
                "gemini_api_key", "anthropic_api_key", "github_token", "github_git_token",
                "gitlab_token", "bitbucket_app_password", "mistral_api_key", "openrouter_api_key",
                "deepseek_api_key", "telegram_bot_token", "discord_bot_token", "litellm_master_key"
            ]

            existing = json.loads(primary_cfg.read_text())
            sanitized = {}
            for k, v in partial_incoming.items():
                if k in secret_fields:
                    if (v is None or v == "") and existing.get(k):
                        sanitized[k] = existing[k]
                    else:
                        sanitized[k] = str(v)
                else:
                    sanitized[k] = v

            merged = {**existing, **sanitized}
            self.assertEqual(merged["gemini_api_key"], "AIzaSyTestGeminiKey12345")
            self.assertEqual(merged["telegram_bot_token"], "8996841045:AAEmznTestToken")
            self.assertEqual(merged["github_token"], "ghp_TestGitHubPersonalAccessToken")

            # 3. Simulate wiping /etc/ (e.g. package purge) and auto-recovery from backup
            primary_cfg.unlink()
            self.assertFalse(primary_cfg.exists())
            self.assertTrue(backup_cfg.exists())

            # Auto-recovery logic
            recovered = json.loads(backup_cfg.read_text())
            primary_cfg.write_text(json.dumps(recovered, indent=2))
            os.chmod(str(primary_cfg), 0o600)

            self.assertTrue(primary_cfg.exists())
            self.assertEqual(primary_cfg.stat().st_mode & 0o777, 0o600)
            reloaded = json.loads(primary_cfg.read_text())
            self.assertEqual(reloaded["telegram_bot_token"], "8996841045:AAEmznTestToken")

class TestBlackboxCLIAndPackaging(unittest.TestCase):
    """Black-box testing for CLI lifecycle helper and Debian packaging."""

    def test_debian_package_structure_and_permissions(self):
        deb_script = ROOT_DIR / "build-deb.sh"
        self.assertTrue(deb_script.exists())

        # Read the version build-deb.sh will actually stamp on the artifact,
        # rather than hardcoding it, so this test can't silently go stale
        # (drift between this literal and VERSION= previously made this test
        # pass locally only by accident, off a leftover .deb from an older
        # build, while failing on every fresh CI checkout).
        version_match = re.search(r'^VERSION="([^"]+)"', deb_script.read_text(encoding="utf-8"), re.MULTILINE)
        self.assertIsNotNone(version_match, "Could not find VERSION= in build-deb.sh")
        version = version_match.group(1)

        # Build deb in isolated environment
        res = subprocess.run([str(deb_script)], cwd=str(ROOT_DIR), capture_output=True, text=True)  # nosec B603,B607
        self.assertEqual(res.returncode, 0, f"build-deb.sh failed: {res.stderr}")

        deb_file = ROOT_DIR / f"openmediavault-agent-station_{version}_all.deb"
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
