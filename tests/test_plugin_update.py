"""
Black-box tests for the plugin self-update mechanism (`omv-agent-station
check-update` / `update-plugin`), requested so users can update the
installed OMV plugin from a new GitHub release without SSH access.

Real network calls (curl to api.github.com and the release asset) and the
real dpkg/apt-get toolchain are replaced with fake shell functions loaded
via BASH_ENV. Plain PATH-prepend shadowing doesn't work here because the
script itself does `export PATH="/usr/local/sbin:...:$PATH"` at startup,
which puts real system binaries (curl is present even on macOS) ahead of
anything a test could prepend beforehand -- but bash always resolves a
function before searching PATH, and BASH_ENV's startup file is sourced
into the script's own shell before that reassignment even runs, so
functions defined there win regardless. This keeps these tests
deterministic without touching the network or the host package database.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
CLI_BIN = ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station"

FAKE_FUNCS = """
curl() {
  local outfile=""
  local prev=""
  for arg in "$@"; do
    if [ "$prev" = "-o" ]; then
      outfile="$arg"
    fi
    prev="$arg"
  done
  if [ -n "$outfile" ]; then
    if [ "${FAKE_CURL_DOWNLOAD_FAIL:-0}" = "1" ]; then
      return 22
    fi
    printf '%s' "${FAKE_CURL_ASSET_CONTENT:-fakedebcontent}" > "$outfile"
    return 0
  fi
  if [ "${FAKE_CURL_API_FAIL:-0}" = "1" ]; then
    return 22
  fi
  printf '%s' "$FAKE_CURL_API_OUTPUT"
  return 0
}

dpkg-query() {
  printf '%s' "${FAKE_CURRENT_VERSION:-unknown}"
}

dpkg() {
  if [ "$1" = "--compare-versions" ]; then
    python3 -c "
import sys
def key(v):
    return [int(p) if p.isdigit() else p for p in v.replace('-', '.').split('.')]
a, op, b = sys.argv[1], sys.argv[2], sys.argv[3]
ka, kb = key(a), key(b)
result = {'lt': ka < kb, 'gt': ka > kb, 'eq': ka == kb, 'le': ka <= kb, 'ge': ka >= kb}.get(op, False)
sys.exit(0 if result else 1)
" "$2" "$3" "$4"
    return $?
  fi
  return 1
}

dpkg-deb() {
  if [ "$1" = "--info" ]; then
    return "${FAKE_DPKGDEB_EXIT:-0}"
  fi
  return 0
}

apt-get() {
  if [ "$1" = "install" ]; then
    echo "fake-apt-get: would install $*"
    return "${FAKE_APT_EXIT:-0}"
  fi
  return 0
}
"""


class _PluginUpdateTestBase(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CLI_BIN.exists())
        self._tmpdir = tempfile.TemporaryDirectory()
        funcs_path = Path(self._tmpdir.name) / "fake_funcs.sh"
        funcs_path.write_text(FAKE_FUNCS, encoding="utf-8")

        self.env = os.environ.copy()
        self.env["BASH_ENV"] = str(funcs_path)

        release_payload = {
            "tag_name": "v0.0.5",
            "html_url": "https://github.com/el-j/omv-agent-station/releases/tag/v0.0.5",
            "published_at": "2026-08-20T00:00:00Z",
            "assets": [
                {"name": "openmediavault-agent-station_0.0.5_all.deb",
                 "browser_download_url": "https://github.com/el-j/omv-agent-station/releases/download/v0.0.5/openmediavault-agent-station_0.0.5_all.deb"}
            ],
        }
        self.env["FAKE_CURL_API_OUTPUT"] = json.dumps(release_payload)

    def tearDown(self):
        self._tmpdir.cleanup()

    def run_cli(self, *args):
        return subprocess.run(  # nosec B603,B607
            ["bash", str(CLI_BIN), *args], env=self.env, capture_output=True, text=True
        )


class TestPluginCheckForUpdate(_PluginUpdateTestBase):
    def test_reports_update_available_when_current_is_older(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.1"
        res = self.run_cli("check-update")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertEqual(data["current_version"], "0.0.1")
        self.assertEqual(data["latest_version"], "0.0.5")
        self.assertTrue(data["update_available"])
        self.assertEqual(
            data["asset_url"],
            "https://github.com/el-j/omv-agent-station/releases/download/v0.0.5/openmediavault-agent-station_0.0.5_all.deb",
        )
        self.assertIn("github.com", data["release_url"])

    def test_reports_no_update_when_current_is_latest(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.5"
        res = self.run_cli("check-update")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(json.loads(res.stdout)["update_available"])

    def test_reports_no_update_when_current_is_newer(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.9"
        res = self.run_cli("check-update")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(json.loads(res.stdout)["update_available"])

    def test_network_failure_reports_error_without_crashing(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.1"
        self.env["FAKE_CURL_API_FAIL"] = "1"
        res = self.run_cli("check-update")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = json.loads(res.stdout)
        self.assertIn("error", data)
        self.assertEqual(data["current_version"], "0.0.1")


class TestPluginUpdatePlugin(_PluginUpdateTestBase):
    def test_noop_when_already_up_to_date(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.5"
        res = self.run_cli("update-plugin")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Already running the latest version", res.stdout)

    def test_downloads_and_installs_when_update_available(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.1"
        res = self.run_cli("update-plugin")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Downloading", res.stdout)
        self.assertIn("Update installed successfully", res.stdout)

    def test_refuses_asset_url_not_hosted_on_github(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.1"
        payload = json.loads(self.env["FAKE_CURL_API_OUTPUT"])
        payload["assets"][0]["browser_download_url"] = "https://evil.example.com/malicious.deb"
        self.env["FAKE_CURL_API_OUTPUT"] = json.dumps(payload)

        res = self.run_cli("update-plugin")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("untrusted host", res.stdout)

    def test_aborts_when_downloaded_file_is_not_a_valid_deb(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.1"
        self.env["FAKE_DPKGDEB_EXIT"] = "1"
        res = self.run_cli("update-plugin")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("not a valid .deb", res.stdout)

    def test_aborts_when_install_fails(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.1"
        self.env["FAKE_APT_EXIT"] = "1"
        res = self.run_cli("update-plugin")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("installation failed", res.stdout)

    def test_aborts_when_release_has_no_deb_asset(self):
        self.env["FAKE_CURRENT_VERSION"] = "0.0.1"
        payload = json.loads(self.env["FAKE_CURL_API_OUTPUT"])
        payload["assets"] = []
        self.env["FAKE_CURL_API_OUTPUT"] = json.dumps(payload)

        res = self.run_cli("update-plugin")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("no .deb asset", res.stdout)


if __name__ == "__main__":
    unittest.main()
