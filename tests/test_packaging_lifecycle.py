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


if __name__ == "__main__":
    unittest.main()
