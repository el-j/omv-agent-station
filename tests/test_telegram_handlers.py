"""
Behavioral tests for the Telegram bot's handlers/*.py modules (issue #51).

Telegram is the reference implementation the Discord and Signal bots were
mirrored from (issue #22), yet it was the only one of the three without a
dedicated handler test file -- handlers/git_ops.py sat at 6% line coverage
while its Discord/Signal counterparts were at ~75%. This file closes that
gap using the same pattern as tests/test_discord_handlers.py: import each
handler submodule directly, rebind the module-level constants it copied out
of core.config at import time (WORKSPACE, OBSIDIAN_VAULT, GIT_BIN, ...), and
drive the real coroutines with Dummy Update/Context objects.

Git-touching flows split two ways on purpose:
  * Local-only operations (branch/diff/pull/push) run against REAL temporary
    git repositories with a `git init --bare` local remote, so the assertions
    cover git's actual behavior rather than a mock's.
  * Network-touching operations (clone, newrepo's push to github.com) point
    GIT_BIN at a shim script that logs its argv, so no test ever reaches the
    network -- and the logged argv is itself asserted on, which is how the
    PAT-injection into the clone URL gets verified.
"""

import asyncio
import json
import os
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs


class DummyStatusMessage:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)
        return self


class DummyReplyTarget:
    """Stands in for the message a ForceReply prompt was answered to."""

    def __init__(self, text="", is_bot=True):
        self.text = text
        self.from_user = DummyUser("99", is_bot=is_bot)


class DummyMessage:
    def __init__(self, thread_id=None, text=None, reply_to=None):
        self.message_thread_id = thread_id
        self.text = text
        self.reply_to_message = reply_to
        self.replies = []
        self.status_messages = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        status = DummyStatusMessage()
        self.status_messages.append(status)
        return status


class DummyChat:
    def __init__(self, cid=1, chat_type="private"):
        self.id = cid
        self.type = chat_type


class DummyUser:
    def __init__(self, uid="1", is_bot=False):
        self.id = uid
        self.username = "tester"
        self.is_bot = is_bot


class DummyForumTopic:
    def __init__(self, thread_id=77):
        self.message_thread_id = thread_id


class DummyBot:
    def __init__(self, topic_error=None):
        self.topic_error = topic_error
        self.created_topics = []

    async def create_forum_topic(self, chat_id, name):
        if self.topic_error:
            raise RuntimeError(self.topic_error)
        self.created_topics.append((chat_id, name))
        return DummyForumTopic()

    async def set_my_commands(self, *args, **kwargs):
        return True


class DummyQuery:
    def __init__(self, data=""):
        self.data = data
        self.answered = False
        self.texts = []

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self.texts.append(text)


class DummyUpdate:
    def __init__(self, cid=1, thread_id=None, uid="1", chat_type="private",
                 text=None, reply_to=None, query=None):
        self.effective_chat = DummyChat(cid, chat_type)
        self.effective_message = DummyMessage(thread_id, text=text, reply_to=reply_to)
        self.effective_user = DummyUser(uid)
        self.callback_query = query

    def replies(self):
        return self.effective_message.replies

    def all_edits(self):
        return [e for m in self.effective_message.status_messages for e in m.edits]


class DummyContext:
    def __init__(self, args=None, bot=None):
        self.args = args if args is not None else []
        self.bot = bot or DummyBot()


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient's async-context-manager API."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if self._error:
            raise self._error
        return self._response

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if self._error:
            raise self._error
        return self._response


class FakeHttpx:
    def __init__(self, client):
        self.AsyncClient = client


class FakeAIClient:
    """Stands in for core.git_auth.ai_client (an AsyncOpenAI instance)."""

    def __init__(self, answer=None, error=None):
        self._answer = answer
        self._error = error
        self.last_kwargs = None
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error:
            raise self._error

        class _Msg:
            content = self._answer

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class TelegramHandlerTestCase(unittest.TestCase):
    """Shared import/teardown machinery for every handler module under test."""

    def setUp(self):
        stubs.purge_bot_modules("core", "handlers", "ui", "bot")
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        import core.config as core_config
        import core.security as core_security
        import handlers.ai_chat as ai_chat
        import handlers.callbacks as callbacks
        import handlers.custom_cmds as custom_cmds
        import handlers.git_ops as git_ops
        import handlers.interactive as interactive
        import handlers.topics as topics
        import handlers.vault as vault
        self.core_config = core_config
        self.core_security = core_security
        self.ai_chat = ai_chat
        self.callbacks = callbacks
        self.custom_cmds = custom_cmds
        self.git_ops = git_ops
        self.interactive = interactive
        self.topics = topics
        self.vault = vault

        self.core_security.ALLOWED_USER_ID = None

        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        self.obsidian = self.tmp / "obsidian"
        self.obsidian.mkdir()

        # WORKSPACE and friends are `from core.config import ...`-ed into each
        # handler module at import time, so every consumer needs its own
        # binding repointed at the temp dirs.
        for mod in (self.git_ops, self.topics, self.callbacks):
            mod.WORKSPACE = self.workspace
        self.vault.OBSIDIAN_VAULT = self.obsidian
        self.topics.TOPICS_FILE = self.workspace / ".agent_topics.json"
        self.custom_cmds.CUSTOM_CMDS_FILE = self.workspace / ".custom_commands.json"
        self.custom_cmds.OBSIDIAN_CMDS_FILE = self.obsidian / "Config" / "commands.json"

        self._patched = []

    def tearDown(self):
        for mod, name, orig in self._patched:
            setattr(mod, name, orig)
        self._tmpdir.cleanup()
        if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "ui", "bot")

    def patch(self, module, name, value):
        self._patched.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    def arun(self, coro):
        return asyncio.run(coro)

    # -- git helpers ----------------------------------------------------

    def git(self, cwd, *args):
        return subprocess.run(  # nosec B603,B607
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
            cwd=str(cwd), capture_output=True, text=True, check=True,
        )

    def make_repo(self, name="myproj", with_remote=False):
        """Creates a real git repo in the temp workspace, optionally wired to a
        local `git init --bare` remote so push/pull run for real without a network."""
        project = self.workspace / name
        project.mkdir(parents=True)
        self.git(project, "init", "-q", "-b", "main")
        (project / "README.md").write_text("hello\n")
        self.git(project, "add", ".")
        self.git(project, "commit", "-q", "-m", "initial")
        if with_remote:
            remote = self.tmp / f"{name}-remote.git"
            remote.mkdir()
            subprocess.run(  # nosec B603,B607
                ["git", "init", "-q", "--bare", "-b", "main", str(remote)],
                capture_output=True, text=True, check=True,
            )
            self.git(project, "remote", "add", "origin", str(remote))
            self.git(project, "push", "-q", "-u", "origin", "main")
        return project

    def fake_git_bin(self, exit_code=0, stderr_text=""):
        """Installs a shim in place of the real git binary that records every
        argv it is called with. Used for the flows that would otherwise reach
        github.com (clone, newrepo push) -- the recorded argv is what proves
        the PAT actually lands in the remote URL."""
        log = self.tmp / "git-argv.log"
        shim = self.tmp / "fakegit.sh"
        # A successful `clone` must leave the destination directory behind --
        # clone_cmd immediately runs `git config` with cwd=target_dir next.
        shim.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$*" >> "{log}"\n'
            f'if [ "$1" = "clone" ] && [ {exit_code} -eq 0 ]; then\n'
            '  for a in "$@"; do last="$a"; done\n'
            '  mkdir -p "$last"\n'
            "fi\n"
            f'[ -n "{stderr_text}" ] && printf "%s\\n" "{stderr_text}" >&2\n'
            f"exit {exit_code}\n"
        )
        os.chmod(shim, 0o755)  # nosec B103
        self.patch(self.git_ops, "GIT_BIN", str(shim))
        return log


