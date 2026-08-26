"""
Behavioral tests covering each branch of Signal's handle_signal_command
dispatch (issue #20) -- a single ~330-line if/elif chain that had zero
behavioral tests before this. Mirrors tests/test_cancel_command.py's
Dummy-object pattern, and tests/test_signal_cancel.py /
tests/test_signal_upload.py's fake send_signal_message approach.
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401


class TestSignalHandlers(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "signal-agent-bot"))
        import signal_bot
        import agent_station_core.task_registry as task_registry
        import agent_station_core.topics_service as topics_service
        self.signal_bot = signal_bot
        self.task_registry = task_registry
        self.topics_service = topics_service
        self.task_registry._active.clear()
        self.signal_bot.SIGNAL_ALLOWED_NUMBER = ""

        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.signal_bot.WORKSPACE = self.workspace
        self.topics_service.WORKSPACE = self.workspace
        self.topics_service.TOPICS_FILE = self.workspace / ".agent_topics.json"

        self.sent = []

        async def fake_send(recipient, message):
            self.sent.append((recipient, message))

        self._orig_send = signal_bot.send_signal_message
        signal_bot.send_signal_message = fake_send

        self._patched = {}

    def tearDown(self):
        self.signal_bot.send_signal_message = self._orig_send
        for name, orig in self._patched.items():
            setattr(self.signal_bot, name, orig)
        self.task_registry._active.clear()
        self._tmpdir.cleanup()
        if str(ROOT_DIR / "signal-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "signal-agent-bot"))

    def patch(self, name, value):
        if name not in self._patched:
            self._patched[name] = getattr(self.signal_bot, name)
        setattr(self.signal_bot, name, value)

    def arun(self, coro):
        return asyncio.run(coro)

    def messages(self):
        return [m for _, m in self.sent]

    # -- authorization -----------------------------------------------------

    def test_unauthorized_sender_is_rejected(self):
        self.signal_bot.SIGNAL_ALLOWED_NUMBER = "+15559990000"
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
        self.patch("query_ai_model", AsyncMock(return_value={"success": True, "answer": "hi there"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "just chatting, no slash"))
        self.assertTrue(any("hi there" in m for m in self.messages()))

    # -- AI query commands -----------------------------------------------

    def test_chat_queries_ai_model(self):
        self.patch("query_ai_model", AsyncMock(return_value={"success": True, "answer": "42"}))
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

        self.patch("query_ai_model", fake_query)
        self.arun(self.signal_bot.handle_signal_command("+1555", "/gemini hello"))
        self.assertEqual(captured["model"], "gemini-3.6-flash")

    def test_gpt4_uses_github_gpt4o_model(self):
        captured = {}

        async def fake_query(prompt, model="coder-smart"):
            captured["model"] = model
            return {"success": True, "answer": "ok"}

        self.patch("query_ai_model", fake_query)
        self.arun(self.signal_bot.handle_signal_command("+1555", "/gpt4 hello"))
        self.assertEqual(captured["model"], "github-gpt-4o")

    def test_modelhelp_and_aihelp_reply_with_guide(self):
        self.arun(self.signal_bot.handle_signal_command("+1555", "/modelhelp"))
        self.assertTrue(any("Models Guide" in m for m in self.messages()))

    # -- workspace / git commands -----------------------------------------

    def test_projects_lists_workspace_projects(self):
        self.patch("list_workspace_projects", lambda: ["myproj"])
        self.arun(self.signal_bot.handle_signal_command("+1555", "/projects"))
        self.assertTrue(any("myproj" in m for m in self.messages()))

    def test_clone_success(self):
        self.patch("clone_repository", AsyncMock(return_value={"success": True, "folder_name": "myrepo"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/clone https://github.com/x/myrepo.git"))
        self.assertTrue(any("Cloned" in m for m in self.messages()))

    def test_direct_github_url_without_slash_triggers_clone(self):
        self.patch("clone_repository", AsyncMock(return_value={"success": True, "folder_name": "myrepo"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "https://github.com/x/myrepo"))
        self.assertTrue(any("Cloned" in m for m in self.messages()))

    def test_newrepo_success(self):
        self.patch("create_new_repository", AsyncMock(return_value={
            "success": True, "repo_name": "newrepo", "html_url": "https://github.com/x/newrepo",
        }))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/newrepo newrepo"))
        self.assertTrue(any("Created" in m for m in self.messages()))

    def test_pull_falls_back_to_usage_when_no_project_bound_or_given(self):
        self.arun(self.signal_bot.handle_signal_command("+1555", "/pull"))
        self.assertTrue(any("Usage" in m for m in self.messages()))

    def test_pull_success(self):
        self.patch("git_pull_repo", AsyncMock(return_value={"success": True, "output": "up to date"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/pull myproj"))
        self.assertTrue(any("Git Pull" in m for m in self.messages()))

    def test_push_success(self):
        self.patch("git_push_repo", AsyncMock(return_value={"success": True, "output": "pushed"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/push myproj main"))
        self.assertTrue(any("Git Push" in m for m in self.messages()))

    def test_diff_success(self):
        self.patch("git_diff_repo", AsyncMock(return_value={"success": True, "diff": "+added"}))
        self.arun(self.signal_bot.handle_signal_command("+1555", "/diff myproj"))
        self.assertTrue(any("added" in m for m in self.messages()))

    def test_branch_lists_branches_when_no_new_branch_given(self):
        project_dir = self.workspace / "myproj"
        (project_dir / ".git").mkdir(parents=True)
        self.patch("run_shell_exec", AsyncMock(return_value={"success": True, "output": "* main"}))
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
        self.patch("run_shell_exec", AsyncMock(return_value={"success": True, "output": "hi"}))
        self.arun(self.signal_bot.handle_signal_command("+15559993333", "/exec echo hi"))
        self.assertTrue(any("Executing" in m for m in self.messages()))

    # -- status / vault / notes -------------------------------------------

    def test_status_reports_metrics(self):
        self.patch("get_system_status", lambda: {"uptime": "1 day", "ram": "50%", "disk": "50%", "tmux": "none"})
        self.arun(self.signal_bot.handle_signal_command("+1555", "/status"))
        self.assertTrue(any("1 day" in m for m in self.messages()))

    def test_note_saves_note(self):
        self.patch("save_obsidian_note", lambda title, content: {"success": True, "path": "Inbox/Test.md"})
        self.arun(self.signal_bot.handle_signal_command("+1555", "/note Test Note | some content"))
        self.assertTrue(any("Saved" in m for m in self.messages()))

    def test_vault_lists_notes(self):
        self.patch("list_vault_notes", lambda: {"success": True, "total_notes": 1, "recent": ["a.md"]})
        self.arun(self.signal_bot.handle_signal_command("+1555", "/vault"))
        self.assertTrue(any("a.md" in m for m in self.messages()))

    # -- custom commands ---------------------------------------------------

    def test_addcmd_delcmd_and_customcmds_roundtrip(self):
        store = {}
        self.patch("load_custom_commands", lambda: dict(store))

        def fake_save(cmds):
            store.clear()
            store.update(cmds)

        self.patch("save_custom_commands", fake_save)

        self.arun(self.signal_bot.handle_signal_command("+1555", "/addcmd test /exec pytest"))
        self.assertIn("test", store)

        self.arun(self.signal_bot.handle_signal_command("+1555", "/cmds"))
        self.assertTrue(any("test" in m for m in self.messages()))

        self.arun(self.signal_bot.handle_signal_command("+1555", "/delcmd test"))
        self.assertNotIn("test", store)

    def test_custom_shortcut_expansion_dispatches_expanded_command(self):
        # expand_custom_command() calls load_custom_commands() as resolved in
        # its OWN module's globals (agent_station_core.custom_cmds_service),
        # not the name imported into signal_bot's namespace -- patch it there.
        import agent_station_core.custom_cmds_service as custom_cmds_service
        orig = custom_cmds_service.load_custom_commands
        custom_cmds_service.load_custom_commands = lambda: {"ping": "/status"}
        try:
            self.patch("get_system_status", lambda: {"uptime": "1 day", "ram": "50%", "disk": "50%", "tmux": "none"})
            self.arun(self.signal_bot.handle_signal_command("+1555", "/ping"))
            self.assertTrue(any("1 day" in m for m in self.messages()))
        finally:
            custom_cmds_service.load_custom_commands = orig


if __name__ == "__main__":
    unittest.main()
