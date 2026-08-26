"""
Tests for agent_station_core.vault_service (issue #19): save_obsidian_note,
list_vault_notes, and init_obsidian_project_spec had no test coverage at all.
Real filesystem operations against a temp directory -- no mocking needed
since these functions are pure filesystem I/O with no network/subprocess use.
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import stubs  # noqa: F401


class TestVaultService(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.vault_service as vault_service
        self.vault_service = vault_service
        self._tmpdir = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmpdir.name) / "vault"
        self.vault_service.OBSIDIAN_VAULT = self.vault

    def tearDown(self):
        self._tmpdir.cleanup()
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    # -- save_obsidian_note ------------------------------------------------

    def test_save_obsidian_note_creates_file_with_frontmatter(self):
        res = self.vault_service.save_obsidian_note("My Quick Note", "Some content here.")
        self.assertTrue(res["success"])
        note_path = self.vault / res["path"]
        self.assertTrue(note_path.exists())
        text = note_path.read_text(encoding="utf-8")
        self.assertIn("# My Quick Note", text)
        self.assertIn("Some content here.", text)
        self.assertIn("tags: [quick-capture, second-brain]", text)

    def test_save_obsidian_note_sanitizes_unsafe_characters_from_filename(self):
        res = self.vault_service.save_obsidian_note("Weird/Title:With*Chars?", "x")
        self.assertTrue(res["success"])
        # Only alnum, space, hyphen, underscore survive -- no path separators.
        self.assertNotIn("/", Path(res["path"]).name)
        self.assertTrue((self.vault / res["path"]).exists())

    def test_save_obsidian_note_blank_title_falls_back_to_quick_note(self):
        res = self.vault_service.save_obsidian_note("///", "x")
        self.assertTrue(res["success"])
        self.assertEqual(Path(res["path"]).name, "Quick Note.md")

    def test_save_obsidian_note_returns_error_on_write_failure(self):
        # Point the vault at a path that can't be created (a file, not a dir,
        # sitting where a directory needs to go).
        blocker = self.vault
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("not a directory")
        res = self.vault_service.save_obsidian_note("Title", "content")
        self.assertFalse(res["success"])
        self.assertIn("error", res)

    # -- list_vault_notes ----------------------------------------------------

    def test_list_vault_notes_missing_vault_returns_error(self):
        res = self.vault_service.list_vault_notes()
        self.assertFalse(res["success"])
        self.assertIn("not mounted", res["error"])

    def test_list_vault_notes_lists_most_recent_first(self):
        self.vault.mkdir(parents=True)
        for name in ("a.md", "b.md", "c.md"):
            (self.vault / name).write_text("x", encoding="utf-8")
            time.sleep(0.01)

        res = self.vault_service.list_vault_notes(limit=2)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_notes"], 3)
        self.assertEqual(res["recent"], ["c.md", "b.md"])

    def test_list_vault_notes_finds_nested_markdown_files(self):
        (self.vault / "Projects" / "foo").mkdir(parents=True)
        (self.vault / "Projects" / "foo" / "project-spec.md").write_text("x", encoding="utf-8")

        res = self.vault_service.list_vault_notes()
        self.assertTrue(res["success"])
        self.assertEqual(res["total_notes"], 1)

    # -- init_obsidian_project_spec ------------------------------------------

    def test_init_obsidian_project_spec_creates_expected_file(self):
        self.vault_service.init_obsidian_project_spec("myproj", "https://github.com/el-j/myproj.git")
        spec = self.vault / "Projects" / "myproj" / "project-spec.md"
        self.assertTrue(spec.exists())
        text = spec.read_text(encoding="utf-8")
        self.assertIn("# Project: myproj", text)
        self.assertIn("https://github.com/el-j/myproj.git", text)
        self.assertIn("Agent Execution History", text)

    def test_init_obsidian_project_spec_does_not_overwrite_existing_note(self):
        proj_dir = self.vault / "Projects" / "myproj"
        proj_dir.mkdir(parents=True)
        spec = proj_dir / "project-spec.md"
        spec.write_text("user's own notes, don't clobber me", encoding="utf-8")

        self.vault_service.init_obsidian_project_spec("myproj", "https://github.com/el-j/myproj.git")

        self.assertEqual(spec.read_text(encoding="utf-8"), "user's own notes, don't clobber me")

    def test_init_obsidian_project_spec_does_not_raise_on_failure(self):
        blocker = self.vault
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("not a directory")
        # Should log a warning and swallow the error, not raise.
        self.vault_service.init_obsidian_project_spec("myproj", "https://github.com/el-j/myproj.git")


if __name__ == "__main__":
    unittest.main()