class TestTelegramGitOps(TelegramHandlerTestCase):
    # -- /projects ------------------------------------------------------

    def test_projects_cmd_reports_missing_workspace(self):
        self.patch(self.git_ops, "WORKSPACE", self.tmp / "nope")
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.git_ops.projects_cmd(update, context))
        self.assertTrue(any("not mounted" in r for r in update.replies()))

    def test_projects_cmd_reports_empty_workspace(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.git_ops.projects_cmd(update, context))
        self.assertTrue(any("No projects found" in r for r in update.replies()))

    def test_projects_cmd_lists_projects_and_skips_dotfolders(self):
        (self.workspace / "alpha").mkdir()
        (self.workspace / "beta").mkdir()
        (self.workspace / ".hidden").mkdir()
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.git_ops.projects_cmd(update, context))
        body = "\n".join(update.replies())
        self.assertIn("alpha", body)
        self.assertIn("beta", body)
        self.assertNotIn(".hidden", body)

    # -- /newrepo -------------------------------------------------------

    def test_newrepo_cmd_without_args_prompts_for_name(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.git_ops.newrepo_cmd(update, context))
        self.assertTrue(any("Create New GitHub Repository" in r for r in update.replies()))

    def test_newrepo_cmd_rejects_invalid_repo_name(self):
        update, context = DummyUpdate(), DummyContext(args=["bad name!"])
        self.arun(self.git_ops.newrepo_cmd(update, context))
        self.assertTrue(any("Invalid repository name" in r for r in update.replies()))

    def test_newrepo_cmd_rejects_existing_directory(self):
        (self.workspace / "taken").mkdir()
        update, context = DummyUpdate(), DummyContext(args=["taken"])
        self.arun(self.git_ops.newrepo_cmd(update, context))
        self.assertTrue(any("already exists" in r for r in update.replies()))

    def test_newrepo_cmd_requires_github_token(self):
        self.patch(self.git_ops, "GITHUB_TOKEN", "")
        update, context = DummyUpdate(), DummyContext(args=["fresh"])
        self.arun(self.git_ops.newrepo_cmd(update, context))
        self.assertTrue(any("GITHUB_TOKEN" in r for r in update.replies()))

    def test_newrepo_cmd_success_scaffolds_repo_and_injects_pat_into_remote(self):
        self.patch(self.git_ops, "GITHUB_TOKEN", "ghp_testtoken")
        client = FakeAsyncClient(FakeResponse(201, {
            "clone_url": "https://github.com/tester/fresh.git",
            "html_url": "https://github.com/tester/fresh",
            "owner": {"login": "tester"},
        }))
        self.patch(self.git_ops, "httpx", FakeHttpx(client))
        log = self.fake_git_bin()

        update, context = DummyUpdate(), DummyContext(args=["fresh", "A", "test", "repo"])
        self.arun(self.git_ops.newrepo_cmd(update, context))

        self.assertTrue(any("New GitHub Repository Created" in e for e in update.all_edits()))
        project = self.workspace / "fresh"
        self.assertTrue((project / "README.md").exists())
        self.assertTrue((project / ".gitignore").exists())
        self.assertIn("A test repo", (project / "README.md").read_text())
        # The PAT must be baked into the origin URL -- that is the whole point
        # of the automated-credentials flow, and a silent regression here means
        # every push from the bot starts failing auth.
        argv = log.read_text()
        self.assertIn("remote add origin https://x-access-token:ghp_testtoken@github.com/tester/fresh.git", argv)
        # The description is what the user typed, not the generated default.
        self.assertEqual(client.calls[0][2]["json"]["description"], "A test repo")
        self.assertTrue(client.calls[0][2]["json"]["private"])

    def test_newrepo_cmd_surfaces_github_api_error(self):
        self.patch(self.git_ops, "GITHUB_TOKEN", "ghp_testtoken")
        client = FakeAsyncClient(FakeResponse(422, text="name already exists"))
        self.patch(self.git_ops, "httpx", FakeHttpx(client))
        update, context = DummyUpdate(), DummyContext(args=["fresh"])
        self.arun(self.git_ops.newrepo_cmd(update, context))
        self.assertTrue(any("GitHub API error (422)" in e for e in update.all_edits()))
        self.assertFalse((self.workspace / "fresh").exists())

    def test_newrepo_cmd_creates_and_binds_forum_topic_in_group_chat(self):
        self.patch(self.git_ops, "GITHUB_TOKEN", "ghp_testtoken")
        self.patch(self.git_ops, "httpx", FakeHttpx(FakeAsyncClient(FakeResponse(201, {
            "clone_url": "https://github.com/tester/fresh.git",
            "html_url": "https://github.com/tester/fresh",
            "owner": {"login": "tester"},
        }))))
        self.fake_git_bin()
        bot = DummyBot()
        update = DummyUpdate(cid=500, chat_type="supergroup")
        context = DummyContext(args=["fresh"], bot=bot)
        self.arun(self.git_ops.newrepo_cmd(update, context))
        self.assertEqual(bot.created_topics, [(500, "📂 fresh")])
        self.assertEqual(self.topics.get_bound_project(500, 77), "fresh")

    def test_newrepo_cmd_explains_missing_admin_rights_for_topic_creation(self):
        self.patch(self.git_ops, "GITHUB_TOKEN", "ghp_testtoken")
        self.patch(self.git_ops, "httpx", FakeHttpx(FakeAsyncClient(FakeResponse(201, {
            "clone_url": "https://github.com/tester/fresh.git",
            "html_url": "https://github.com/tester/fresh",
            "owner": {"login": "tester"},
        }))))
        self.fake_git_bin()
        update = DummyUpdate(cid=500, chat_type="supergroup")
        context = DummyContext(args=["fresh"], bot=DummyBot(topic_error="not enough rights"))
        self.arun(self.git_ops.newrepo_cmd(update, context))
        self.assertTrue(any("Administrator" in e for e in update.all_edits()))

    # -- /clone ---------------------------------------------------------

    def test_clone_cmd_without_args_prompts_for_url(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.git_ops.clone_cmd(update, context))
        self.assertTrue(any("Clone Git Repository" in r for r in update.replies()))

    def test_clone_cmd_rejects_malformed_url(self):
        update, context = DummyUpdate(), DummyContext(args=["not a url"])
        self.arun(self.git_ops.clone_cmd(update, context))
        self.assertTrue(any("Invalid git URL" in r for r in update.replies()))

    def test_clone_cmd_rejects_argument_injection_url(self):
        """A leading dash would be parsed by git as a flag, not a URL."""
        update, context = DummyUpdate(), DummyContext(args=["--upload-pack=evil"])
        self.arun(self.git_ops.clone_cmd(update, context))
        self.assertTrue(any("Invalid git URL" in r for r in update.replies()))

    def test_clone_cmd_rejects_existing_destination(self):
        (self.workspace / "repo").mkdir()
        update, context = DummyUpdate(), DummyContext(args=["https://github.com/owner/repo.git"])
        self.arun(self.git_ops.clone_cmd(update, context))
        self.assertTrue(any("already exists" in r for r in update.replies()))

    def test_clone_cmd_success_injects_pat_and_writes_obsidian_spec(self):
        self.patch(self.git_ops, "GITHUB_TOKEN", "ghp_clonetoken")
        log = self.fake_git_bin()
        update, context = DummyUpdate(), DummyContext(args=["https://github.com/owner/repo.git"])
        self.arun(self.git_ops.clone_cmd(update, context))

        self.assertTrue(any("Repository Cloned" in e for e in update.all_edits()))
        argv = log.read_text()
        self.assertIn("clone -- https://x-access-token:ghp_clonetoken@github.com/owner/repo.git", argv)
        self.assertTrue((self.obsidian / "Projects" / "repo" / "project-spec.md").exists())

    def test_clone_cmd_honors_explicit_folder_name(self):
        self.patch(self.git_ops, "GITHUB_TOKEN", "")
        log = self.fake_git_bin()
        update, context = DummyUpdate(), DummyContext(args=["https://github.com/owner/repo.git", "custom-dir"])
        self.arun(self.git_ops.clone_cmd(update, context))
        argv = log.read_text()
        self.assertIn("custom-dir", argv)
        # With no token configured the URL must be passed through untouched.
        self.assertIn("clone -- https://github.com/owner/repo.git", argv)

    def test_clone_cmd_reports_git_failure(self):
        self.patch(self.git_ops, "GITHUB_TOKEN", "")
        self.fake_git_bin(exit_code=128, stderr_text="repository not found")
        update, context = DummyUpdate(), DummyContext(args=["https://github.com/owner/repo.git"])
        self.arun(self.git_ops.clone_cmd(update, context))
        edits = update.all_edits()
        self.assertTrue(any("Git clone failed" in e for e in edits))
        self.assertTrue(any("repository not found" in e for e in edits))

    # -- /pull, /push ---------------------------------------------------

    def test_pull_cmd_without_project_shows_usage(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.git_ops.pull_cmd(update, context))
        self.assertTrue(any("Usage" in r for r in update.replies()))

    def test_pull_cmd_rejects_non_repository(self):
        (self.workspace / "plain").mkdir()
        update, context = DummyUpdate(), DummyContext(args=["plain"])
        self.arun(self.git_ops.pull_cmd(update, context))
        self.assertTrue(any("not a valid git repository" in r for r in update.replies()))

    def test_pull_cmd_success_against_real_remote(self):
        self.make_repo("myproj", with_remote=True)
        update, context = DummyUpdate(), DummyContext(args=["myproj"])
        self.arun(self.git_ops.pull_cmd(update, context))
        self.assertTrue(any("Git Pull Successful" in e for e in update.all_edits()))

    def test_pull_cmd_reports_failure_when_no_remote_configured(self):
        self.make_repo("lonely")
        update, context = DummyUpdate(), DummyContext(args=["lonely"])
        self.arun(self.git_ops.pull_cmd(update, context))
        self.assertTrue(any("Git Pull Failed" in e for e in update.all_edits()))

    def test_push_cmd_success_against_real_remote(self):
        project = self.make_repo("myproj", with_remote=True)
        (project / "new.txt").write_text("x")
        self.git(project, "add", ".")
        self.git(project, "commit", "-q", "-m", "second")

        update, context = DummyUpdate(), DummyContext(args=["myproj"])
        self.arun(self.git_ops.push_cmd(update, context))
        self.assertTrue(any("Git Push Successful" in e for e in update.all_edits()))

        remote = self.tmp / "myproj-remote.git"
        log = subprocess.run(  # nosec B603,B607
            ["git", "log", "--oneline", "main"], cwd=str(remote),
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("second", log)

    def test_push_cmd_rejects_invalid_branch_name(self):
        self.make_repo("myproj", with_remote=True)
        update, context = DummyUpdate(), DummyContext(args=["myproj", "--force"])
        self.arun(self.git_ops.push_cmd(update, context))
        self.assertTrue(any("Invalid branch name" in r for r in update.replies()))

    def test_push_cmd_reports_failure_when_no_remote_configured(self):
        self.make_repo("lonely")
        update, context = DummyUpdate(), DummyContext(args=["lonely"])
        self.arun(self.git_ops.push_cmd(update, context))
        self.assertTrue(any("Git Push Failed" in e for e in update.all_edits()))

    # -- /branch --------------------------------------------------------

    def test_branch_cmd_lists_branches(self):
        project = self.make_repo("myproj")
        self.git(project, "branch", "feature")
        update, context = DummyUpdate(), DummyContext(args=["myproj"])
        self.arun(self.git_ops.branch_cmd(update, context))
        body = "\n".join(update.replies())
        self.assertIn("Branches", body)
        self.assertIn("feature", body)

    def test_branch_cmd_creates_new_branch(self):
        project = self.make_repo("myproj")
        update, context = DummyUpdate(), DummyContext(args=["myproj", "feature"])
        self.arun(self.git_ops.branch_cmd(update, context))
        self.assertTrue(any("Checked out new branch" in r for r in update.replies()))
        head = self.git(project, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self.assertEqual(head, "feature")

    def test_branch_cmd_switches_to_existing_branch_without_discarding_commits(self):
        """Issue #48's regression guard, mirrored from the Discord suite: the
        second /branch call for an existing branch must switch, never reset."""
        project = self.make_repo("myproj")
        update1, context1 = DummyUpdate(), DummyContext(args=["myproj", "feature"])
        self.arun(self.git_ops.branch_cmd(update1, context1))

        (project / "b.txt").write_text("b")
        self.git(project, "add", ".")
        self.git(project, "commit", "-q", "-m", "feature work")
        tip = self.git(project, "rev-parse", "feature").stdout.strip()
        self.git(project, "checkout", "-q", "main")

        update2, context2 = DummyUpdate(), DummyContext(args=["myproj", "feature"])
        self.arun(self.git_ops.branch_cmd(update2, context2))
        self.assertTrue(any("Switched to existing branch" in r for r in update2.replies()))
        self.assertEqual(self.git(project, "rev-parse", "feature").stdout.strip(), tip)

    def test_branch_cmd_rejects_invalid_branch_name(self):
        self.make_repo("myproj")
        update, context = DummyUpdate(), DummyContext(args=["myproj", "--orphan"])
        self.arun(self.git_ops.branch_cmd(update, context))
        self.assertTrue(any("Invalid branch name" in r for r in update.replies()))

    def test_branch_cmd_reports_checkout_failure(self):
        self.make_repo("myproj")
        # Passes the bot's own sanitizer but git itself rejects a ".lock" suffix,
        # so both the create and the fallback-switch attempt fail.
        update, context = DummyUpdate(), DummyContext(args=["myproj", "feature.lock"])
        self.arun(self.git_ops.branch_cmd(update, context))
        self.assertTrue(any("Branch checkout failed" in r for r in update.replies()))

    def test_branch_cmd_without_project_shows_usage(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.git_ops.branch_cmd(update, context))
        self.assertTrue(any("Usage" in r for r in update.replies()))

    # -- /diff ----------------------------------------------------------

    def test_diff_cmd_reports_clean_tree(self):
        self.make_repo("myproj")
        update, context = DummyUpdate(), DummyContext(args=["myproj"])
        self.arun(self.git_ops.diff_cmd(update, context))
        self.assertTrue(any("Working tree clean" in r for r in update.replies()))

    def test_diff_cmd_shows_uncommitted_changes(self):
        project = self.make_repo("myproj")
        (project / "README.md").write_text("changed content\n")
        update, context = DummyUpdate(), DummyContext(args=["myproj"])
        self.arun(self.git_ops.diff_cmd(update, context))
        self.assertTrue(any("changed content" in r for r in update.replies()))

    def test_diff_cmd_truncates_oversized_diffs(self):
        project = self.make_repo("myproj")
        (project / "README.md").write_text("x" * 200 + "\n" + "\n".join(f"line {i}" for i in range(1000)))
        update, context = DummyUpdate(), DummyContext(args=["myproj"])
        self.arun(self.git_ops.diff_cmd(update, context))
        self.assertTrue(any("diff truncated" in r for r in update.replies()))

    def test_diff_cmd_without_project_shows_usage(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.git_ops.diff_cmd(update, context))
        self.assertTrue(any("Usage" in r for r in update.replies()))

    def test_git_commands_resolve_project_from_bound_topic(self):
        """In a bound forum topic the project name is implicit -- /diff with no
        args must still target the bound project."""
        project = self.make_repo("bound-proj")
        (project / "README.md").write_text("topic-inferred\n")
        self.topics.set_bound_project(42, 7, "bound-proj")
        update = DummyUpdate(cid=42, thread_id=7, chat_type="supergroup")
        self.arun(self.git_ops.diff_cmd(update, DummyContext()))
        self.assertTrue(any("topic-inferred" in r for r in update.replies()))


class TestTelegramCustomCmds(TelegramHandlerTestCase):
    def test_load_returns_empty_dict_when_file_missing(self):
        self.assertEqual(self.custom_cmds.load_custom_commands(), {})

    def test_load_tolerates_corrupt_json(self):
        self.custom_cmds.CUSTOM_CMDS_FILE.write_text("{not json")
        self.assertEqual(self.custom_cmds.load_custom_commands(), {})

    def test_save_persists_to_workspace_and_mirrors_to_obsidian(self):
        self.custom_cmds.save_custom_commands({"test": "/exec pytest"})
        self.assertEqual(
            json.loads(self.custom_cmds.CUSTOM_CMDS_FILE.read_text()),
            {"test": "/exec pytest"},
        )
        self.assertEqual(
            json.loads(self.custom_cmds.OBSIDIAN_CMDS_FILE.read_text()),
            {"test": "/exec pytest"},
        )

    def test_addcmd_without_enough_args_shows_usage(self):
        update, context = DummyUpdate(), DummyContext(args=["only-name"])
        self.arun(self.custom_cmds.addcmd_cmd(update, context))
        self.assertTrue(any("Usage" in r for r in update.replies()))

    def test_addcmd_rejects_invalid_name(self):
        update, context = DummyUpdate(), DummyContext(args=["bad-name!", "/exec", "ls"])
        self.arun(self.custom_cmds.addcmd_cmd(update, context))
        self.assertTrue(any("Invalid command name" in r for r in update.replies()))

    def test_addcmd_rejects_reserved_builtin(self):
        """Issue #49: a custom /cancel could never fire -- the built-in wins dispatch."""
        update, context = DummyUpdate(), DummyContext(args=["cancel", "/exec", "ls"])
        self.arun(self.custom_cmds.addcmd_cmd(update, context))
        self.assertTrue(any("reserved built-in command" in r for r in update.replies()))
        self.assertEqual(self.custom_cmds.load_custom_commands(), {})

    def test_addcmd_persists_and_customcmds_lists_it_and_delcmd_removes_it(self):
        update, context = DummyUpdate(), DummyContext(args=["test", "/exec", "pytest", "-v"])
        self.arun(self.custom_cmds.addcmd_cmd(update, context))
        self.assertEqual(self.custom_cmds.load_custom_commands(), {"test": "/exec pytest -v"})
        self.assertTrue(any("Custom Command Registered" in r for r in update.replies()))

        listing = DummyUpdate()
        self.arun(self.custom_cmds.customcmds_cmd(listing, DummyContext()))
        self.assertTrue(any("/test" in r for r in listing.replies()))

        removal = DummyUpdate()
        self.arun(self.custom_cmds.delcmd_cmd(removal, DummyContext(args=["test"])))
        self.assertEqual(self.custom_cmds.load_custom_commands(), {})
        self.assertTrue(any("Deleted custom command" in r for r in removal.replies()))

    def test_delcmd_without_args_shows_usage(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.custom_cmds.delcmd_cmd(update, context))
        self.assertTrue(any("Usage" in r for r in update.replies()))

    def test_delcmd_rejects_invalid_name(self):
        update, context = DummyUpdate(), DummyContext(args=["!!!"])
        self.arun(self.custom_cmds.delcmd_cmd(update, context))
        self.assertTrue(any("Invalid command name" in r for r in update.replies()))

    def test_delcmd_reports_unknown_command(self):
        update, context = DummyUpdate(), DummyContext(args=["ghost"])
        self.arun(self.custom_cmds.delcmd_cmd(update, context))
        self.assertTrue(any("does not exist" in r for r in update.replies()))

    def test_customcmds_reports_empty_state(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.custom_cmds.customcmds_cmd(update, context))
        self.assertTrue(any("No custom commands configured" in r for r in update.replies()))

    def test_dynamic_handler_ignores_unregistered_commands(self):
        update = DummyUpdate(text="/nothingregistered")
        self.arun(self.custom_cmds.dynamic_command_handler(update, DummyContext()))
        self.assertEqual(update.replies(), [])

    def test_dynamic_handler_ignores_plain_text(self):
        update = DummyUpdate(text="just talking")
        self.arun(self.custom_cmds.dynamic_command_handler(update, DummyContext()))
        self.assertEqual(update.replies(), [])

    def test_dynamic_handler_expands_args_placeholder_and_dispatches(self):
        self.custom_cmds.save_custom_commands({"review": "/chat Review this: {args}"})
        captured = {}

        async def fake_chat(update, context):
            captured["args"] = list(context.args)

        self.patch(self.ai_chat, "chat_cmd", fake_chat)
        update = DummyUpdate(text="/review my_module.py")
        self.arun(self.custom_cmds.dynamic_command_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["Review", "this:", "my_module.py"])

    def test_dynamic_handler_appends_args_when_no_placeholder(self):
        self.custom_cmds.save_custom_commands({"t": "/exec pytest"})
        captured = {}

        import handlers.system as system

        async def fake_exec(update, context):
            captured["args"] = list(context.args)

        self.patch(system, "exec_cmd", fake_exec)
        update = DummyUpdate(text="/t -v")
        self.arun(self.custom_cmds.dynamic_command_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["pytest", "-v"])

    def test_dynamic_handler_strips_bot_username_suffix(self):
        self.custom_cmds.save_custom_commands({"t": "/exec pytest"})
        captured = {}

        import handlers.system as system

        async def fake_exec(update, context):
            captured["hit"] = True

        self.patch(system, "exec_cmd", fake_exec)
        update = DummyUpdate(text="/t@agent_station_bot")
        self.arun(self.custom_cmds.dynamic_command_handler(update, DummyContext()))
        self.assertTrue(captured.get("hit"))

    def test_dynamic_handler_reports_unknown_target_handler(self):
        self.custom_cmds.save_custom_commands({"weird": "/notarealcommand"})
        update = DummyUpdate(text="/weird")
        self.arun(self.custom_cmds.dynamic_command_handler(update, DummyContext()))
        self.assertTrue(any("not found" in r for r in update.replies()))


class TestTelegramCallbacks(TelegramHandlerTestCase):
    def test_no_callback_query_is_a_noop(self):
        self.arun(self.callbacks.help_callback_handler(DummyUpdate(), DummyContext()))

    def test_help_menu_main_renders_topic_index(self):
        query = DummyQuery("help_menu:main")
        self.arun(self.callbacks.help_callback_handler(DummyUpdate(query=query), DummyContext()))
        self.assertTrue(query.answered)
        self.assertIn("Interactive Handbook", query.texts[0])

    def test_help_menu_submenus_each_render(self):
        for data, expected in [
            ("help_menu:models", "AI Models Guide"),
            ("btn_modelhelp", "AI Models Guide"),
            ("help_menu:agent", "Autonomous Coding Agent"),
            ("help_menu:git", "Git & Workspace Management"),
            ("help_menu:obsidian", "Obsidian Second-Brain"),
            ("help_menu:customcmds", "User-Defined Custom Commands"),
        ]:
            query = DummyQuery(data)
            self.arun(self.callbacks.help_callback_handler(DummyUpdate(query=query), DummyContext()))
            self.assertIn(expected, query.texts[0], f"callback_data={data}")

    def test_btn_models_lists_gateway_models(self):
        self.patch(self.callbacks, "httpx", FakeHttpx(FakeAsyncClient(
            FakeResponse(200, {"data": [{"id": "coder-smart"}, {"id": "gemini-3.6-flash"}]})
        )))
        query = DummyQuery("btn_models")
        self.arun(self.callbacks.help_callback_handler(DummyUpdate(query=query), DummyContext()))
        self.assertIn("coder-smart", query.texts[0])

    def test_btn_models_surfaces_gateway_error(self):
        self.patch(self.callbacks, "httpx", FakeHttpx(FakeAsyncClient(error=RuntimeError("gateway down"))))
        query = DummyQuery("btn_models")
        self.arun(self.callbacks.help_callback_handler(DummyUpdate(query=query), DummyContext()))
        self.assertIn("gateway down", query.texts[0])

    def test_btn_projects_lists_workspace_projects(self):
        (self.workspace / "alpha").mkdir()
        query = DummyQuery("btn_projects")
        self.arun(self.callbacks.help_callback_handler(DummyUpdate(query=query), DummyContext()))
        self.assertIn("alpha", query.texts[0])

    def test_btn_projects_handles_empty_workspace(self):
        query = DummyQuery("btn_projects")
        self.arun(self.callbacks.help_callback_handler(DummyUpdate(query=query), DummyContext()))
        self.assertIn("No projects found", query.texts[0])


class TestTelegramAiChat(TelegramHandlerTestCase):
    def test_chat_cmd_without_args_prompts(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.ai_chat.chat_cmd(update, context))
        self.assertTrue(any("Smart Router" in r for r in update.replies()))

    def test_chat_cmd_returns_model_answer(self):
        client = FakeAIClient(answer="42")
        self.patch(self.ai_chat, "ai_client", client)
        update, context = DummyUpdate(), DummyContext(args=["what", "is", "the", "answer"])
        self.arun(self.ai_chat.chat_cmd(update, context))
        self.assertIn("42", update.all_edits())
        self.assertEqual(client.last_kwargs["model"], "coder-smart")
        self.assertEqual(client.last_kwargs["messages"][1]["content"], "what is the answer")

    def test_chat_cmd_honors_explicit_model_flag(self):
        client = FakeAIClient(answer="ok")
        self.patch(self.ai_chat, "ai_client", client)
        update, context = DummyUpdate(), DummyContext(args=["-m", "reasoning-heavy", "solve", "this"])
        self.arun(self.ai_chat.chat_cmd(update, context))
        self.assertEqual(client.last_kwargs["model"], "reasoning-heavy")
        self.assertEqual(client.last_kwargs["messages"][1]["content"], "solve this")

    def test_chat_cmd_truncates_overlong_answers(self):
        self.patch(self.ai_chat, "ai_client", FakeAIClient(answer="y" * 5000))
        update, context = DummyUpdate(), DummyContext(args=["hi"])
        self.arun(self.ai_chat.chat_cmd(update, context))
        self.assertTrue(any("Response truncated" in e for e in update.all_edits()))

    def test_chat_cmd_gives_key_hint_on_auth_error(self):
        self.patch(self.ai_chat, "ai_client", FakeAIClient(error=RuntimeError("AuthenticationError: bad key")))
        update, context = DummyUpdate(), DummyContext(args=["hi"])
        self.arun(self.ai_chat.chat_cmd(update, context))
        self.assertTrue(any("AI Authentication Error" in e for e in update.all_edits()))

    def test_chat_cmd_gives_routing_hint_when_no_route_configured(self):
        self.patch(self.ai_chat, "ai_client", FakeAIClient(error=RuntimeError("No active route for model")))
        update, context = DummyUpdate(), DummyContext(args=["hi"])
        self.arun(self.ai_chat.chat_cmd(update, context))
        self.assertTrue(any("No active AI route" in e for e in update.all_edits()))

    def test_chat_cmd_falls_back_to_raw_error(self):
        self.patch(self.ai_chat, "ai_client", FakeAIClient(error=RuntimeError("connection reset")))
        update, context = DummyUpdate(), DummyContext(args=["hi"])
        self.arun(self.ai_chat.chat_cmd(update, context))
        self.assertTrue(any("connection reset" in e for e in update.all_edits()))

    def test_gemini_cmd_routes_to_gemini_model(self):
        client = FakeAIClient(answer="ok")
        self.patch(self.ai_chat, "ai_client", client)
        update, context = DummyUpdate(), DummyContext(args=["hello"])
        self.arun(self.ai_chat.gemini_cmd(update, context))
        self.assertEqual(client.last_kwargs["model"], "gemini-3.6-flash")

    def test_gemini_cmd_without_args_prompts(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.ai_chat.gemini_cmd(update, context))
        self.assertTrue(any("Gemini" in r for r in update.replies()))

    def test_gpt4_cmd_routes_to_github_model(self):
        client = FakeAIClient(answer="ok")
        self.patch(self.ai_chat, "ai_client", client)
        update, context = DummyUpdate(), DummyContext(args=["hello"])
        self.arun(self.ai_chat.gpt4_cmd(update, context))
        self.assertEqual(client.last_kwargs["model"], "github-gpt-4o")

    def test_gpt4_cmd_without_args_prompts(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.ai_chat.gpt4_cmd(update, context))
        self.assertTrue(any("GPT-4o" in r for r in update.replies()))

    def test_modelhelp_cmd_documents_every_router(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.ai_chat.modelhelp_cmd(update, context))
        body = update.replies()[0]
        for model in ("gemini-3.6-flash", "coder-smart", "reasoning-heavy", "github-gpt-4o"):
            self.assertIn(model, body)

    def test_models_cmd_lists_live_gateway_models(self):
        self.patch(self.ai_chat, "httpx", FakeHttpx(FakeAsyncClient(
            FakeResponse(200, {"data": [{"id": "coder-fast"}]})
        )))
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.ai_chat.models_cmd(update, context))
        self.assertTrue(any("coder-fast" in e for e in update.all_edits()))

    def test_models_cmd_falls_back_when_gateway_returns_nothing(self):
        self.patch(self.ai_chat, "httpx", FakeHttpx(FakeAsyncClient(FakeResponse(200, {"data": []}))))
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.ai_chat.models_cmd(update, context))
        self.assertTrue(any("Active Gateway Configuration" in e for e in update.all_edits()))

    def test_models_cmd_falls_back_when_gateway_unreachable(self):
        self.patch(self.ai_chat, "httpx", FakeHttpx(FakeAsyncClient(error=RuntimeError("refused"))))
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.ai_chat.models_cmd(update, context))
        self.assertTrue(any("gateway unreachable" in e for e in update.all_edits()))


