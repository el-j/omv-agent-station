"""
Coverage for the Debian package lifecycle scripts.

These guard against the RPC 500 bug (GitHub issue #3): the WebGUI installs
this plugin over an active RPC session, so postinst/postrm must never
restart openmediavault-engined synchronously -- that kills the very socket
serving the install request ("Failed to read from socket: Connection reset
by peer"). They must instead arm dpkg triggers so OMV core restarts engined
and recompiles the workbench only after the whole transaction (and the RPC
call driving it) has finished.

The module is split by what each test actually proves (GitHub issue #61):

TestPackagingStaticAssertions reads the maintainer scripts and build/install
scripts as text and asserts substrings are present or absent. Cheap, runs
anywhere, and catches an accidental deletion -- but a script that contains
`dpkg-trigger update-workbench` inside a branch that never executes, or that
fails on line 1, still passes.

TestMaintainerScriptsExecuted actually runs debian/postinst and debian/postrm
under /bin/sh and asserts on their real exit status and real side effects:
which triggers were fired, which files ended up removed, and -- the point of
issue #3 -- that systemctl was never invoked at all.

TestVersionResolutionExecuted runs scripts/resolve-version.sh for real.
"""

import json
import os
import shutil
import stat
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DEBIAN_DIR = ROOT_DIR / "openmediavault-agent-station" / "debian"

# Commands the maintainer scripts invoke that must not touch the real system
# (or, for systemctl, must not be invoked at all) while under test.
SHIMMED_COMMANDS = ("mkdir", "rm", "dpkg-trigger", "systemctl")

# Redirects absolute paths into the fake root, so `mkdir -p /var/cache/...`
# and `rm -f /etc/...` act on the sandbox instead of the machine running the
# tests -- the same redirection a chroot would do, done in userland so the
# scripts themselves run completely unmodified.
_REDIRECTING_SHIM = '''#!/usr/bin/env python3
import os, subprocess, sys
root = os.environ["FAKE_ROOT"]
real = os.environ["REAL_" + os.path.basename(sys.argv[0]).replace("-", "_").upper()]
args = [root + a if a.startswith("/") else a for a in sys.argv[1:]]
sys.exit(subprocess.call([real] + args))
'''

# Records the invocation instead of running anything, so a test can assert on
# exactly which triggers were armed -- and that systemctl was never reached.
_RECORDING_SHIM = '''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["INVOCATION_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps([os.path.basename(sys.argv[0])] + sys.argv[1:]) + "\\n")
'''


class MaintainerScriptSandbox:
    """Runs a real maintainer script against a fake filesystem root."""

    def __init__(self, tmpdir: Path):
        self.root = tmpdir / "root"
        self.shims = tmpdir / "shims"
        self.log = tmpdir / "invocations.log"
        for d in (self.root, self.shims):
            d.mkdir(parents=True)
        self.log.touch()

        self.env = {**os.environ, "FAKE_ROOT": str(self.root), "INVOCATION_LOG": str(self.log)}
        for name in SHIMMED_COMMANDS:
            recording = name in ("dpkg-trigger", "systemctl")
            shim = self.shims / name
            shim.write_text(_RECORDING_SHIM if recording else _REDIRECTING_SHIM, encoding="utf-8")
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            if not recording:
                real = shutil.which(name)
                if real is None:
                    raise RuntimeError(f"required command {name} not found")
                self.env["REAL_" + name.replace("-", "_").upper()] = real
        self.env["PATH"] = f"{self.shims}{os.pathsep}{os.environ['PATH']}"

    def touch(self, absolute_path: str, content: str = "{}") -> Path:
        """Seeds a file inside the fake root at an absolute production path."""
        target = self.root / absolute_path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def path(self, absolute_path: str) -> Path:
        return self.root / absolute_path.lstrip("/")

    def run(self, script_name: str, *args) -> subprocess.CompletedProcess:
        return subprocess.run(  # nosec B603
            ["/bin/sh", str(DEBIAN_DIR / script_name), *args],
            capture_output=True, text=True, env=self.env, cwd=str(self.root),
        )

    def invocations(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line]


