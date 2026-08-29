import unittest
from unittest.mock import patch
from scripts.auto_release_version import determine_release_version, parse_semver


class TestAutoReleaseVersion(unittest.TestCase):
    def test_parse_semver(self):
        self.assertEqual(parse_semver("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_semver("0.1.0"), (0, 1, 0))
        self.assertEqual(parse_semver("invalid"), (0, 0, 0))

    @patch("scripts.auto_release_version.get_latest_git_tag", return_value="v0.0.2")
    @patch("scripts.auto_release_version.get_control_file_version", return_value="0.1.0")
    def test_control_file_higher_version_priority(self, _ctrl, _tag):
        ver = determine_release_version(branch="develop")
        self.assertEqual(ver, "0.1.0")

    @patch("scripts.auto_release_version.get_latest_git_tag", return_value="v0.1.0")
    @patch("scripts.auto_release_version.get_control_file_version", return_value="0.1.0")
    def test_hotfix_branch_bumps_patch(self, _ctrl, _tag):
        ver = determine_release_version(branch="hotfix/fix-auth-token")
        self.assertEqual(ver, "0.1.1")

    @patch("scripts.auto_release_version.get_latest_git_tag", return_value="v0.1.0")
    @patch("scripts.auto_release_version.get_control_file_version", return_value="0.1.0")
    def test_fix_branch_bumps_patch(self, _ctrl, _tag):
        ver = determine_release_version(branch="fix/workbench-navigation")
        self.assertEqual(ver, "0.1.1")

    @patch("scripts.auto_release_version.get_latest_git_tag", return_value="v0.1.0")
    @patch("scripts.auto_release_version.get_control_file_version", return_value="0.1.0")
    def test_develop_branch_bumps_minor(self, _ctrl, _tag):
        ver = determine_release_version(branch="develop")
        self.assertEqual(ver, "0.2.0")

    @patch("scripts.auto_release_version.get_latest_git_tag", return_value="v0.1.0")
    @patch("scripts.auto_release_version.get_control_file_version", return_value="0.1.0")
    def test_breaking_change_bumps_major(self, _ctrl, _tag):
        ver = determine_release_version(branch="develop", pr_title="feat!: redesign entire architecture [BREAKING]")
        self.assertEqual(ver, "1.0.0")

    @patch("scripts.auto_release_version.get_latest_git_tag", return_value="v0.1.0")
    @patch("scripts.auto_release_version.get_control_file_version", return_value="0.1.0")
    def test_explicit_release_branch(self, _ctrl, _tag):
        ver = determine_release_version(branch="release/v0.3.0")
        self.assertEqual(ver, "0.3.0")


if __name__ == "__main__":
    unittest.main()
