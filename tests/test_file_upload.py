"""
Tests for the Telegram bot's file-upload-to-GitHub feature (issue #28).

Covers the pure logic (caption parsing, path sanitization, remote-URL
parsing) directly, plus an end-to-end handler test with mocked Telegram
file download and git subprocesses -- mirroring tests/test_cancel_command.py's
Dummy-object pattern.
"""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs


class DummyStatusMessage:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)


class DummyMessage:
    def __init__(self, thread_id=None, document=None, photo=None, caption=None):
        self.message_thread_id = thread_id
        self.document = document
        self.photo = photo or []
        self.caption = caption
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return DummyStatusMessage()


class DummyChat:
    def __init__(self, cid):
        self.id = cid


class DummyUser:
    def __init__(self, uid):
        self.id = uid


class DummyUpdate:
    def __init__(self, cid, message, uid="1"):
        self.effective_chat = DummyChat(cid)
        self.effective_message = message
        self.effective_user = DummyUser(uid)


class DummyDocument:
    def __init__(self, file_id="doc-1", file_name="report.pdf", file_size=1024):
        self.file_id = file_id
        self.file_name = file_name
        self.file_size = file_size


class DummyContext:
    def __init__(self):
        self.bot = MagicMock()
        self.bot.get_file = AsyncMock()


class TestUploadCaptionParsing(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "bot")
        import handlers.upload as upload
        self.upload = upload

    def tearDown(self):
        if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "bot")

    def test_no_caption_returns_none_none(self):
        self.assertEqual(self.upload.parse_upload_caption(None), (None, None))
        self.assertEqual(self.upload.parse_upload_caption("   "), (None, None))

    def test_bare_path_caption(self):
        self.assertEqual(self.upload.parse_upload_caption("docs/notes.md"), (None, "docs/notes.md"))

    def test_project_override_syntax(self):
        self.assertEqual(
            self.upload.parse_upload_caption("myapi: docs/notes.md"),
            ("myapi", "docs/notes.md"),
        )

    def test_colon_without_valid_project_prefix_falls_back_to_bare_path(self):
        # A path that happens to contain a colon but doesn't look like
        # "shortname: rest" (has a slash before the colon) is not split.
        self.assertEqual(
            self.upload.parse_upload_caption("weird/pa:th.txt"),
            (None, "weird/pa:th.txt"),
        )

    def test_parse_github_owner_repo_https(self):
        self.assertEqual(
            self.upload.parse_github_owner_repo("https://github.com/el-j/omv-agent-station.git"),
            ("el-j", "omv-agent-station"),
        )

    def test_parse_github_owner_repo_ssh(self):
        self.assertEqual(
            self.upload.parse_github_owner_repo("git@github.com:el-j/omv-agent-station.git"),
            ("el-j", "omv-agent-station"),
        )

    def test_parse_github_owner_repo_non_github_returns_none(self):
        self.assertIsNone(self.upload.parse_github_owner_repo("https://gitlab.com/el-j/omv-agent-station.git"))


class TestSanitizeRelativePath(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "bot")
        import core.security as security
        self.security = security
        self._tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()
        if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "bot")

    def test_simple_relative_path_allowed(self):
        result = self.security.sanitize_relative_path(self.base, "docs/notes.md")
        self.assertEqual(result, (self.base / "docs" / "notes.md").resolve())

    def test_bare_filename_allowed(self):
        result = self.security.sanitize_relative_path(self.base, "notes.md")
        self.assertEqual(result, (self.base / "notes.md").resolve())

    def test_traversal_blocked(self):
        self.assertIsNone(self.security.sanitize_relative_path(self.base, "../../etc/passwd"))
        self.assertIsNone(self.security.sanitize_relative_path(self.base, "docs/../../etc/passwd"))

    def test_absolute_path_blocked(self):
        self.assertIsNone(self.security.sanitize_relative_path(self.base, "/etc/passwd"))

    def test_dot_git_component_blocked(self):
        self.assertIsNone(self.security.sanitize_relative_path(self.base, ".git/hooks/post-commit"))
        self.assertIsNone(self.security.sanitize_relative_path(self.base, "sub/.git/config"))

    def test_empty_or_root_blocked(self):
        self.assertIsNone(self.security.sanitize_relative_path(self.base, ""))
        self.assertIsNone(self.security.sanitize_relative_path(self.base, "."))


