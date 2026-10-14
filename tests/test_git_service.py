"""
Tests for agent_station_core's git_service, security, and custom_cmds_service
(issue #52). git_service sat at 12% line coverage despite being the highest
blast-radius module in the repo: it builds the PAT-bearing remote URLs, decides
what gets cloned where, and runs push/pull. A silent regression there means a
leaked token in a URL, a push to the wrong remote, or a clone escaping the
workspace root.

Where practical the tests drive REAL git against real temporary repositories
(`git init --bare` standing in for the remote) rather than asserting against a
mock's call list. Only the genuinely network-bound parts are substituted:
  * the GitHub repo-creation REST call (a fake httpx client), and
  * the clone/push against github.com, where GIT_BIN points at a shim that
    records its argv -- which is exactly how the PAT-in-URL assertions work.
"""

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


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class FakeAsyncClient:
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
        self.calls.append((url, kwargs))
        if self._error:
            raise self._error
        return self._response


class FakeHttpx:
    def __init__(self, client):
        self.AsyncClient = client


class RecordingSubprocess:
    """Stands in for git_service's `subprocess` module for init_git_credentials,
    which shells out to `git config --global` and would otherwise rewrite the
    test runner's own global git configuration."""

    def __init__(self, error=None):
        self.commands = []
        self._error = error

    def run(self, args, **kwargs):
        if self._error:
            raise self._error
        self.commands.append(list(args))
        return None


class CoreServiceTestCase(unittest.TestCase):
    def setUp(self):
        # The three bots each vendor their own copy of agent_station_core; a
        # previously-imported one would otherwise shadow the root package here.
        # Deliberately NOT re-purged in tearDown: that would leave the name
        # unbound for the next test file, letting whichever bot happens to run
        # next cache ITS vendored copy under the shared `agent_station_core`
        # name for the rest of the process.
        stubs.purge_bot_modules("agent_station_core")
        sys.path.insert(0, str(ROOT_DIR))
        import agent_station_core.custom_cmds_service as custom_cmds_service
        import agent_station_core.git_service as git_service
        import agent_station_core.security as security
        import agent_station_core.vault_service as vault_service
        self.custom_cmds_service = custom_cmds_service
        self.git_service = git_service
        self.security = security
        self.vault_service = vault_service

        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        self.obsidian = self.tmp / "obsidian"
        self.obsidian.mkdir()

        self._patched = []
        self.patch(self.git_service, "WORKSPACE", self.workspace)
        self.patch(self.vault_service, "OBSIDIAN_VAULT", self.obsidian)
        self.patch(self.custom_cmds_service, "CUSTOM_CMDS_FILE", self.workspace / ".custom_commands.json")
        self.patch(self.custom_cmds_service, "OBSIDIAN_CMDS_FILE", self.obsidian / "Config" / "commands.json")

    def tearDown(self):
        for mod, name, orig in self._patched:
            setattr(mod, name, orig)
        self._tmpdir.cleanup()
        if str(ROOT_DIR) in sys.path:
            sys.path.remove(str(ROOT_DIR))

    def patch(self, module, name, value):
        self._patched.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    def arun(self, coro):
        import asyncio
        return asyncio.run(coro)

    def git(self, cwd, *args):
        return subprocess.run(  # nosec B603,B607
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
            cwd=str(cwd), capture_output=True, text=True, check=True,
        )

    def make_repo(self, name="myproj", with_remote=False):
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
        log = self.tmp / "git-argv.log"
        shim = self.tmp / "fakegit.sh"
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
        self.patch(self.git_service, "GIT_BIN", str(shim))
        return log


