"""
Regression tests for the Debian package lifecycle scripts.

These guard against the RPC 500 bug (GitHub issue #3): the WebGUI installs
this plugin over an active RPC session, so postinst/postrm must never
restart openmediavault-engined synchronously -- that kills the very socket
serving the install request ("Failed to read from socket: Connection reset
by peer"). They must instead arm dpkg triggers so OMV core restarts engined
and recompiles the workbench only after the whole transaction (and the RPC
call driving it) has finished.
"""

import unittest
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DEBIAN_DIR = ROOT_DIR / "openmediavault-agent-station" / "debian"


class TestPackagingLifecycleTriggers(unittest.TestCase):
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

    def test_resolve_version_handles_branch_and_tag_inputs(self):
        import re
        import subprocess  # nosec B404
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