class TestTelegramInteractive(TelegramHandlerTestCase):
    def _capture(self, name):
        captured = {}

        async def fake(update, context):
            captured["args"] = list(context.args)

        self.patch(self.interactive, name, fake)
        return captured

    def test_empty_message_is_ignored(self):
        update = DummyUpdate(text=None)
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(update.replies(), [])

    def test_force_reply_to_gemini_prompt_routes_to_gemini(self):
        captured = self._capture("chat_cmd")
        update = DummyUpdate(text="why is the sky blue",
                             reply_to=DummyReplyTarget("Google Gemini 3.6 Flash (Fast Tier)"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"][:2], ["-m", "gemini-3.6-flash"])

    def test_force_reply_to_gpt4_prompt_routes_to_github_model(self):
        captured = self._capture("chat_cmd")
        update = DummyUpdate(text="hello", reply_to=DummyReplyTarget("GitHub Models GPT-4o"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"][:2], ["-m", "github-gpt-4o"])

    def test_force_reply_to_smart_router_prompt_routes_to_chat(self):
        captured = self._capture("chat_cmd")
        update = DummyUpdate(text="hi there", reply_to=DummyReplyTarget("OMV AI Smart Router"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["hi", "there"])

    def test_force_reply_to_agent_prompt_shlex_splits_quoted_input(self):
        captured = self._capture("task_cmd")
        update = DummyUpdate(text='myproj "fix the bug"',
                             reply_to=DummyReplyTarget("Autonomous Coding Agent"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["myproj", "fix the bug"])

    def test_force_reply_to_claude_prompt_routes_to_claude(self):
        captured = self._capture("claude_cmd")
        update = DummyUpdate(text="refactor", reply_to=DummyReplyTarget("Claude Code CLI"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["refactor"])

    def test_force_reply_to_note_prompt_routes_to_note(self):
        captured = self._capture("note_cmd")
        update = DummyUpdate(text="Title | body", reply_to=DummyReplyTarget("Obsidian vault note"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["Title", "|", "body"])

    def test_force_reply_to_shell_prompt_routes_to_exec(self):
        captured = self._capture("exec_cmd")
        update = DummyUpdate(text="ls -la", reply_to=DummyReplyTarget("Workspace Shell Command"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["ls", "-la"])

    def test_force_reply_to_newrepo_prompt_routes_to_newrepo(self):
        captured = self._capture("newrepo_cmd")
        update = DummyUpdate(text='my-app "a description"',
                             reply_to=DummyReplyTarget("Create New GitHub Repository"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["my-app", "a description"])

    def test_force_reply_to_clone_prompt_routes_to_clone(self):
        """Regression guard: "Clone Git Repository" also contains "Repository",
        so the looser newrepo keyword test used to win and every reply to the
        /clone prompt was handed to newrepo_cmd."""
        captured = self._capture("clone_cmd")
        update = DummyUpdate(text="https://github.com/o/r",
                             reply_to=DummyReplyTarget("Clone Git Repository"))
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["https://github.com/o/r"])

    def test_pasted_github_url_auto_clones(self):
        captured = self._capture("clone_cmd")
        update = DummyUpdate(text="https://github.com/owner/repo")
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["https://github.com/owner/repo"])

    def test_plain_text_in_private_chat_falls_through_to_ai_chat(self):
        captured = self._capture("chat_cmd")
        update = DummyUpdate(text="what is a raid array", chat_type="private")
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertEqual(captured["args"], ["what", "is", "a", "raid", "array"])

    def test_plain_text_in_group_chat_is_ignored(self):
        """Group chatter must not be silently forwarded to the AI -- that would
        answer every unrelated message in the group."""
        captured = self._capture("chat_cmd")
        update = DummyUpdate(text="lunch anyone", chat_type="supergroup")
        self.arun(self.interactive.interactive_text_handler(update, DummyContext()))
        self.assertNotIn("args", captured)


class TestTelegramVault(TelegramHandlerTestCase):
    def test_vault_cmd_reports_unmounted_vault(self):
        self.patch(self.vault, "OBSIDIAN_VAULT", self.tmp / "absent")
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.vault.vault_cmd(update, context))
        self.assertTrue(any("not mounted" in r for r in update.replies()))

    def test_vault_cmd_reports_empty_vault(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.vault.vault_cmd(update, context))
        self.assertTrue(any("No notes found" in r for r in update.replies()))

    def test_vault_cmd_lists_recent_notes(self):
        (self.obsidian / "Inbox").mkdir()
        (self.obsidian / "Inbox" / "One.md").write_text("# one")
        (self.obsidian / "Inbox" / "Two.md").write_text("# two")
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.vault.vault_cmd(update, context))
        body = update.replies()[0]
        self.assertIn("Total notes: `2`", body)
        self.assertIn("One.md", body)

    def test_note_cmd_without_args_prompts(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.vault.note_cmd(update, context))
        self.assertTrue(any("Usage" in r for r in update.replies()))

    def test_note_cmd_splits_title_and_content_on_pipe(self):
        update, context = DummyUpdate(), DummyContext(args=["API", "Design", "|", "Use", "FastAPI"])
        self.arun(self.vault.note_cmd(update, context))
        note = self.obsidian / "Inbox" / "API Design.md"
        self.assertTrue(note.exists())
        body = note.read_text()
        self.assertIn("# API Design", body)
        self.assertIn("Use FastAPI", body)

    def test_note_cmd_without_pipe_generates_dated_title(self):
        update, context = DummyUpdate(), DummyContext(args=["remember", "this"])
        self.arun(self.vault.note_cmd(update, context))
        notes = list((self.obsidian / "Inbox").glob("Quick Note*.md"))
        self.assertEqual(len(notes), 1)
        self.assertIn("remember this", notes[0].read_text())

    def test_note_cmd_strips_path_separators_from_title(self):
        """A '/' in the title would otherwise escape the Inbox directory."""
        update, context = DummyUpdate(), DummyContext(args=["../../etc/passwd", "|", "x"])
        self.arun(self.vault.note_cmd(update, context))
        written = list((self.obsidian / "Inbox").glob("*.md"))
        self.assertEqual(len(written), 1)
        self.assertNotIn("/", written[0].name)

    def test_note_cmd_reports_write_failure(self):
        self.patch(self.vault, "OBSIDIAN_VAULT", self.obsidian / "README.md")
        (self.obsidian / "README.md").write_text("not a directory")
        update, context = DummyUpdate(), DummyContext(args=["T", "|", "c"])
        self.arun(self.vault.note_cmd(update, context))
        self.assertTrue(any("Failed to write note" in r for r in update.replies()))

    def test_init_obsidian_project_spec_writes_once(self):
        self.vault.init_obsidian_project_spec("myproj", "https://github.com/o/myproj")
        spec = self.obsidian / "Projects" / "myproj" / "project-spec.md"
        self.assertIn("https://github.com/o/myproj", spec.read_text())

        spec.write_text("hand-edited")
        self.vault.init_obsidian_project_spec("myproj", "https://github.com/o/myproj")
        self.assertEqual(spec.read_text(), "hand-edited")

    def test_init_obsidian_project_spec_swallows_errors(self):
        self.patch(self.vault, "OBSIDIAN_VAULT", self.obsidian / "file.md")
        (self.obsidian / "file.md").write_text("x")
        self.vault.init_obsidian_project_spec("myproj", "url")


class TestTelegramTopics(TelegramHandlerTestCase):
    def test_bindings_roundtrip_on_disk(self):
        self.assertEqual(self.topics.load_topic_bindings(), {})
        self.topics.set_bound_project(10, 3, "alpha")
        self.assertEqual(self.topics.get_bound_project(10, 3), "alpha")
        self.assertEqual(self.topics.load_topic_bindings(), {"10:3": "alpha"})
        self.topics.remove_bound_project(10, 3)
        self.assertIsNone(self.topics.get_bound_project(10, 3))

    def test_remove_unknown_binding_is_a_noop(self):
        self.topics.remove_bound_project(10, 3)
        self.assertEqual(self.topics.load_topic_bindings(), {})

    def test_get_bound_project_without_thread_id_is_none(self):
        self.assertIsNone(self.topics.get_bound_project(10, None))

    def test_load_bindings_tolerates_corrupt_file(self):
        self.topics.TOPICS_FILE.write_text("{broken")
        self.assertEqual(self.topics.load_topic_bindings(), {})

    def test_resolve_prefers_existing_workspace_folder_over_binding(self):
        (self.workspace / "explicit").mkdir()
        self.topics.set_bound_project(1, 5, "bound")
        update = DummyUpdate(cid=1, thread_id=5)
        resolved = self.topics.resolve_project_context(update, DummyContext(args=["explicit", "extra"]))
        self.assertEqual(resolved, ("explicit", ["extra"]))

    def test_resolve_uses_binding_when_first_arg_is_not_a_project(self):
        self.topics.set_bound_project(1, 5, "bound")
        update = DummyUpdate(cid=1, thread_id=5)
        resolved = self.topics.resolve_project_context(update, DummyContext(args=["do", "the", "thing"]))
        self.assertEqual(resolved, ("bound", ["do", "the", "thing"]))

    def test_resolve_with_no_args_returns_binding_only(self):
        self.topics.set_bound_project(1, 5, "bound")
        update = DummyUpdate(cid=1, thread_id=5)
        self.assertEqual(self.topics.resolve_project_context(update, DummyContext()), ("bound", []))

    def test_resolve_unbound_falls_back_to_first_arg(self):
        update = DummyUpdate()
        self.assertEqual(
            self.topics.resolve_project_context(update, DummyContext(args=["guess", "rest"])),
            ("guess", ["rest"]),
        )

    def test_bind_cmd_outside_topic_explains_setup(self):
        update, context = DummyUpdate(), DummyContext(args=["alpha"])
        self.arun(self.topics.bind_cmd(update, context))
        self.assertTrue(any("Enable **Topics**" in r for r in update.replies()))

    def test_bind_cmd_without_args_shows_status(self):
        (self.workspace / "alpha").mkdir()
        self.topics.set_bound_project(1, 5, "alpha")
        update = DummyUpdate(cid=1, thread_id=5, chat_type="supergroup")
        self.arun(self.topics.bind_cmd(update, DummyContext()))
        body = update.replies()[0]
        self.assertIn("Currently bound to: `alpha`", body)
        self.assertIn("alpha", body)

    def test_bind_cmd_rejects_unknown_project(self):
        update = DummyUpdate(cid=1, thread_id=5, chat_type="supergroup")
        self.arun(self.topics.bind_cmd(update, DummyContext(args=["ghost"])))
        self.assertTrue(any("not found" in r for r in update.replies()))
        self.assertIsNone(self.topics.get_bound_project(1, 5))

    def test_bind_cmd_binds_existing_project(self):
        (self.workspace / "alpha").mkdir()
        update = DummyUpdate(cid=1, thread_id=5, chat_type="supergroup")
        self.arun(self.topics.bind_cmd(update, DummyContext(args=["alpha"])))
        self.assertTrue(any("Successfully Bound" in r for r in update.replies()))
        self.assertEqual(self.topics.get_bound_project(1, 5), "alpha")

    def test_bind_cmd_rejects_traversal_project_name(self):
        update = DummyUpdate(cid=1, thread_id=5, chat_type="supergroup")
        self.arun(self.topics.bind_cmd(update, DummyContext(args=["../../etc"])))
        self.assertTrue(any("not found" in r for r in update.replies()))

    def test_unbind_cmd_outside_topic_explains(self):
        update, context = DummyUpdate(), DummyContext()
        self.arun(self.topics.unbind_cmd(update, context))
        self.assertTrue(any("inside a Telegram Forum Topic" in r for r in update.replies()))

    def test_unbind_cmd_clears_binding(self):
        self.topics.set_bound_project(1, 5, "alpha")
        update = DummyUpdate(cid=1, thread_id=5, chat_type="supergroup")
        self.arun(self.topics.unbind_cmd(update, DummyContext()))
        self.assertIsNone(self.topics.get_bound_project(1, 5))

    def test_createtopic_cmd_requires_group_chat(self):
        update, context = DummyUpdate(chat_type="private"), DummyContext(args=["alpha"])
        self.arun(self.topics.createtopic_cmd(update, context))
        self.assertTrue(any("Group / Supergroup" in r for r in update.replies()))

    def test_createtopic_cmd_without_args_lists_projects(self):
        (self.workspace / "alpha").mkdir()
        update = DummyUpdate(chat_type="supergroup")
        self.arun(self.topics.createtopic_cmd(update, DummyContext()))
        self.assertIn("alpha", update.replies()[0])

    def test_createtopic_cmd_rejects_unknown_project(self):
        update = DummyUpdate(chat_type="supergroup")
        self.arun(self.topics.createtopic_cmd(update, DummyContext(args=["ghost"])))
        self.assertTrue(any("not found" in r for r in update.replies()))

    def test_createtopic_cmd_creates_and_binds_topic(self):
        (self.workspace / "alpha").mkdir()
        bot = DummyBot()
        update = DummyUpdate(cid=300, chat_type="supergroup")
        self.arun(self.topics.createtopic_cmd(update, DummyContext(args=["alpha"], bot=bot)))
        self.assertEqual(bot.created_topics, [(300, "📂 alpha")])
        self.assertEqual(self.topics.get_bound_project(300, 77), "alpha")

    def test_createtopic_cmd_explains_topics_disabled(self):
        (self.workspace / "alpha").mkdir()
        update = DummyUpdate(chat_type="supergroup")
        context = DummyContext(args=["alpha"], bot=DummyBot(topic_error="the chat is not a forum"))
        self.arun(self.topics.createtopic_cmd(update, context))
        self.assertTrue(any("Topics are not enabled" in r for r in update.replies()))

    def test_createtopic_cmd_explains_missing_rights(self):
        (self.workspace / "alpha").mkdir()
        update = DummyUpdate(chat_type="supergroup")
        context = DummyContext(args=["alpha"], bot=DummyBot(topic_error="not enough rights"))
        self.arun(self.topics.createtopic_cmd(update, context))
        self.assertTrue(any("Administrator" in r for r in update.replies()))

    def test_createtopic_cmd_surfaces_unexpected_error(self):
        (self.workspace / "alpha").mkdir()
        update = DummyUpdate(chat_type="supergroup")
        context = DummyContext(args=["alpha"], bot=DummyBot(topic_error="network unreachable"))
        self.arun(self.topics.createtopic_cmd(update, context))
        self.assertTrue(any("Could not create topic" in r for r in update.replies()))


class TestTelegramAuthorizationGate(TelegramHandlerTestCase):
    """Every handler funnels through check_auth first -- if that gate ever stops
    firing, an unauthorized user gets a full shell on the workspace."""

    def test_unauthorized_user_is_refused_before_any_handler_runs(self):
        self.core_security.ALLOWED_USER_ID = "12345"
        update = DummyUpdate(uid="99999")
        self.arun(self.git_ops.projects_cmd(update, DummyContext()))
        self.assertTrue(any("Unauthorized" in r for r in update.replies()))

    def test_authorized_user_passes_the_gate(self):
        self.core_security.ALLOWED_USER_ID = "12345"
        update = DummyUpdate(uid="12345")
        self.arun(self.git_ops.projects_cmd(update, DummyContext()))
        self.assertFalse(any("Unauthorized" in r for r in update.replies()))


if __name__ == "__main__":
    unittest.main()