class TestUploadHandlerEndToEnd(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR / "telegram-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "bot")
        import handlers.upload as upload
        import handlers.topics as topics
        import core.task_registry as task_registry
        self.upload = upload
        self.topics = topics
        self.task_registry = task_registry
        self.task_registry._active.clear()

    def tearDown(self):
        self.task_registry._active.clear()
        if str(ROOT_DIR / "telegram-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "telegram-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "bot")

    def test_rejects_when_no_project_bound(self):
        async def scenario():
            msg = DummyMessage(thread_id=None, document=DummyDocument())
            update = DummyUpdate(cid=42, message=msg)
            ctx = DummyContext()
            await self.upload.upload_file_handler(update, ctx)
            self.assertTrue(any("No project bound" in r for r in msg.replies))
            self.assertIsNone(self.task_registry.get(42, None))

        asyncio.run(scenario())

    def test_rejects_path_traversal_caption(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir) / "workspace"
                project_dir = workspace / "myproj"
                (project_dir / ".git").mkdir(parents=True)

                self.upload.WORKSPACE = workspace
                self.topics.WORKSPACE = workspace
                self.topics.TOPICS_FILE = workspace / ".agent_topics.json"
                self.topics.set_bound_project(99, 7, "myproj")

                msg = DummyMessage(thread_id=7, document=DummyDocument(), caption="../../etc/passwd")
                update = DummyUpdate(cid=99, message=msg)
                ctx = DummyContext()
                await self.upload.upload_file_handler(update, ctx)

                self.assertTrue(any("Invalid target path" in r for r in msg.replies))
                self.assertIsNone(self.task_registry.get(99, 7))

        asyncio.run(scenario())

    def test_full_upload_flow_creates_branch_commits_and_pushes(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir) / "workspace"
                project_dir = workspace / "myproj"
                (project_dir / ".git").mkdir(parents=True)

                self.upload.WORKSPACE = workspace
                self.topics.WORKSPACE = workspace
                self.topics.TOPICS_FILE = workspace / ".agent_topics.json"
                self.topics.set_bound_project(1, 2, "myproj")

                msg = DummyMessage(thread_id=2, document=DummyDocument(file_name="report.pdf"), caption="docs/report.pdf")
                update = DummyUpdate(cid=1, message=msg)

                ctx = DummyContext()
                fake_tg_file = MagicMock()

                async def fake_download(custom_path):
                    Path(custom_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(custom_path).write_bytes(b"%PDF-fake-content")

                fake_tg_file.download_to_drive = fake_download
                ctx.bot.get_file.return_value = fake_tg_file

                git_calls = []

                class FakeGitProc:
                    def __init__(self, args):
                        self.args = args
                        self.returncode = 0

                    async def communicate(self):
                        if self.args[:2] == ["rev-parse", "--abbrev-ref"]:
                            return b"main\n", b""
                        if self.args[0] == "remote":
                            return b"https://github.com/el-j/omv-agent-station.git\n", b""
                        return b"", b""

                async def fake_create_subprocess_exec(*args, **kwargs):
                    git_args = list(args[1:])  # drop GIT_BIN
                    git_calls.append(git_args)
                    return FakeGitProc(git_args)

                orig = asyncio.create_subprocess_exec
                asyncio.create_subprocess_exec = fake_create_subprocess_exec
                try:
                    await asyncio.wait_for(self.upload.upload_file_handler(update, ctx), timeout=1.0)

                    for _ in range(100):
                        if self.task_registry.get(1, 2) is None and any("Uploaded" in r or "error" in r.lower() for r in msg.replies + []):
                            break
                        if not self.task_registry.get(1, 2):
                            break
                        await asyncio.sleep(0.01)
                    else:
                        self.fail("upload task never finished")

                    written = project_dir / "docs" / "report.pdf"
                    self.assertTrue(written.exists())
                    self.assertEqual(written.read_bytes(), b"%PDF-fake-content")

                    self.assertTrue(any(c[:2] == ["checkout", "-B"] for c in git_calls))
                    checkout_call = next(c for c in git_calls if c[:2] == ["checkout", "-B"])
                    self.assertTrue(checkout_call[2].startswith("upload/"))

                    self.assertTrue(any(c[0] == "add" for c in git_calls))
                    self.assertTrue(any(c[0] == "commit" for c in git_calls))
                    push_call = next(c for c in git_calls if c[0] == "push")
                    self.assertEqual(push_call[1], "-u")
                    self.assertEqual(push_call[2], "origin")
                    self.assertTrue(push_call[3].startswith("upload/"))
                finally:
                    asyncio.create_subprocess_exec = orig

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