class TestInitGitCredentials(CoreServiceTestCase):
    """Covers the credential-helper setup for all three supported providers."""

    def _run_with(self, github="", gitlab="", bb_user="", bb_token="", error=None):
        recorder = RecordingSubprocess(error=error)
        self.patch(self.git_service, "subprocess", recorder)
        self.patch(self.git_service, "GITHUB_TOKEN", github)
        self.patch(self.git_service, "GITLAB_TOKEN", gitlab)
        self.patch(self.git_service, "BITBUCKET_USER", bb_user)
        self.patch(self.git_service, "BITBUCKET_TOKEN", bb_token)
        self.git_service.init_git_credentials()
        return recorder

    def test_always_sets_author_identity_and_default_branch(self):
        recorder = self._run_with()
        joined = [" ".join(c) for c in recorder.commands]
        self.assertEqual(len(recorder.commands), 3)
        self.assertTrue(any("user.name" in c for c in joined))
        self.assertTrue(any("user.email" in c for c in joined))
        self.assertTrue(any("init.defaultBranch main" in c for c in joined))

    def test_github_token_configures_insteadof_rewrite(self):
        recorder = self._run_with(github="ghp_secret")
        joined = " ".join(" ".join(c) for c in recorder.commands)
        self.assertIn("url.https://x-access-token:ghp_secret", joined)
        self.assertIn("@github.com/.insteadOf", joined)
        self.assertIn("https://github.com/", joined)

    def test_gitlab_token_configures_oauth2_rewrite(self):
        recorder = self._run_with(gitlab="glpat_secret")
        joined = " ".join(" ".join(c) for c in recorder.commands)
        self.assertIn("url.https://oauth2:glpat_secret", joined)
        self.assertIn("@gitlab.com/.insteadOf", joined)

    def test_bitbucket_requires_both_user_and_token(self):
        only_token = self._run_with(bb_token="app_pw")
        self.assertEqual(len(only_token.commands), 3)

        both = self._run_with(bb_user="alice", bb_token="app_pw")
        joined = " ".join(" ".join(c) for c in both.commands)
        self.assertIn("url.https://alice:app_pw", joined)
        self.assertIn("@bitbucket.org/.insteadOf", joined)

    def test_all_three_providers_configured_together(self):
        recorder = self._run_with(github="gh", gitlab="gl", bb_user="alice", bb_token="bb")
        joined = " ".join(" ".join(c) for c in recorder.commands)
        self.assertEqual(len(recorder.commands), 6)
        self.assertIn("github.com/.insteadOf", joined)
        self.assertIn("gitlab.com/.insteadOf", joined)
        self.assertIn("bitbucket.org/.insteadOf", joined)

    def test_failure_is_swallowed_so_the_bot_still_boots(self):
        self._run_with(error=OSError("git not installed"))