class TestMaintainerScriptsExecuted(unittest.TestCase):
    """Executes debian/postinst and debian/postrm and asserts on real effects."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.sandbox = MaintainerScriptSandbox(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def assertNoServiceRestart(self):
        """Issue #3, verified by execution rather than by grep: nothing in the
        run may shell out to systemctl, because a synchronous engined restart
        kills the RPC session performing the install."""
        systemctl_calls = [c for c in self.sandbox.invocations() if c[0] == "systemctl"]
        self.assertEqual(systemctl_calls, [], "maintainer script invoked systemctl during the transaction")

    def triggers(self) -> list[list[str]]:
        return [c[1:] for c in self.sandbox.invocations() if c[0] == "dpkg-trigger"]

    def test_postinst_configure_arms_workbench_trigger_and_creates_archives_dir(self):
        res = self.sandbox.run("postinst", "configure")

        self.assertEqual(res.returncode, 0, f"postinst configure failed: {res.stderr}")
        self.assertTrue(
            self.sandbox.path("/var/cache/openmediavault/archives").is_dir(),
            "postinst did not create the local deb repo archives directory",
        )
        self.assertIn(["update-workbench"], self.triggers())
        self.assertNoServiceRestart()

    def test_postinst_abort_paths_are_no_ops(self):
        for arg in ("abort-upgrade", "abort-remove", "abort-deconfigure"):
            with self.subTest(arg=arg):
                res = self.sandbox.run("postinst", arg)
                self.assertEqual(res.returncode, 0, f"postinst {arg} failed: {res.stderr}")
        self.assertEqual(self.triggers(), [], "an abort path armed a trigger it should not have")
        self.assertNoServiceRestart()

    def test_postinst_rejects_unknown_argument(self):
        res = self.sandbox.run("postinst", "not-a-real-dpkg-action")

        self.assertEqual(res.returncode, 1)
        self.assertIn("unknown argument", res.stderr)

    def test_postrm_purge_removes_only_this_plugins_config(self):
        own_config = self.sandbox.touch("/etc/openmediavault-agent-station.json")
        legacy_config = self.sandbox.touch("/etc/openmediavault-ai-orchestrator.json")
        other_plugin_config = self.sandbox.touch("/etc/openmediavault-someotherplugin.json")
        shared_cache = self.sandbox.touch("/var/cache/openmediavault/cache.omv-someotherplugin.json")

        res = self.sandbox.run("postrm", "purge")

        self.assertEqual(res.returncode, 0, f"postrm purge failed: {res.stderr}")
        self.assertFalse(own_config.exists(), "purge left this plugin's config behind")
        self.assertFalse(legacy_config.exists(), "purge left the legacy orchestrator config behind")
        self.assertTrue(other_plugin_config.exists(), "purge deleted another plugin's config")
        self.assertTrue(shared_cache.exists(), "purge wiped the shared openmediavault cache")
        self.assertIn(["update-workbench"], self.triggers())
        self.assertNoServiceRestart()

    def test_postrm_remove_arms_trigger_but_keeps_config(self):
        own_config = self.sandbox.touch("/etc/openmediavault-agent-station.json")

        res = self.sandbox.run("postrm", "remove")

        self.assertEqual(res.returncode, 0, f"postrm remove failed: {res.stderr}")
        self.assertTrue(own_config.exists(), "a plain remove (not purge) must keep the config for reinstall")
        self.assertIn(["update-workbench"], self.triggers())
        self.assertNoServiceRestart()

    def test_postrm_upgrade_paths_are_no_ops(self):
        for arg in ("upgrade", "failed-upgrade", "abort-install", "abort-upgrade"):
            with self.subTest(arg=arg):
                res = self.sandbox.run("postrm", arg)
                self.assertEqual(res.returncode, 0, f"postrm {arg} failed: {res.stderr}")
        self.assertEqual(self.triggers(), [], "an upgrade path armed a trigger it should not have")
        self.assertNoServiceRestart()

    def test_postrm_rejects_unknown_argument(self):
        res = self.sandbox.run("postrm", "not-a-real-dpkg-action")

        self.assertEqual(res.returncode, 1)
        self.assertIn("unknown argument", res.stderr)


class TestPackagingStaticAssertions(unittest.TestCase):
    """Substring assertions over packaging scripts. Nothing here is executed."""

    def test_postinst_never_restarts_engined_synchronously(self):
        postinst = (DEBIAN_DIR / "postinst").read_text(encoding="utf-8")
        self.assertNotIn("systemctl restart openmediavault-engined", postinst)
        self.assertNotIn("systemctl restart omv-engined", postinst)

    def test_postinst_activates_update_workbench_trigger(self):
        postinst = (DEBIAN_DIR / "postinst").read_text(encoding="utf-8")
        self.assertIn("dpkg-trigger update-workbench", postinst)

    def test_triggers_file_declares_restart_engined(self):
        triggers_file = DEBIAN_DIR / "triggers"
        self.assertTrue(triggers_file.exists(), "debian/triggers is required so dpkg defers the engined restart")
        content = triggers_file.read_text(encoding="utf-8")
        self.assertIn("activate restart-engined", content)

    def test_postrm_never_restarts_engined_synchronously(self):
        postrm = (DEBIAN_DIR / "postrm").read_text(encoding="utf-8")
        self.assertNotIn("systemctl restart openmediavault-engined", postrm)

    def test_postrm_uses_trigger_instead_of_direct_mkworkbench(self):
        postrm = (DEBIAN_DIR / "postrm").read_text(encoding="utf-8")
        self.assertIn("dpkg-trigger update-workbench", postrm)

    def test_postrm_does_not_wipe_shared_openmediavault_cache(self):
        """postrm must only clean up this plugin's own assets, never every
        plugin's cached schema files under /var/cache/openmediavault/."""
        postrm = (DEBIAN_DIR / "postrm").read_text(encoding="utf-8")
        self.assertNotIn('-name "cache.*" -delete', postrm)

    def test_uninstall_script_does_not_suppress_mkworkbench_errors(self):
        uninstall_script = (ROOT_DIR / "scripts" / "uninstall-plugin.sh").read_text(encoding="utf-8")
        self.assertNotIn("omv-mkworkbench all 2>/dev/null", uninstall_script)

    def test_install_script_does_not_suppress_mkworkbench_errors(self):
        install_script = (ROOT_DIR / "scripts" / "install-plugin.sh").read_text(encoding="utf-8")
        self.assertNotIn("omv-mkworkbench all 2>/dev/null", install_script)

    def test_control_depends_accepts_docker_ce_cli(self):
        """A fresh OMV install with Docker set up via Docker's own official
        apt repo (get.docker.com / docs.docker.com) provides the package
        docker-ce-cli, not docker-cli/docker.io. Reproduced by installing on
        a clean OrbStack Debian 13 + OMV 8.5.6 VM: apt refused to configure
        this package because the second alternation group in Depends only
        listed docker-cli | podman-docker | docker.io, none of which were
        satisfied even though a fully working Docker CLI was present."""
        control = (DEBIAN_DIR / "control").read_text(encoding="utf-8")
        depends_line = next(line for line in control.splitlines() if line.startswith("Depends:"))
        self.assertIn("docker-ce-cli", depends_line)

    def test_build_script_uses_dynamic_version_resolution(self):
        build_script = (ROOT_DIR / "build-deb.sh").read_text(encoding="utf-8")
        self.assertNotIn('VERSION="0.0.2-beta.2"', build_script)
        self.assertIn("resolve-version.sh", build_script)
        self.assertIn("AGENT_STATION_VERSION", build_script)
        self.assertIn('sed -i.bak -E "s/^Version:.*/Version: ${VERSION}/"', build_script)

    def test_install_script_supports_explicit_version_tags(self):
        install_script = (ROOT_DIR / "scripts" / "install-plugin.sh").read_text(encoding="utf-8")
        self.assertIn("VERSION_TAG", install_script)
        self.assertIn("REQUESTED_VERSION", install_script)
        self.assertIn("fetch --tags", install_script)
        self.assertIn("refs/tags/${REQUESTED_REF}", install_script)
        self.assertIn("refs/tags/v${REQUESTED_REF#v}", install_script)
        self.assertIn("dpkg -i", install_script)


