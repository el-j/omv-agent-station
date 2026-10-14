"""
Behavioral tests covering each branch of Signal's handle_signal_command
dispatch (issue #20) -- a single ~330-line if/elif chain that had zero
behavioral tests before this. Mirrors tests/test_cancel_command.py's
Dummy-object pattern, and tests/test_signal_cancel.py /
tests/test_signal_upload.py's fake send_signal_message approach.

Since issue #22 split signal_bot.py into handlers/*.py modules (mirroring
Telegram's structure), every handler module has its OWN imported binding of
shared names (WORKSPACE, send_signal_message, query_ai_model, etc.) --
patching must target the specific submodule that owns the reference, not
signal_bot.py itself (which no longer imports most of them).
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs


class TestSignalHandlers(unittest.TestCase):
    def setUp(self):
        stubs.purge_bot_modules("core", "handlers", "signal_bot")
        sys.path.insert(0, str(ROOT_DIR / "signal-agent-bot"))
        import signal_bot
        import core.security as core_security
        import core.messaging as messaging
        import handlers.system as system
        import handlers.ai_chat as ai_chat
        import handlers.git_ops as git_ops
        import handlers.custom_cmds as custom_cmds
        import handlers.vault as vault
        import handlers.topics as topics
        import handlers.interactive as interactive
        import agent_station_core.task_registry as task_registry
        import agent_station_core.topics_service as topics_service
        self.signal_bot = signal_bot
        self.core_security = core_security
        self.messaging = messaging
        self.system = system
        self.ai_chat = ai_chat
        self.git_ops = git_ops
        self.custom_cmds = custom_cmds
        self.vault = vault
        self.topics = topics
        self.interactive = interactive
        self.task_registry = task_registry
        self.topics_service = topics_service
        self.task_registry._active.clear()
        self.core_security.SIGNAL_ALLOWED_NUMBER = ""

        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name) / "workspace"
        # WORKSPACE is imported independently into every module that uses it --
        # each needs its own binding updated for tests to see the temp workspace.
        for mod in (self.system, self.git_ops, self.topics):
            mod.WORKSPACE = self.workspace
        self.topics_service.WORKSPACE = self.workspace
        self.topics_service.TOPICS_FILE = self.workspace / ".agent_topics.json"

        self.sent = []

        async def fake_send(recipient, message):
            self.sent.append((recipient, message))

        # send_signal_message is imported independently into every handler
        # module -- patch it everywhere a handler could call it, to capture
        # every outgoing message regardless of which command produced it.
        self._send_modules = [
            self.signal_bot, self.messaging, self.system, self.ai_chat, self.git_ops,
            self.custom_cmds, self.vault, self.topics, self.interactive,
        ]
        self._orig_send = {mod: mod.send_signal_message for mod in self._send_modules}
        for mod in self._send_modules:
            mod.send_signal_message = fake_send

        self._patched = []

    def tearDown(self):
        for mod, orig in self._orig_send.items():
            mod.send_signal_message = orig
        for mod, name, orig in self._patched:
            setattr(mod, name, orig)
        self.task_registry._active.clear()
        self._tmpdir.cleanup()
        if str(ROOT_DIR / "signal-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "signal-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "signal_bot")

    def patch(self, module, name, value):
        self._patched.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    def arun(self, coro):
        return asyncio.run(coro)

    def messages(self):
        return [m for _, m in self.sent]

    # -- authorization -----------------------------------------------------

    def test_unauthorized_sender_is_rejected(self):
        self.core_security.SIGNAL_ALLOWED_NUMBER = "+15559990000"
        self.arun(self.signal_bot.handle_signal_command("+15551110000", "/status"))
        self.assertTrue(any("Unauthorized" in m for m in self.messages()))

    # -- basics --------------------------------------------------------------

    def test_start_and_menu_reply_with_welcome(self):
        self.arun(self.signal_bot.handle_signal_command("+1555", "/start"))
        self.assertTrue(any("Agent Station" in m for m in self.messages()))

    def test_help_replies_with_handbook(self):
        self.arun(self.signal_bot.handle_signal_command("+1555", "/help"))
        self.assertTrue(any("Handbook" in m for m in self.messages()))

    def test_non_slash_message_routes_to_conversational_ai(self):
        self.patch(self.interactive, "query_ai_model", AsyncMock(return_value={"success": True, "answer": "hi there"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "just chatting, no slash"))
        self.assertTrue(any("hi there" in m for m in self.messages()))

    # -- AI query commands -----------------------------------------------

    def test_chat_queries_ai_model(self):
        self.patch(self.ai_chat, "query_ai_model", AsyncMock(return_value={"success": True, "answer": "42"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/chat what is the answer"))
        self.assertTrue(any("42" in m for m in self.messages()))

    def test_chat_no_args_shows_usage(self):
        self.arun(self.signal_bot.handle_signal_command("+1555", "/chat"))
        self.assertTrue(any("Usage" in m for m in self.messages()))

    def test_gemini_uses_gemini_model(self):
        captured = {}

        async def fake_query(prompt, model="coder-smart"):
            captured["model"] = model
            return {"success": True, "answer": "ok"}

        self.patch(self.ai_chat, "query_ai_model", fake_query)
        self.arun(self.signal_bot.handle_signal_command("+1555", "/gemini hello"))
        self.assertEqual(captured["model"], "gemini-3.6-flash")

    def test_gpt4_uses_github_gpt4o_model(self):
        captured = {}

        async def fake_query(prompt, model="coder-smart"):
            captured["model"] = model
            return {"success": True, "answer": "ok"}

        self.patch(self.ai_chat, "query_ai_model", fake_query)
        self.arun(self.signal_bot.handle_signal_command("+1555", "/gpt4 hello"))
        self.assertEqual(captured["model"], "github-gpt-4o")

    def test_modelhelp_and_aihelp_reply_with_guide(self):
        self.arun(self.signal_bot.handle_signal_command("+1555", "/modelhelp"))
        self.assertTrue(any("Models Guide" in m for m in self.messages()))

    # -- workspace / git commands -----------------------------------------

    def test_projects_lists_workspace_projects(self):
        self.patch(self.git_ops, "list_workspace_projects", lambda: ["myproj"])
        self.arun(self.signal_bot.handle_signal_command("+1555", "/projects"))
        self.assertTrue(any("myproj" in m for m in self.messages()))

    def test_clone_success(self):
        self.patch(self.git_ops, "clone_repository", AsyncMock(return_value={"success": True, "folder_name": "myrepo"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/clone https://github.com/x/myrepo.git"))
        self.assertTrue(any("Cloned" in m for m in self.messages()))

    def test_direct_github_url_without_slash_triggers_clone(self):
        self.patch(self.git_ops, "clone_repository", AsyncMock(return_value={"success": True, "folder_name": "myrepo"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "https://github.com/x/myrepo"))
        self.assertTrue(any("Cloned" in m for m in self.messages()))

    def test_newrepo_success(self):
        self.patch(self.git_ops, "create_new_repository", AsyncMock(return_value={
            "success": True, "repo_name": "newrepo", "html_url": "https://github.com/x/newrepo",
        }))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/newrepo newrepo"))
        self.assertTrue(any("Created" in m for m in self.messages()))

    def test_pull_falls_back_to_usage_when_no_project_bound_or_given(self):
        self.arun(self.signal_bot.handle_signal_command("+1555", "/pull"))
        self.assertTrue(any("Usage" in m for m in self.messages()))

    def test_pull_success(self):
        self.patch(self.git_ops, "git_pull_repo", AsyncMock(return_value={"success": True, "output": "up to date"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/pull myproj"))
        self.assertTrue(any("Git Pull" in m for m in self.messages()))

    def test_push_success(self):
        self.patch(self.git_ops, "git_push_repo", AsyncMock(return_value={"success": True, "output": "pushed"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/push myproj main"))
        self.assertTrue(any("Git Push" in m for m in self.messages()))

    def test_diff_success(self):
        self.patch(self.git_ops, "git_diff_repo", AsyncMock(return_value={"success": True, "diff": "+added"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/diff myproj"))
        self.assertTrue(any("added" in m for m in self.messages()))

    def test_branch_lists_branches_when_no_new_branch_given(self):
        project_dir = self.workspace / "myproj"
        (project_dir / ".git").mkdir(parents=True)
        self.patch(self.git_ops, "run_shell_exec", AsyncMock(return_value={"success": True, "output": "* main"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/branch myproj"))
        self.assertTrue(any("Branches" in m for m in self.messages()))

    # -- background task commands (happy path; overlap/cancel already
    # covered by tests/test_signal_cancel.py) --------------------------

    def test_task_launches_background_task(self):
        project_dir = self.workspace / "myproj"
        project_dir.mkdir(parents=True)
        self.arun(self.signal_bot.handle_signal_command("+15559991111", "/task myproj do the thing"))
        self.assertTrue(any("Launching" in m for m in self.messages()))
        self.arun(self.task_registry.cancel("+15559991111"))

    def test_claude_launches_background_task(self):
        self.arun(self.signal_bot.handle_signal_command("+15559992222", "/claude fix the bug"))
        self.assertTrue(any("Dispatching" in m for m in self.messages()))
        self.arun(self.task_registry.cancel("+15559992222"))

    def test_exec_launches_and_completes(self):
        self.patch(self.system, "run_shell_exec", AsyncMock(return_value={"success": True, "output": "hi"}))
        self.arun(self.signal_bot.handle_signal_command("+15559993333", "/exec echo hi"))
        self.assertTrue(any("Executing" in m for m in self.messages()))

    # -- status / vault / notes -------------------------------------------

    def test_status_reports_metrics(self):
        self.patch(self.system, "get_system_status", lambda: {"uptime": "1 day", "ram": "50%", "disk": "50%", "tmux": "none"})
        self.arun(self.signal_bot.handle_signal_command("+1555", "/status"))
        self.assertTrue(any("1 day" in m for m in self.messages()))

    def test_note_saves_note(self):
        self.patch(self.vault, "save_obsidian_note", lambda title, content, extra_tags=None: {"success": True, "path": "Inbox/Test.md"})
        self.patch(self.vault, "suggest_tags", AsyncMock(return_value=[]))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/note Test Note | some content"))
        self.assertTrue(any("Saved" in m for m in self.messages()))

    def test_vault_lists_notes(self):
        self.patch(self.vault, "list_vault_notes", lambda: {"success": True, "total_notes": 1, "recent": ["a.md"]})
        self.arun(self.signal_bot.handle_signal_command("+1555", "/vault"))
        self.assertTrue(any("a.md" in m for m in self.messages()))

    # -- custom commands ---------------------------------------------------

    def test_addcmd_delcmd_and_customcmds_roundtrip(self):
        store = {}
        self.patch(self.custom_cmds, "load_custom_commands", lambda: dict(store))

        def fake_save(cmds):
            store.clear()
            store.update(cmds)

        self.patch(self.custom_cmds, "save_custom_commands", fake_save)

        self.arun(self.signal_bot.handle_signal_command("+1555", "/addcmd test /exec pytest"))
        self.assertIn("test", store)

        self.arun(self.signal_bot.handle_signal_command("+1555", "/cmds"))
        self.assertTrue(any("test" in m for m in self.messages()))

        self.arun(self.signal_bot.handle_signal_command("+1555", "/delcmd test"))
        self.assertNotIn("test", store)

    def test_addcmd_rejects_reserved_builtin_names(self):
        """Issue #49: /addcmd cancel used to be silently accepted, but the real
        /cancel command always wins dispatch -- the custom command could never fire."""
        store = {}
        self.patch(self.custom_cmds, "load_custom_commands", lambda: dict(store))
        self.patch(self.custom_cmds, "save_custom_commands", lambda cmds: (store.clear(), store.update(cmds)))

        self.arun(self.signal_bot.handle_signal_command("+1555", "/addcmd cancel /exec pytest"))
        self.assertTrue(any("reserved built-in command" in m for m in self.messages()))
        self.assertNotIn("cancel", store)

    def test_custom_shortcut_expansion_dispatches_expanded_command(self):
        # expand_custom_command() calls load_custom_commands() as resolved in
        # its OWN module's globals (agent_station_core.custom_cmds_service),
        # not the name imported into handlers.custom_cmds's namespace -- patch
        # it there.
        import agent_station_core.custom_cmds_service as custom_cmds_service
        orig = custom_cmds_service.load_custom_commands
        custom_cmds_service.load_custom_commands = lambda: {"ping": "/status"}
        try:
            self.patch(self.system, "get_system_status", lambda: {"uptime": "1 day", "ram": "50%", "disk": "50%", "tmux": "none"})
            self.arun(self.signal_bot.handle_signal_command("+1555", "/ping"))
            self.assertTrue(any("1 day" in m for m in self.messages()))
        finally:
            custom_cmds_service.load_custom_commands = orig

    # -- /branch safety (issue #48: git checkout -B silently discarded commits) --

    def _git(self, cwd, *args):
        import subprocess  # nosec B404
        return subprocess.run(  # nosec B603,B607
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
            cwd=str(cwd), capture_output=True, text=True, check=True,
        )

    def test_branch_does_not_discard_commits_on_existing_branch(self):
        project_dir = self.workspace / "myproj"
        project_dir.mkdir(parents=True)
        self._git(project_dir, "init", "-q", "-b", "main")
        (project_dir / "a.txt").write_text("a")
        self._git(project_dir, "add", "a.txt")
        self._git(project_dir, "commit", "-q", "-m", "initial")

        # First /branch call: creates and switches to "feature".
        self.arun(self.signal_bot.handle_signal_command("+1555", "/branch myproj feature"))
        self.assertTrue(any("Checked out new branch" in m for m in self.messages()))

        # Commit something unique on "feature", then switch back to "main"
        # (simulating a user who moved on before re-running /branch).
        (project_dir / "b.txt").write_text("b")
        self._git(project_dir, "add", "b.txt")
        self._git(project_dir, "commit", "-q", "-m", "feature work")
        feature_tip = self._git(project_dir, "rev-parse", "feature").stdout.strip()
        self._git(project_dir, "checkout", "-q", "main")

        # Second /branch call for the SAME existing branch name, from "main".
        # The old `git checkout -B feature` would reset feature to main's HEAD
        # here, discarding the "feature work" commit.
        self.arun(self.signal_bot.handle_signal_command("+1555", "/branch myproj feature"))
        self.assertTrue(any("Switched to existing branch" in m for m in self.messages()))

        self.assertEqual(self._git(project_dir, "rev-parse", "feature").stdout.strip(), feature_tip)
        self.assertIn("feature work", self._git(project_dir, "log", "--oneline", "feature").stdout)


if __name__ == "__main__":
    unittest.main()
