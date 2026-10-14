"""
Whitebox unit tests for the bots' security, sanitization, and binding helpers.

These used to live in tests/test_blackbox.py under names ending in
"_blackbox" (GitHub issue #60). They are not black-box tests: they import the
bot modules directly, reach into module globals (WORKSPACE, ALLOWED_USER_ID,
...), and call individual functions with hand-built dummy objects. That is a
perfectly good way to test these helpers -- it was only the label that was
wrong, so they moved here unchanged in substance and were renamed to say what
they actually do. tests/test_blackbox.py now holds only the genuinely
process-level tests that shell out to real scripts.
"""

import os
import sys
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

# Load test isolation stubs
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stubs


@contextmanager
def bot_on_sys_path(bot_dir_name, *module_names):
    """Puts one bot's directory on sys.path with a clean module slate, and
    tears both down afterwards. All three bots ship same-named `core`/`handlers`
    packages, so the purge on entry AND exit is what keeps whichever bot ran
    first from winning for the rest of the pytest process."""
    bot_dir = str(ROOT_DIR / bot_dir_name)
    stubs.purge_bot_modules(*module_names)
    sys.path.insert(0, bot_dir)
    try:
        yield
    finally:
        if bot_dir in sys.path:
            sys.path.remove(bot_dir)
        stubs.purge_bot_modules(*module_names)


class TestPathAndNameSanitization(unittest.TestCase):
    def test_path_traversal_attacks_prevented(self):
        with bot_on_sys_path("telegram-agent-bot", "core", "handlers", "bot"):
            import bot
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir) / "workspace"
                workspace.mkdir()

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

                valid_project = workspace / "my-cool-project"
                valid_project.mkdir()
                res = bot.sanitize_project_path(workspace, "my-cool-project")
                self.assertIsNotNone(res)
                self.assertEqual(res, valid_project.resolve())

    def test_repo_name_sanitization(self):
        with bot_on_sys_path("telegram-agent-bot", "core", "handlers", "bot"):
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


class TestAuthorization(unittest.TestCase):
    def test_telegram_authorization(self):
        with bot_on_sys_path("telegram-agent-bot", "core", "handlers", "bot"):
            import bot

            class DummyUser:
                def __init__(self, uid):
                    self.id = uid

            class DummyUpdate:
                def __init__(self, uid):
                    self.effective_user = DummyUser(uid) if uid is not None else None

            bot.ALLOWED_USER_ID = "987654321"
            self.assertTrue(bot.authorized(DummyUpdate("987654321")))
            self.assertFalse(bot.authorized(DummyUpdate("111111111")))
            self.assertFalse(bot.authorized(DummyUpdate(None)))
            self.assertFalse(bot.authorized(DummyUpdate("9876543210")))

    def test_discord_authorization(self):
        with bot_on_sys_path("discord-agent-bot", "core", "handlers", "discord_bot"):
            import discord_bot
            import core.security as core_security

            class DummyAuthor:
                def __init__(self, uid):
                    self.id = uid

            class DummyContext:
                def __init__(self, uid):
                    self.author = DummyAuthor(uid) if uid is not None else None

            core_security.ALLOWED_USER_ID = "555666777"
            self.assertTrue(discord_bot.is_authorized(DummyContext("555666777")))
            self.assertFalse(discord_bot.is_authorized(DummyContext("999999999")))
            self.assertFalse(discord_bot.is_authorized(DummyContext(None)))