class TestCloneRepository(CoreServiceTestCase):
    def test_rejects_malformed_url(self):
        res = self.arun(self.git_service.clone_repository("not a url"))
        self.assertFalse(res["success"])
        self.assertIn("Invalid git URL", res["error"])

    def test_rejects_leading_dash_argument_injection(self):
        res = self.arun(self.git_service.clone_repository("--upload-pack=touch /tmp/pwned"))
        self.assertFalse(res["success"])
        self.assertIn("Invalid git URL", res["error"])

    def test_rejects_folder_name_escaping_the_workspace(self):
        res = self.arun(self.git_service.clone_repository(
            "https://github.com/owner/repo.git", "../../etc"))
        self.assertFalse(res["success"])
        self.assertIn("Invalid folder name", res["error"])

    def test_rejects_existing_destination(self):
        (self.workspace / "repo").mkdir()
        res = self.arun(self.git_service.clone_repository("https://github.com/owner/repo.git"))
        self.assertFalse(res["success"])
        self.assertIn("already exists", res["error"])

    def test_success_injects_pat_into_github_url(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_secret")
        log = self.fake_git_bin()
        res = self.arun(self.git_service.clone_repository("https://github.com/owner/repo.git"))
        self.assertTrue(res["success"])
        self.assertEqual(res["folder_name"], "repo")
        # The returned git_url must be the CLEAN url -- the token-bearing one is
        # only ever handed to git, never surfaced back to a chat message.
        self.assertEqual(res["git_url"], "https://github.com/owner/repo.git")
        clone_log = log.read_text()
        self.assertIn("clone -- https://x-access-token:ghp_secret", clone_log)
        self.assertIn("@github.com/owner/repo.git", clone_log)

    def test_non_github_url_is_never_rewritten_with_a_github_token(self):
        """Sending the GitHub PAT to gitlab.com would leak it to a third party."""
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_secret")
        log = self.fake_git_bin()
        res = self.arun(self.git_service.clone_repository("https://gitlab.com/owner/repo.git"))
        self.assertTrue(res["success"])
        argv = log.read_text()
        self.assertNotIn("ghp_secret", argv)
        self.assertIn("clone -- https://gitlab.com/owner/repo.git", argv)

    def test_ssh_url_is_never_rewritten(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_secret")
        log = self.fake_git_bin()
        res = self.arun(self.git_service.clone_repository("git@github.com:owner/repo.git"))
        self.assertTrue(res["success"])
        self.assertNotIn("ghp_secret", log.read_text())

    def test_custom_folder_name_is_honored(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "")
        self.fake_git_bin()
        res = self.arun(self.git_service.clone_repository(
            "https://github.com/owner/repo.git", "my-checkout"))
        self.assertEqual(res["folder_name"], "my-checkout")
        self.assertTrue((self.workspace / "my-checkout").exists())

    def test_success_initializes_obsidian_project_spec(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "")
        self.fake_git_bin()
        self.arun(self.git_service.clone_repository("https://github.com/owner/repo.git"))
        spec = self.obsidian / "Projects" / "repo" / "project-spec.md"
        self.assertTrue(spec.exists())
        self.assertIn("https://github.com/owner/repo.git", spec.read_text())

    def test_bad_pat_failure_returns_git_stderr(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_wrong")
        self.fake_git_bin(exit_code=128, stderr_text="fatal: Authentication failed")
        res = self.arun(self.git_service.clone_repository("https://github.com/owner/repo.git"))
        self.assertFalse(res["success"])
        self.assertIn("Authentication failed", res["error"])
        # A failed clone must not leave a half-provisioned Obsidian spec behind.
        self.assertFalse((self.obsidian / "Projects" / "repo").exists())

    def test_missing_git_binary_is_reported_not_raised(self):
        self.patch(self.git_service, "GIT_BIN", str(self.tmp / "no-such-git"))
        res = self.arun(self.git_service.clone_repository("https://github.com/owner/repo.git"))
        self.assertFalse(res["success"])
        self.assertTrue(res["error"])


class TestCreateNewRepository(CoreServiceTestCase):
    def _github_ok(self):
        return FakeAsyncClient(FakeResponse(201, {
            "clone_url": "https://github.com/tester/newrepo.git",
            "html_url": "https://github.com/tester/newrepo",
            "owner": {"login": "tester"},
        }))

    def test_rejects_invalid_repo_name(self):
        res = self.arun(self.git_service.create_new_repository("bad name!"))
        self.assertFalse(res["success"])
        self.assertIn("Invalid repository name", res["error"])

    def test_rejects_traversal_repo_name(self):
        res = self.arun(self.git_service.create_new_repository("../escape"))
        self.assertFalse(res["success"])

    def test_rejects_existing_directory(self):
        (self.workspace / "taken").mkdir()
        res = self.arun(self.git_service.create_new_repository("taken"))
        self.assertFalse(res["success"])
        self.assertIn("already exists", res["error"])

    def test_requires_github_token(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "")
        res = self.arun(self.git_service.create_new_repository("newrepo"))
        self.assertFalse(res["success"])
        self.assertIn("GITHUB_TOKEN", res["error"])

    def test_success_scaffolds_local_repo_and_injects_pat_into_origin(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_secret")
        client = self._github_ok()
        self.patch(self.git_service, "httpx", FakeHttpx(client))
        log = self.fake_git_bin()

        res = self.arun(self.git_service.create_new_repository("newrepo", "My description"))
        self.assertTrue(res["success"])
        self.assertEqual(res["html_url"], "https://github.com/tester/newrepo")

        project = self.workspace / "newrepo"
        self.assertIn("My description", (project / "README.md").read_text())
        self.assertIn("__pycache__/", (project / ".gitignore").read_text())

        argv = log.read_text()
        self.assertIn("remote add origin https://x-access-token:ghp_secret", argv)
        self.assertIn("@github.com/tester/newrepo.git", argv)
        self.assertIn("push -u origin main", argv)

        body = client.calls[0][1]["json"]
        self.assertEqual(body["name"], "newrepo")
        self.assertEqual(body["description"], "My description")
        self.assertTrue(body["private"])
        self.assertFalse(body["auto_init"])
        self.assertEqual(client.calls[0][1]["headers"]["Authorization"], "Bearer ghp_secret")

    def test_default_description_when_none_given(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_secret")
        client = self._github_ok()
        self.patch(self.git_service, "httpx", FakeHttpx(client))
        self.fake_git_bin()
        self.arun(self.git_service.create_new_repository("newrepo"))
        self.assertIn("OMV Agent Station", client.calls[0][1]["json"]["description"])

    def test_api_error_is_surfaced_and_nothing_is_scaffolded(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_secret")
        self.patch(self.git_service, "httpx", FakeHttpx(
            FakeAsyncClient(FakeResponse(422, text="name already exists on this account")))
        )
        res = self.arun(self.git_service.create_new_repository("newrepo"))
        self.assertFalse(res["success"])
        self.assertIn("GitHub API error (422)", res["error"])
        self.assertFalse((self.workspace / "newrepo").exists())

    def test_unauthorized_pat_is_surfaced(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_revoked")
        self.patch(self.git_service, "httpx", FakeHttpx(
            FakeAsyncClient(FakeResponse(401, text="Bad credentials")))
        )
        res = self.arun(self.git_service.create_new_repository("newrepo"))
        self.assertFalse(res["success"])
        self.assertIn("401", res["error"])

    def test_network_failure_is_reported_not_raised(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_secret")
        self.patch(self.git_service, "httpx", FakeHttpx(
            FakeAsyncClient(error=RuntimeError("connection refused")))
        )
        res = self.arun(self.git_service.create_new_repository("newrepo"))
        self.assertFalse(res["success"])
        self.assertIn("connection refused", res["error"])

    def test_success_initializes_obsidian_project_spec(self):
        self.patch(self.git_service, "GITHUB_TOKEN", "ghp_secret")
        self.patch(self.git_service, "httpx", FakeHttpx(self._github_ok()))
        self.fake_git_bin()
        self.arun(self.git_service.create_new_repository("newrepo"))
        self.assertTrue((self.obsidian / "Projects" / "newrepo" / "project-spec.md").exists())


class TestPushPullDiff(CoreServiceTestCase):
    """These run against real git repositories with a real local bare remote."""

    def test_pull_rejects_non_repository(self):
        (self.workspace / "plain").mkdir()
        res = self.arun(self.git_service.git_pull_repo("plain"))
        self.assertFalse(res["success"])
        self.assertIn("not a valid git repository", res["error"])

    def test_pull_rejects_traversal(self):
        res = self.arun(self.git_service.git_pull_repo("../../etc"))
        self.assertFalse(res["success"])

    def test_pull_fetches_a_commit_made_on_the_remote(self):
        self.make_repo("myproj", with_remote=True)
        remote = self.tmp / "myproj-remote.git"
        other = self.tmp / "other-clone"
        subprocess.run(  # nosec B603,B607
            ["git", "clone", "-q", str(remote), str(other)],
            capture_output=True, text=True, check=True,
        )
        (other / "from-remote.txt").write_text("x")
        self.git(other, "add", ".")
        self.git(other, "commit", "-q", "-m", "remote side commit")
        self.git(other, "push", "-q", "origin", "main")

        res = self.arun(self.git_service.git_pull_repo("myproj"))
        self.assertTrue(res["success"], res)
        self.assertTrue((self.workspace / "myproj" / "from-remote.txt").exists())

    def test_pull_failure_when_no_remote_configured(self):
        self.make_repo("lonely")
        res = self.arun(self.git_service.git_pull_repo("lonely"))
        self.assertFalse(res["success"])
        self.assertTrue(res["output"])

    def test_push_rejects_non_repository(self):
        res = self.arun(self.git_service.git_push_repo("ghost"))
        self.assertFalse(res["success"])
        self.assertIn("not a valid git repository", res["error"])

    def test_push_lands_the_commit_on_the_remote(self):
        project = self.make_repo("myproj", with_remote=True)
        (project / "new.txt").write_text("x")
        self.git(project, "add", ".")
        self.git(project, "commit", "-q", "-m", "second")

        res = self.arun(self.git_service.git_push_repo("myproj"))
        self.assertTrue(res["success"], res)
        remote_log = subprocess.run(  # nosec B603,B607
            ["git", "log", "--oneline", "main"], cwd=str(self.tmp / "myproj-remote.git"),
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("second", remote_log)

    def test_push_falls_back_to_main_for_an_injection_style_branch(self):
        """`--delete` would otherwise be handed to git as a flag and wipe the
        remote branch; the sanitizer must collapse it to the safe default."""
        project = self.make_repo("myproj", with_remote=True)
        (project / "new.txt").write_text("x")
        self.git(project, "add", ".")
        self.git(project, "commit", "-q", "-m", "second")

        res = self.arun(self.git_service.git_push_repo("myproj", "--delete"))
        self.assertTrue(res["success"], res)
        branches = subprocess.run(  # nosec B603,B607
            ["git", "branch"], cwd=str(self.tmp / "myproj-remote.git"),
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("main", branches)

    def test_push_named_branch_only_updates_that_branch(self):
        project = self.make_repo("myproj", with_remote=True)
        self.git(project, "checkout", "-q", "-b", "feature")
        (project / "f.txt").write_text("f")
        self.git(project, "add", ".")
        self.git(project, "commit", "-q", "-m", "feature work")

        res = self.arun(self.git_service.git_push_repo("myproj", "feature"))
        self.assertTrue(res["success"], res)
        branches = subprocess.run(  # nosec B603,B607
            ["git", "branch"], cwd=str(self.tmp / "myproj-remote.git"),
            capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn("feature", branches)

    def test_push_failure_when_no_remote_configured(self):
        self.make_repo("lonely")
        res = self.arun(self.git_service.git_push_repo("lonely"))
        self.assertFalse(res["success"])

    def test_diff_rejects_non_repository(self):
        res = self.arun(self.git_service.git_diff_repo("ghost"))
        self.assertFalse(res["success"])

    def test_diff_is_empty_on_a_clean_tree(self):
        self.make_repo("myproj")
        res = self.arun(self.git_service.git_diff_repo("myproj"))
        self.assertTrue(res["success"])
        self.assertEqual(res["diff"], "")

    def test_diff_reports_uncommitted_changes(self):
        project = self.make_repo("myproj")
        (project / "README.md").write_text("totally different\n")
        res = self.arun(self.git_service.git_diff_repo("myproj"))
        self.assertIn("totally different", res["diff"])


class TestListWorkspaceProjects(CoreServiceTestCase):
    def test_empty_when_workspace_missing(self):
        self.patch(self.git_service, "WORKSPACE", self.tmp / "absent")
        self.assertEqual(self.git_service.list_workspace_projects(), [])

    def test_sorted_and_excludes_dotdirs_and_files(self):
        for name in ("zeta", "alpha", ".hidden"):
            (self.workspace / name).mkdir()
        (self.workspace / "loose.txt").write_text("x")
        self.assertEqual(self.git_service.list_workspace_projects(), ["alpha", "zeta"])


class TestSecuritySanitizers(CoreServiceTestCase):
    def test_project_path_accepts_plain_name(self):
        target = self.security.sanitize_project_path(self.workspace, "myproj")
        self.assertEqual(target, (self.workspace / "myproj").resolve())

    def test_project_path_accepts_nested_name(self):
        target = self.security.sanitize_project_path(self.workspace, "group/myproj")
        self.assertEqual(target, (self.workspace / "group" / "myproj").resolve())

    def test_project_path_rejects_traversal_and_absolute_and_flags(self):
        for bad in ("", "..", "../etc", "a/../../b", "/etc/passwd", "\\windows", "-rf", "./", "."):
            self.assertIsNone(self.security.sanitize_project_path(self.workspace, bad), bad)

    def test_project_path_rejects_symlink_escape(self):
        """A symlink inside the workspace pointing out of it must not become a
        usable project path -- resolve() follows it, and the parent check is
        what catches the escape."""
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.workspace / "escape").symlink_to(outside)
        self.assertIsNone(self.security.sanitize_project_path(self.workspace, "escape"))

    def test_repo_name_accepts_safe_names(self):
        for good in ("my-app", "my_app", "app.v2", "App123"):
            self.assertEqual(self.security.sanitize_repo_name(good), good)

    def test_repo_name_strips_surrounding_whitespace(self):
        self.assertEqual(self.security.sanitize_repo_name("  my-app  "), "my-app")

    def test_repo_name_rejects_unsafe_names(self):
        for bad in ("", "-flag", ".hidden", "a..b", "a/b", "a\\b", "my app", "emoji😀"):
            self.assertIsNone(self.security.sanitize_repo_name(bad), bad)

    def test_branch_name_accepts_safe_names(self):
        for good in ("main", "feature/x", "release-1.2", "a_b"):
            self.assertEqual(self.security.sanitize_branch_name(good), good)

    def test_branch_name_rejects_unsafe_names(self):
        for bad in ("", "-D", "a..b", "a\\b", "HEAD@{1}", "with space", "a;rm -rf /"):
            self.assertIsNone(self.security.sanitize_branch_name(bad), bad)

    def test_cmd_name_normalizes_slash_and_case(self):
        self.assertEqual(self.security.sanitize_cmd_name("/Test"), "test")
        self.assertEqual(self.security.sanitize_cmd_name("  my_cmd "), "my_cmd")

    def test_cmd_name_rejects_unsafe_names(self):
        for bad in ("", "bad-name", "with space", "a" * 33, "sh!"):
            self.assertIsNone(self.security.sanitize_cmd_name(bad), bad)

    def test_relative_path_accepts_nested_target(self):
        base = self.workspace
        target = self.security.sanitize_relative_path(base, "src/main.py")
        self.assertEqual(target, (base / "src" / "main.py").resolve())

    def test_relative_path_rejects_git_directory_write(self):
        """A write under .git is a code-execution vector via hooks."""
        for bad in (".git/hooks/pre-commit", "sub/.git/config"):
            self.assertIsNone(self.security.sanitize_relative_path(self.workspace, bad), bad)

    def test_relative_path_rejects_traversal_and_absolute(self):
        for bad in ("", "   ", "../outside.txt", "a/../../b", "/etc/passwd", "\\etc"):
            self.assertIsNone(self.security.sanitize_relative_path(self.workspace, bad), bad)

    def test_relative_path_rejects_the_base_itself(self):
        self.assertIsNone(self.security.sanitize_relative_path(self.workspace, "."))

    def test_git_url_accepts_supported_schemes(self):
        for good in (
            "https://github.com/owner/repo.git",
            "http://example.com/x/y",
            "git://example.com/x/y.git",
            "ssh://git@example.com/x/y.git",
            "git@github.com:owner/repo.git",
        ):
            self.assertEqual(self.security.sanitize_git_url(good), good, good)

    def test_git_url_rejects_injection_and_unsupported_forms(self):
        for bad in (
            "",
            "--upload-pack=evil",
            "-oProxyCommand=x",
            "file:///etc/passwd",
            "https://github.com/owner/repo with space",
            "just-a-string",
        ):
            self.assertIsNone(self.security.sanitize_git_url(bad), bad)


class TestCustomCmdsService(CoreServiceTestCase):
    def test_load_is_empty_when_nothing_stored(self):
        self.assertEqual(self.custom_cmds_service.load_custom_commands(), {})

    def test_save_writes_workspace_file_and_obsidian_mirror(self):
        self.custom_cmds_service.save_custom_commands({"t": "/exec pytest"})
        self.assertEqual(
            json.loads(self.custom_cmds_service.CUSTOM_CMDS_FILE.read_text()), {"t": "/exec pytest"})
        self.assertEqual(
            json.loads(self.custom_cmds_service.OBSIDIAN_CMDS_FILE.read_text()), {"t": "/exec pytest"})

    def test_save_creates_missing_parent_directories(self):
        self.patch(self.custom_cmds_service, "CUSTOM_CMDS_FILE",
                   self.workspace / "deep" / "nested" / "cmds.json")
        self.custom_cmds_service.save_custom_commands({"t": "x"})
        self.assertTrue(self.custom_cmds_service.CUSTOM_CMDS_FILE.exists())

    def test_load_roundtrips_what_save_wrote(self):
        self.custom_cmds_service.save_custom_commands({"a": "1", "b": "2"})
        self.assertEqual(self.custom_cmds_service.load_custom_commands(), {"a": "1", "b": "2"})

    def test_load_falls_back_to_obsidian_mirror(self):
        """The Obsidian vault is Syncthing-backed, so it survives a workspace
        volume being recreated -- that is the whole point of the mirror."""
        self.custom_cmds_service.OBSIDIAN_CMDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.custom_cmds_service.OBSIDIAN_CMDS_FILE.write_text(json.dumps({"restored": "/exec ls"}))
        self.assertEqual(self.custom_cmds_service.load_custom_commands(), {"restored": "/exec ls"})

    def test_load_falls_back_to_mirror_when_primary_is_corrupt(self):
        self.custom_cmds_service.CUSTOM_CMDS_FILE.write_text("{not json")
        self.custom_cmds_service.OBSIDIAN_CMDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.custom_cmds_service.OBSIDIAN_CMDS_FILE.write_text(json.dumps({"restored": "/exec ls"}))
        self.assertEqual(self.custom_cmds_service.load_custom_commands(), {"restored": "/exec ls"})

    def test_load_returns_empty_when_both_copies_are_corrupt(self):
        self.custom_cmds_service.CUSTOM_CMDS_FILE.write_text("{not json")
        self.custom_cmds_service.OBSIDIAN_CMDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.custom_cmds_service.OBSIDIAN_CMDS_FILE.write_text("also broken")
        self.assertEqual(self.custom_cmds_service.load_custom_commands(), {})

    def test_save_failures_are_swallowed(self):
        self.patch(self.custom_cmds_service, "CUSTOM_CMDS_FILE", self.workspace)
        self.patch(self.custom_cmds_service, "OBSIDIAN_CMDS_FILE", self.obsidian)
        self.custom_cmds_service.save_custom_commands({"t": "x"})

    def test_expand_unknown_command_is_none(self):
        self.assertIsNone(self.custom_cmds_service.expand_custom_command("ghost"))

    def test_expand_substitutes_args_placeholder(self):
        self.custom_cmds_service.save_custom_commands({"review": "/chat Review this: {args}"})
        self.assertEqual(
            self.custom_cmds_service.expand_custom_command("review", "main.py"),
            "/chat Review this: main.py")

    def test_expand_with_placeholder_and_no_args_leaves_it_blank(self):
        self.custom_cmds_service.save_custom_commands({"review": "/chat Review: {args}"})
        self.assertEqual(self.custom_cmds_service.expand_custom_command("review"), "/chat Review:")

    def test_expand_appends_args_when_no_placeholder(self):
        self.custom_cmds_service.save_custom_commands({"t": "/exec pytest"})
        self.assertEqual(self.custom_cmds_service.expand_custom_command("t", "-v"), "/exec pytest -v")

    def test_expand_without_args_returns_template(self):
        self.custom_cmds_service.save_custom_commands({"t": "/exec pytest"})
        self.assertEqual(self.custom_cmds_service.expand_custom_command("t"), "/exec pytest")


if __name__ == "__main__":
    unittest.main()
