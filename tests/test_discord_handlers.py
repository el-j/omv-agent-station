"""
Behavioral tests for Discord command handlers (issue #20). Prior to this,
only is_authorized had any test -- none of chat_cmd, clone_cmd, pull_cmd,
etc. had a test exercising their actual logic, so a correctness bug in any
of them (like the /bind message-id bug fixed in PR #11) could ship
silently. Mirrors tests/test_cancel_command.py's Dummy-object pattern.
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


class DummyChannel:
    def __init__(self, cid=1):
        self.id = cid


class DummyAuthor:
    def __init__(self, uid="1"):
        self.id = uid


class DummyMessage:
    edits = None


class DummyReplyMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, content=None, **kwargs):
        self.edits.append(content)


class DummyCtx:
    def __init__(self, channel_id=1, uid="1"):
        self.channel = DummyChannel(channel_id)
        self.author = DummyAuthor(uid)
        self.replies = []
        self.reply_messages = []

    async def reply(self, content=None, **kwargs):
        self.replies.append(content)
        msg = DummyReplyMessage()
        self.reply_messages.append(msg)
        return msg

    def all_edits(self):
        """Every edit() call made on any message this ctx has replied with,
        flattened -- covers the reply-then-edit pattern most handlers use."""
        return [e for msg in self.reply_messages for e in msg.edits]


class TestDiscordHandlers(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "discord-agent-bot"))
        import discord_bot
        import agent_station_core.task_registry as task_registry
        import agent_station_core.topics_service as topics_service
        self.discord_bot = discord_bot
        self.task_registry = task_registry
        self.topics_service = topics_service
        self.task_registry._active.clear()
        self.discord_bot.ALLOWED_USER_ID = None

        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name) / "workspace"
        self.discord_bot.WORKSPACE = self.workspace
        self.topics_service.WORKSPACE = self.workspace
        self.topics_service.TOPICS_FILE = self.workspace / ".agent_topics.json"

        self._patched = {}

    def tearDown(self):
        for name, orig in self._patched.items():
            setattr(self.discord_bot, name, orig)
        self.task_registry._active.clear()
        self._tmpdir.cleanup()
        if str(ROOT_DIR / "discord-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "discord-agent-bot"))

    def patch(self, name, value):
        if name not in self._patched:
            self._patched[name] = getattr(self.discord_bot, name)
        setattr(self.discord_bot, name, value)

    def arun(self, coro):
        return asyncio.run(coro)

    # -- basics --------------------------------------------------------

    def test_start_cmd_replies_with_welcome(self):
        ctx = DummyCtx()
        self.arun(self.discord_bot.start_cmd(ctx))
        self.assertTrue(any("Agent Station" in r for r in ctx.replies))

    def test_help_cmd_replies_with_handbook(self):
        ctx = DummyCtx()
        self.arun(self.discord_bot.help_cmd(ctx))
        self.assertTrue(any("Handbook" in r for r in ctx.replies))

    # -- AI query commands -----------------------------------------------

    def test_chat_cmd_queries_ai_model_and_replies_with_answer(self):
        self.patch("query_ai_model", AsyncMock(return_value={"success": True, "answer": "42"}))
        ctx = DummyCtx()
        self.arun(self.discord_bot.chat_cmd(ctx, message="what is the answer"))
        # chat_cmd sends a placeholder reply, then edits it with the answer.
        self.assertTrue(any("Querying" in r for r in ctx.replies))
        self.assertTrue(any("42" in e for e in ctx.all_edits()))

    def test_chat_cmd_no_message_shows_usage(self):
        ctx = DummyCtx()
        self.arun(self.discord_bot.chat_cmd(ctx, message=""))
        self.assertTrue(any("Usage" in r for r in ctx.replies))

    def test_gemini_cmd_delegates_to_chat_with_gemini_model(self):
        captured = {}

        async def fake_query(prompt, model="coder-smart"):
            captured["model"] = model
            captured["prompt"] = prompt
            return {"success": True, "answer": "ok"}

        self.patch("query_ai_model", fake_query)
        ctx = DummyCtx()
        self.arun(self.discord_bot.gemini_cmd(ctx, prompt="hello"))
        self.assertEqual(captured["model"], "gemini-3.6-flash")

    def test_gpt4_cmd_delegates_to_chat_with_github_gpt4o_model(self):
        captured = {}

        async def fake_query(prompt, model="coder-smart"):
            captured["model"] = model
            return {"success": True, "answer": "ok"}

        self.patch("query_ai_model", fake_query)
        ctx = DummyCtx()
        self.arun(self.discord_bot.gpt4_cmd(ctx, prompt="hello"))
        self.assertEqual(captured["model"], "github-gpt-4o")

    # -- workspace / git commands -----------------------------------------

    def test_projects_cmd_lists_workspace_projects(self):
        self.patch("list_workspace_projects", lambda: ["myproj", "otherproj"])
        ctx = DummyCtx()
        self.arun(self.discord_bot.projects_cmd(ctx))
        self.assertTrue(any("myproj" in r for r in ctx.replies))

    def test_projects_cmd_empty_workspace(self):
        self.patch("list_workspace_projects", lambda: [])
        ctx = DummyCtx()
        self.arun(self.discord_bot.projects_cmd(ctx))
        self.assertTrue(any("No workspace projects" in r for r in ctx.replies))

    def test_clone_cmd_success(self):
        self.patch("clone_repository", AsyncMock(return_value={"success": True, "folder_name": "myrepo"}))
        ctx = DummyCtx()
        self.arun(self.discord_bot.clone_cmd(ctx, git_url="https://github.com/x/myrepo.git"))
        self.assertTrue(any("Cloned" in e for e in ctx.all_edits()))

    def test_clone_cmd_no_url_shows_usage(self):
        ctx = DummyCtx()
        self.arun(self.discord_bot.clone_cmd(ctx))
        self.assertTrue(any("Usage" in r for r in ctx.replies))

    def test_newrepo_cmd_success(self):
        self.patch("create_new_repository", AsyncMock(return_value={
            "success": True, "repo_name": "newrepo", "html_url": "https://github.com/x/newrepo",
        }))
        ctx = DummyCtx()
        self.arun(self.discord_bot.newrepo_cmd(ctx, repo_name="newrepo"))
        self.assertTrue(any("Created" in e for e in ctx.all_edits()))

    def test_pull_cmd_requires_project(self):
        ctx = DummyCtx()
        self.arun(self.discord_bot.pull_cmd(ctx, project_name=""))
        self.assertTrue(any("Usage" in r for r in ctx.replies))

    def test_pull_cmd_success(self):
        self.patch("git_pull_repo", AsyncMock(return_value={"success": True, "output": "Already up to date."}))
        ctx = DummyCtx()
        self.arun(self.discord_bot.pull_cmd(ctx, project_name="myproj"))
        self.assertTrue(any("Git Pull" in e for e in ctx.all_edits()))

    def test_push_cmd_success(self):
        self.patch("git_push_repo", AsyncMock(return_value={"success": True, "output": "pushed"}))
        ctx = DummyCtx()
        self.arun(self.discord_bot.push_cmd(ctx, project_name="myproj", branch="main"))
        self.assertTrue(any("Git Push" in e for e in ctx.all_edits()))

    def test_diff_cmd_success(self):
        self.patch("git_diff_repo", AsyncMock(return_value={"success": True, "diff": "+added line"}))
        ctx = DummyCtx()
        self.arun(self.discord_bot.diff_cmd(ctx, project_name="myproj"))
        self.assertTrue(any("added line" in r for r in ctx.replies))

    def test_branch_cmd_lists_branches_when_no_name_given(self):
        project_dir = self.workspace / "myproj"
        (project_dir / ".git").mkdir(parents=True)
        self.patch("run_shell_exec", AsyncMock(return_value={"success": True, "output": "* main"}))
        ctx = DummyCtx()
        self.arun(self.discord_bot.branch_cmd(ctx, project_name="myproj"))
        self.assertTrue(any("Branches" in r for r in ctx.replies))

    def test_branch_cmd_invalid_project_rejected(self):
        ctx = DummyCtx()
        self.arun(self.discord_bot.branch_cmd(ctx, project_name="doesnotexist"))
        self.assertTrue(any("not a valid git repository" in r for r in ctx.replies))

    # -- background task commands (happy path; overlap/cancel already
    # covered by tests/test_discord_cancel.py) --------------------------

    def test_task_cmd_launches_background_task(self):
        project_dir = self.workspace / "myproj"
        project_dir.mkdir(parents=True)
        ctx = DummyCtx(channel_id=999)
        self.arun(self.discord_bot.task_cmd(ctx, args_str="myproj do the thing"))
        self.assertTrue(any("Launching" in r for r in ctx.replies))
        self.arun(self.task_registry.cancel("999", None))

    def test_task_cmd_missing_instructions_shows_usage(self):
        ctx = DummyCtx()
        self.arun(self.discord_bot.task_cmd(ctx, args_str=""))
        self.assertTrue(any("Usage" in r for r in ctx.replies))

    def test_claude_cmd_launches_background_task(self):
        ctx = DummyCtx(channel_id=998)
        self.arun(self.discord_bot.claude_cmd(ctx, prompt="fix the bug"))
        self.assertTrue(any("Dispatching" in r for r in ctx.replies))
        self.arun(self.task_registry.cancel("998", None))

    def test_exec_cmd_launches_and_completes(self):
        self.patch("run_shell_exec", AsyncMock(return_value={"success": True, "output": "hi"}))
        ctx = DummyCtx(channel_id=997)
        self.arun(self.discord_bot.exec_cmd(ctx, shell_cmd="echo hi"))
        self.assertTrue(any("Executing" in r for r in ctx.replies))

    # -- status / vault / notes -------------------------------------------

    def test_status_cmd_reports_metrics(self):
        self.patch("get_system_status", lambda: {"uptime": "1 day", "ram": "1024 MB used of 2048 MB (50%)", "disk": "50% used", "tmux": "none"})
        ctx = DummyCtx()
        self.arun(self.discord_bot.status_cmd(ctx))
        self.assertTrue(any("1 day" in r for r in ctx.replies))

    def test_note_cmd_saves_note(self):
        self.patch("save_obsidian_note", lambda title, content: {"success": True, "path": "Inbox/Test.md"})
        ctx = DummyCtx()
        self.arun(self.discord_bot.note_cmd(ctx, note_text="Test Note | some content"))
        self.assertTrue(any("Saved" in r for r in ctx.replies))

    def test_vault_cmd_lists_notes(self):
        self.patch("list_vault_notes", lambda: {"success": True, "total_notes": 2, "recent": ["a.md", "b.md"]})
        ctx = DummyCtx()
        self.arun(self.discord_bot.vault_cmd(ctx))
        self.assertTrue(any("a.md" in r for r in ctx.replies))

    # -- custom commands ---------------------------------------------------

    def test_addcmd_and_delcmd_and_customcmds_roundtrip(self):
        store = {}
        self.patch("load_custom_commands", lambda: dict(store))

        def fake_save(cmds):
            store.clear()
            store.update(cmds)

        self.patch("save_custom_commands", fake_save)

        ctx = DummyCtx()
        self.arun(self.discord_bot.addcmd_cmd(ctx, name="test", template="/exec pytest"))
        self.assertIn("test", store)

        ctx2 = DummyCtx()
        self.arun(self.discord_bot.customcmds_cmd(ctx2))
        self.assertTrue(any("test" in r for r in ctx2.replies))

        ctx3 = DummyCtx()
        self.arun(self.discord_bot.delcmd_cmd(ctx3, name="test"))
        self.assertNotIn("test", store)

    # -- topic binding -------------------------------------------------------

    def test_bind_cmd_rejects_unknown_project(self):
        ctx = DummyCtx()
        self.arun(self.discord_bot.bind_cmd(ctx, project_name="doesnotexist"))
        self.assertTrue(any("not found" in r for r in ctx.replies))

    def test_unbind_cmd_clears_binding(self):
        ctx = DummyCtx(channel_id=555)
        self.topics_service.set_bound_project("555", None, "myproj")
        self.arun(self.discord_bot.unbind_cmd(ctx))
        self.assertIsNone(self.topics_service.get_bound_project("555", None))


if __name__ == "__main__":
    unittest.main()