class TestVersionResolutionExecuted(unittest.TestCase):
    def test_resolve_version_handles_branch_and_tag_inputs(self):
        import re
        script = ROOT_DIR / "scripts" / "resolve-version.sh"
        bash_exe = shutil.which("bash") or "/bin/bash"

        # Explicit SemVer tag with leading 'v'
        out = subprocess.check_output([bash_exe, str(script)], env={"VERSION_TAG": "v0.0.1"}, text=True).strip()  # nosec B603
        self.assertEqual(out, "0.0.1")

        # Explicit SemVer tag without leading 'v'
        out = subprocess.check_output([bash_exe, str(script)], env={"AGENT_STATION_VERSION": "0.0.2-beta.2"}, text=True).strip()  # nosec B603
        self.assertEqual(out, "0.0.2-beta.2")

        # Branch name 'develop' must resolve to a SemVer starting with a digit, NOT literal string 'develop'
        out = subprocess.check_output([bash_exe, str(script)], env={"BRANCH": "develop", "AGENT_STATION_VERSION": "develop"}, text=True).strip()  # nosec B603
        self.assertTrue(re.match(r"^[0-9]+\.[0-9]+\.[0-9]+(-beta\.[0-9]+)?$", out), f"Resolved version '{out}' is not valid SemVer")

        # Branch name 'main' must resolve to a valid SemVer
        out = subprocess.check_output([bash_exe, str(script)], env={"BRANCH": "main", "AGENT_STATION_VERSION": "main"}, text=True).strip()  # nosec B603
        self.assertTrue(re.match(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$", out), f"Resolved version '{out}' is not valid SemVer")


class TestNoVendoredStackDuplicate(unittest.TestCase):
    """Guards against the stale duplicate stack tree (GitHub issue #71) coming back.

    build-deb.sh copies the packaged stack fresh from the top-level
    telegram-agent-bot/, discord-agent-bot/, signal-agent-bot/, agent_station_core/,
    agent-workspace/, docker-compose.yml, and litellm/config.yaml into build-pkg/
    (gitignored) at build time -- nothing should ever commit a second, manually
    maintained copy of any of them under openmediavault-agent-station/.
    """

    def test_omv_share_dir_has_no_vendored_stack_copies(self):
        share_dir = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "agent-station"
        forbidden = [
            "telegram-agent-bot",
            "discord-agent-bot",
            "signal-agent-bot",
            "agent_station_core",
            "agent-workspace",
            "docker-compose.yml",
            "litellm",
        ]
        for name in forbidden:
            self.assertFalse(
                (share_dir / name).exists(),
                f"{share_dir / name} should not exist -- it's a stale vendored copy; "
                "build-deb.sh copies from the top-level source directories at build time instead.",
            )


if __name__ == "__main__":
    unittest.main()