class TestProjectBindingResolution(unittest.TestCase):
    def test_telegram_topic_binding_and_context_resolution(self):
        with bot_on_sys_path("telegram-agent-bot", "core", "handlers", "bot"):
            import bot
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir) / "workspace"
                workspace.mkdir()
                bot.WORKSPACE = workspace
                bot.TOPICS_FILE = workspace / ".agent_topics.json"

                (workspace / "project-alpha").mkdir()
                (workspace / "project-beta").mkdir()

                bot.set_bound_project(100, 42, "project-alpha")
                self.assertEqual(bot.get_bound_project(100, 42), "project-alpha")
                self.assertIsNone(bot.get_bound_project(100, 99))

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

                bot.remove_bound_project(100, 42)
                self.assertIsNone(bot.get_bound_project(100, 42))

    def test_discord_channel_scope_uses_stable_thread_id_not_message_id(self):
        """channel_scope() must key a Discord Thread by the thread's own stable id,
        not by ctx.message.id -- every message has a unique snowflake, so a binding
        set on one message could never be found again by a later message in the
        same thread if message id were used as the thread key."""
        with bot_on_sys_path("discord-agent-bot", "core", "handlers", "discord_bot"):
            import discord_bot
            import core.security as core_security

            class FakeThread:
                def __init__(self, thread_id, parent_id):
                    self.id = thread_id
                    self.parent_id = parent_id

            # Patch the (otherwise mocked) discord.Thread with a real class so
            # isinstance() checks in channel_scope() behave correctly.
            discord_bot.discord.Thread = FakeThread

            class FakeMessage:
                def __init__(self, mid):
                    self.id = mid

            class FakeCtx:
                def __init__(self, channel, message_id):
                    self.channel = channel
                    self.message = FakeMessage(message_id)

            thread = FakeThread(thread_id=999, parent_id=100)

            first_message_scope = core_security.channel_scope(FakeCtx(thread, message_id=111))
            second_message_scope = core_security.channel_scope(FakeCtx(thread, message_id=222))

            self.assertEqual(first_message_scope, second_message_scope)
            self.assertEqual(first_message_scope, ("100", "999"))

            class FakeChannel:
                def __init__(self, cid):
                    self.id = cid

            plain_channel_scope = core_security.channel_scope(FakeCtx(FakeChannel(555), message_id=333))
            self.assertEqual(plain_channel_scope, ("555", None))


class TestCustomCommandsStore(unittest.TestCase):
    def test_custom_commands_lifecycle_and_expansion(self):
        with bot_on_sys_path("telegram-agent-bot", "core", "handlers", "bot"):
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
                for builtin in ["start", "help", "task", "status", "exec", "newrepo", "bind", "cancel", "stop"]:
                    self.assertIn(builtin, bot.BUILTIN_COMMANDS)


class TestCredentialPersistenceContract(unittest.TestCase):
    """Models -- rather than executes -- the plugin's credential-storage contract.

    The real implementation of this merge lives in PHP
    (engined/rpc/agentstation.inc setSettings) and is executed for real by
    tests/php/AgentStationTest.php. This test re-states the same rules over
    plain temp files so a Python-only test run still documents them; it
    deliberately imports no product code, so it can never fail because of a
    regression in one. Kept (issue #60: no coverage lost in the move) but named
    to say so.
    """

    def test_partial_save_merge_and_backup_recovery_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            primary_cfg = tmp / "etc_agent_station.json"
            backup_cfg = tmp / "srv_data_config" / "agent-station.json"
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

            backup_cfg.write_text(json.dumps(full_config, indent=2))
            os.chmod(str(backup_cfg), 0o600)

            # 2. Partial save from Angular Formly (e.g. the Overview tab submits
            # only {"enable": true, "telegram_bot_token": ""})
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

            # 3. Wiping /etc/ (e.g. package purge) and auto-recovery from backup
            primary_cfg.unlink()
            self.assertFalse(primary_cfg.exists())
            self.assertTrue(backup_cfg.exists())

            recovered = json.loads(backup_cfg.read_text())
            primary_cfg.write_text(json.dumps(recovered, indent=2))
            os.chmod(str(primary_cfg), 0o600)

            self.assertTrue(primary_cfg.exists())
            self.assertEqual(primary_cfg.stat().st_mode & 0o777, 0o600)
            reloaded = json.loads(primary_cfg.read_text())
            self.assertEqual(reloaded["telegram_bot_token"], "8996841045:AAEmznTestToken")


if __name__ == "__main__":
    unittest.main()
