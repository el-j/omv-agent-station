"""
Real git integration tests for all three bots (GitHub issue #63).

Every other test of /clone and of file-upload-to-repo replaces the git work
with a mock: `patch("clone_repository", AsyncMock(...))`, or a stubbed
`asyncio.create_subprocess_exec` so `git add/commit/push` never runs. Nothing
proved the real code could clone a repo or land a file in a real commit.

Here nothing about git is mocked. A real `git daemon` serves a real bare
repository over git://127.0.0.1, the bots' real clone paths clone from it, and
the bots' real upload paths write a file, commit it, and push it back -- the
assertions read the resulting objects out of the bare repo with `git` itself.
Only the messenger boundary is faked: Discord/Signal/Telegram attachment
downloads return bytes from memory instead of hitting a platform API.

A local `git daemon` (rather than a plain filesystem path) is what the bots'
own sanitize_git_url() accepts: it requires an https/git/ssh scheme, so a
bare path or file:// URL is rejected before git is ever invoked. Serving the
fixture over git:// therefore exercises the real URL validation too.
"""

import asyncio
import os
import shutil
import socket
import subprocess  # nosec B404
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stubs

GIT_BIN = shutil.which("git")
SEED_COMMIT_MESSAGE = "feat: seed commit"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _git(cwd, *args, **kwargs):
    return subprocess.run(  # nosec B603
        [GIT_BIN, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        **kwargs,
    )


class LocalGitRemote:
    """A real bare repository with one seed commit, served by a real `git daemon`.

    receive-pack is enabled so the upload tests can push back to it; the daemon
    binds 127.0.0.1 only and lives for the duration of a single test.
    """

    def __init__(self, root: Path, name: str = "myrepo"):
        self.root = root
        self.name = name
        self.bare = root / f"{name}.git"
        self.port = _free_port()
        self._proc = None

    @property
    def url(self) -> str:
        return f"git://127.0.0.1:{self.port}/{self.name}.git"

    def start(self):
        self.root.mkdir(parents=True, exist_ok=True)
        _git(self.root, "init", "--bare", "-q", "-b", "main", str(self.bare))

        seed = self.root / "_seed"
        seed.mkdir()
        _git(seed, "init", "-q", "-b", "main")
        _git(seed, "config", "user.name", "Seed")
        _git(seed, "config", "user.email", "seed@example.com")
        (seed / "README.md").write_text("seed\n", encoding="utf-8")
        _git(seed, "add", "README.md")
        _git(seed, "commit", "-q", "-m", SEED_COMMIT_MESSAGE)
        _git(seed, "push", "-q", str(self.bare), "main")

        (self.bare / "git-daemon-export-ok").touch()
        self._proc = subprocess.Popen(  # nosec B603
            [
                GIT_BIN, "daemon",
                "--listen=127.0.0.1",
                f"--port={self.port}",
                f"--base-path={self.root}",
                "--export-all",
                "--enable=receive-pack",
                "--reuseaddr",
                str(self.root),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_until_listening()
        return self

    def _wait_until_listening(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError("git daemon exited before accepting connections")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError(f"git daemon did not start listening on port {self.port}")

    def stop(self):
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)

    # -- assertions read straight out of the real bare repo -----------------

    def branches(self) -> list[str]:
        out = _git(self.bare, "for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout
        return out.split()

    def file_at(self, ref: str, path: str) -> bytes:
        return subprocess.run(  # nosec B603
            [GIT_BIN, "show", f"{ref}:{path}"],
            cwd=str(self.bare), capture_output=True, check=True,
        ).stdout

    def log(self, ref: str) -> str:
        return _git(self.bare, "log", "--format=%s", ref).stdout

    def make_working_copy(self, dest: Path, author="Test Bot", email="bot@example.com") -> Path:
        """A real clone the upload tests start from, with a committer identity
        configured so `git commit` works in an environment with no global one."""
        _git(self.root, "clone", "-q", self.url, str(dest))
        _git(dest, "config", "user.name", author)
        _git(dest, "config", "user.email", email)
        return dest


@unittest.skipIf(GIT_BIN is None, "git binary not available")
class RealGitTestCase(unittest.TestCase):
    """Shared temp workspace + live git daemon for one test."""

    bot_dir = ""
    purge = ("core", "handlers")

    def setUp(self):
        stubs.purge_bot_modules(*self.purge)
        sys.path.insert(0, str(ROOT_DIR / self.bot_dir))

        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        self.obsidian = self.tmp / "obsidian"
        self.obsidian.mkdir()

        self.remote = LocalGitRemote(self.tmp / "remotes").start()

    def tearDown(self):
        self.remote.stop()
        self._tmpdir.cleanup()
        if str(ROOT_DIR / self.bot_dir) in sys.path:
            sys.path.remove(str(ROOT_DIR / self.bot_dir))
        stubs.purge_bot_modules(*self.purge)

    def assertClonedFromRemote(self, project_dir: Path):
        self.assertTrue(project_dir.is_dir(), f"{project_dir} was never created on disk")
        self.assertTrue((project_dir / ".git").is_dir(), f"{project_dir} is not a git working copy")
        self.assertTrue((project_dir / "README.md").is_file(), "the seeded file is missing from the clone")
        log = _git(project_dir, "log", "--format=%s").stdout
        self.assertIn(SEED_COMMIT_MESSAGE, log, "the clone does not contain the remote's commit")

    def assertPushedUpload(self, expected_bytes: bytes, expected_path: str):
        upload_branches = [b for b in self.remote.branches() if b.startswith("upload/")]
        self.assertEqual(
            len(upload_branches), 1,
            f"expected exactly one pushed upload branch in the real remote, got {self.remote.branches()}",
        )
        branch = upload_branches[0]
        self.assertEqual(self.remote.file_at(branch, expected_path), expected_bytes)
        self.assertIn("chore(upload)", self.remote.log(branch))
        return branch


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

class DummyTelegramMessage:
    def __init__(self):
        self.texts = []
        self.edits = []

    async def reply_text(self, text=None, **kwargs):
        self.texts.append(text)
        return self

    async def edit_text(self, text=None, **kwargs):
        self.edits.append(text)
        return self


class DummyTelegramFile:
    """Stands in for telegram.File: writes the bytes the test handed it, which
    is exactly what download_to_drive does after fetching from Telegram."""

    def __init__(self, content: bytes):
        self._content = content

    async def download_to_drive(self, custom_path=None):
        Path(custom_path).write_bytes(self._content)
        return Path(custom_path)


class TestTelegramRealGit(RealGitTestCase):
    bot_dir = "telegram-agent-bot"
    purge = ("core", "handlers", "bot")

    def setUp(self):
        super().setUp()
        import core.config as config
        import core.security as security
        import core.task_registry as task_registry
        import handlers.git_ops as git_ops
        import handlers.topics as topics
        import handlers.upload as upload
        import handlers.vault as vault

        self.git_ops = git_ops
        self.topics = topics
        self.upload = upload
        self.task_registry = task_registry
        self.task_registry._active.clear()
        security.ALLOWED_USER_ID = None

        config.WORKSPACE = self.workspace
        config.OBSIDIAN_VAULT = self.obsidian
        for mod in (git_ops, topics, upload):
            mod.WORKSPACE = self.workspace
        vault.OBSIDIAN_VAULT = self.obsidian
        topics.TOPICS_FILE = self.workspace / ".agent_topics.json"

    def tearDown(self):
        self.task_registry._active.clear()
        super().tearDown()

    def _update_and_context(self, args=None, chat_id=100):
        message = DummyTelegramMessage()

        class Chat:
            id = chat_id
            type = "private"

        class User:
            id = 1
            username = "tester"

        class Update:
            effective_message = message
            effective_chat = Chat()
            effective_user = User()

        class Bot:
            pass

        class Context:
            pass

        ctx = Context()
        ctx.args = args or []
        ctx.bot = Bot()
        return Update(), ctx, message

    def test_clone_cmd_really_clones_from_a_live_git_daemon(self):
        update, ctx, message = self._update_and_context(args=[self.remote.url])
        asyncio.run(self.git_ops.clone_cmd(update, ctx))

        self.assertTrue(any("Cloned" in e for e in message.edits), f"clone_cmd reported: {message.edits}")
        self.assertClonedFromRemote(self.workspace / "myrepo")
        self.assertTrue((self.obsidian / "Projects" / "myrepo" / "project-spec.md").is_file())

    def test_upload_really_commits_and_pushes_the_file(self):
        project_dir = self.remote.make_working_copy(self.workspace / "myrepo")
        payload = b"telegram upload payload\n"
        # Telegram's get_bound_project() only resolves bindings that carry a
        # forum-topic id, so this upload runs in a topic rather than a bare chat.
        self.topics.set_bound_project(100, 42, "myrepo")

        async def scenario():
            update, ctx, message = self._update_and_context(chat_id=100)

            class Doc:
                file_id = "tg-file-1"
                file_name = "notes.txt"
                file_size = len(payload)

            msg = update.effective_message
            msg.document = Doc()
            msg.photo = None
            msg.caption = "docs/notes.txt"
            msg.message_thread_id = 42

            async def get_file(file_id):
                self.assertEqual(file_id, "tg-file-1")
                return DummyTelegramFile(payload)

            ctx.bot.get_file = get_file

            await self.upload.upload_file_handler(update, ctx)
            entry = self.task_registry.get(100, 42)
            self.assertIsNotNone(entry, "upload_file_handler never registered a background task")
            await entry.asyncio_task
            return message

        message = asyncio.run(scenario())

        self.assertTrue(
            any("File Uploaded" in e for e in message.edits),
            f"upload reported: {message.edits}",
        )
        branch = self.assertPushedUpload(payload, "docs/notes.txt")
        self.assertEqual((project_dir / "docs" / "notes.txt").read_bytes(), payload)
        self.assertIn(branch, self.remote.branches())


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

class DummyDiscordReply:
    def __init__(self):
        self.edits = []

    async def edit(self, content=None, **kwargs):
        self.edits.append(content)


class DummyDiscordChannel:
    def __init__(self, cid):
        self.id = cid


class DummyDiscordAuthor:
    def __init__(self, uid="1"):
        self.id = uid
        self.name = "tester"


class DummyDiscordCtx:
    def __init__(self, channel_id=1):
        self.channel = DummyDiscordChannel(channel_id)
        self.author = DummyDiscordAuthor()
        self.replies = []
        self.reply_messages = []

    async def reply(self, content=None, **kwargs):
        self.replies.append(content)
        msg = DummyDiscordReply()
        self.reply_messages.append(msg)
        return msg

    def all_edits(self):
        return [e for m in self.reply_messages for e in m.edits]


class DummyDiscordAttachment:
    def __init__(self, filename, content: bytes):
        self.filename = filename
        self.size = len(content)
        self._content = content

    async def read(self):
        return self._content


class DummyDiscordMessage:
    def __init__(self, channel_id, content="", attachments=None):
        self.channel = DummyDiscordChannel(channel_id)
        self.author = DummyDiscordAuthor()
        self.content = content
        self.attachments = attachments or []
        self.replies = []
        self.reply_messages = []

    async def reply(self, content=None, **kwargs):
        self.replies.append(content)
        msg = DummyDiscordReply()
        self.reply_messages.append(msg)
        return msg

    def all_edits(self):
        return [e for m in self.reply_messages for e in m.edits]


class TestDiscordRealGit(RealGitTestCase):
    bot_dir = "discord-agent-bot"
    purge = ("core", "handlers", "discord_bot")

    def setUp(self):
        super().setUp()
        import core.security as core_security
        import handlers.git_ops as git_ops
        import handlers.upload as upload
        import agent_station_core.git_service as git_service
        import agent_station_core.vault_service as vault_service
        import agent_station_core.task_registry as task_registry
        import agent_station_core.topics_service as topics_service

        self.git_ops = git_ops
        self.upload = upload
        self.task_registry = task_registry
        self.topics_service = topics_service
        self.task_registry._active.clear()
        core_security.ALLOWED_USER_ID = None

        # WORKSPACE/OBSIDIAN_VAULT are imported by value into each module.
        git_service.WORKSPACE = self.workspace
        vault_service.OBSIDIAN_VAULT = self.obsidian
        core_security.WORKSPACE = self.workspace
        for mod in (git_ops, upload):
            mod.WORKSPACE = self.workspace
        topics_service.WORKSPACE = self.workspace
        topics_service.TOPICS_FILE = self.workspace / ".agent_topics.json"

    def tearDown(self):
        self.task_registry._active.clear()
        super().tearDown()

    def test_clone_cmd_really_clones_from_a_live_git_daemon(self):
        ctx = DummyDiscordCtx()
        asyncio.run(self.git_ops.clone_cmd(ctx, git_url=self.remote.url))

        self.assertTrue(any("Cloned" in e for e in ctx.all_edits()), f"clone_cmd reported: {ctx.all_edits()}")
        self.assertClonedFromRemote(self.workspace / "myrepo")
        self.assertTrue((self.obsidian / "Projects" / "myrepo" / "project-spec.md").is_file())

    def test_upload_really_commits_and_pushes_the_file(self):
        project_dir = self.remote.make_working_copy(self.workspace / "myrepo")
        payload = b"discord upload payload\n"
        self.topics_service.set_bound_project("321", None, "myrepo")

        async def scenario():
            message = DummyDiscordMessage(
                channel_id=321,
                content="docs/from-discord.txt",
                attachments=[DummyDiscordAttachment("from-discord.txt", payload)],
            )
            await self.upload.handle_discord_upload(message)
            entry = self.task_registry.get("321", None)
            self.assertIsNotNone(entry, "handle_discord_upload never registered a background task")
            await entry.asyncio_task
            return message

        message = asyncio.run(scenario())

        self.assertTrue(
            any("File Uploaded" in e for e in message.all_edits()),
            f"upload reported: {message.all_edits()} / {message.replies}",
        )
        self.assertPushedUpload(payload, "docs/from-discord.txt")
        self.assertEqual((project_dir / "docs" / "from-discord.txt").read_bytes(), payload)


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------

class TestSignalRealGit(RealGitTestCase):
    bot_dir = "signal-agent-bot"
    purge = ("core", "handlers", "signal_bot")

    def setUp(self):
        super().setUp()
        import core.security as core_security
        import core.messaging as messaging
        import handlers.git_ops as git_ops
        import handlers.upload as upload
        import agent_station_core.git_service as git_service
        import agent_station_core.vault_service as vault_service
        import agent_station_core.task_registry as task_registry
        import agent_station_core.topics_service as topics_service

        self.git_ops = git_ops
        self.upload = upload
        self.task_registry = task_registry
        self.topics_service = topics_service
        self.task_registry._active.clear()
        core_security.SIGNAL_ALLOWED_NUMBER = ""

        git_service.WORKSPACE = self.workspace
        vault_service.OBSIDIAN_VAULT = self.obsidian
        for mod in (git_ops, upload):
            mod.WORKSPACE = self.workspace
        topics_service.WORKSPACE = self.workspace
        topics_service.TOPICS_FILE = self.workspace / ".agent_topics.json"

        self.sent = []

        async def fake_send(recipient, message):
            self.sent.append(message)

        self._send_modules = [messaging, git_ops, upload]
        self._orig_send = {mod: mod.send_signal_message for mod in self._send_modules}
        for mod in self._send_modules:
            mod.send_signal_message = fake_send

    def tearDown(self):
        for mod, orig in self._orig_send.items():
            mod.send_signal_message = orig
        self.task_registry._active.clear()
        super().tearDown()

    def test_clone_really_clones_from_a_live_git_daemon(self):
        asyncio.run(self.git_ops.clone("+15550001111", [self.remote.url]))

        self.assertTrue(any("Cloned" in m for m in self.sent), f"clone reported: {self.sent}")
        self.assertClonedFromRemote(self.workspace / "myrepo")
        self.assertTrue((self.obsidian / "Projects" / "myrepo" / "project-spec.md").is_file())

    def test_upload_really_commits_and_pushes_the_file(self):
        project_dir = self.remote.make_working_copy(self.workspace / "myrepo")
        payload = b"signal upload payload\n"
        sender = "+15550001111"
        self.topics_service.set_bound_project(sender, None, "myrepo")

        async def fake_download(attachment_id):
            self.assertEqual(attachment_id, "sig-att-1")
            return payload

        self.upload.download_signal_attachment = fake_download

        async def scenario():
            await self.upload.handle_signal_upload(
                sender,
                {"id": "sig-att-1", "filename": "from-signal.txt", "size": len(payload)},
                "docs/from-signal.txt",
            )
            entry = self.task_registry.get(sender)
            self.assertIsNotNone(entry, "handle_signal_upload never registered a background task")
            await entry.asyncio_task

        asyncio.run(scenario())

        self.assertTrue(any("File Uploaded" in m for m in self.sent), f"upload reported: {self.sent}")
        self.assertPushedUpload(payload, "docs/from-signal.txt")
        self.assertEqual((project_dir / "docs" / "from-signal.txt").read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
