"""
Web-terminal (ttyd, port 7681) authentication enforcement (GitHub issue #64).

The plugin's Security form page lets an admin set terminal_user/terminal_pass;
/usr/sbin/omv-agent-station reads them out of the config into TERMINAL_USER /
TERMINAL_PASS, and docker-compose.yml passes them to ttyd as `-c user:pass`.
Nothing verified that this actually keeps anyone out -- a typo in the flag, or
ttyd changing its credential handling, would silently expose a root-capable
shell on the LAN.

This starts the real web-terminal container with the real command line taken
from docker-compose.yml (not a hand-written approximation) and checks that an
unauthenticated request is rejected, a wrong-password request is rejected, and
the configured credentials get in.

Requires a Docker daemon and the agent-station-workspace image; both are
skipped with an explicit reason when absent, never silently passed.
"""

import base64
import re
import shlex
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dockerutil

COMPOSE_FILE = ROOT_DIR / "docker-compose.yml"
SERVICE = "web-terminal"
TEST_USER = "omvtestadmin"
TEST_PASS = "s3cret-terminal-pass"

DOCKER_SKIP_REASON = dockerutil.docker_unavailable_reason()


def _compose_service() -> dict:
    import yaml
    with open(COMPOSE_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["services"][SERVICE]


def _expand(value: str, overrides: dict) -> str:
    """Resolves ${VAR} / ${VAR:-default} the way docker compose would."""
    def repl(match):
        name, default = match.group(1), match.group(2)
        if name in overrides:
            return overrides[name]
        return default if default is not None else ""
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}", repl, value)


class TestWebTerminalCommandStaticAssertions(unittest.TestCase):
    """Reads docker-compose.yml. No container is started."""

    def test_ttyd_is_launched_with_credential_enforcement(self):
        service = _compose_service()
        command = _expand(service["command"], {})
        argv = shlex.split(command)

        self.assertIn("-c", argv, "ttyd is started without -c: the web terminal would accept anyone")
        credential = argv[argv.index("-c") + 1]
        self.assertIn(":", credential, f"ttyd -c argument is not user:pass ({credential!r})")

    def test_terminal_credentials_come_from_plugin_settings(self):
        service = _compose_service()
        self.assertIn("TERMINAL_USER", service["command"])
        self.assertIn("TERMINAL_PASS", service["command"])

        cli = (ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station").read_text(encoding="utf-8")
        self.assertIn("terminal_user", cli)
        self.assertIn("terminal_pass", cli)
        self.assertIn("TERMINAL_USER", cli)
        self.assertIn("TERMINAL_PASS", cli)


@unittest.skipIf(DOCKER_SKIP_REASON is not None, f"requires a Docker daemon ({DOCKER_SKIP_REASON})")
class TestWebTerminalAuthEnforced(unittest.TestCase):
    """Starts the real ttyd container and probes its auth for real."""

    image = None
    container = None
    port = None

    @classmethod
    def setUpClass(cls):
        service = _compose_service()
        cls.image = service["image"]
        if not dockerutil.image_exists(cls.image):
            raise unittest.SkipTest(
                f"image {cls.image} not built -- run `docker compose build {SERVICE}` first"
            )

        command = shlex.split(_expand(
            service["command"], {"TERMINAL_USER": TEST_USER, "TERMINAL_PASS": TEST_PASS}
        ))
        cls.port = dockerutil.free_port()
        cls.container = dockerutil.Container(
            cls.image, command=command, ports={cls.port: 7681},
        ).start()
        try:
            cls.container.wait_for_port(cls.port)
            cls.container.wait_for_http(f"http://127.0.0.1:{cls.port}/")
        except Exception:
            cls.container.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.container is not None:
            cls.container.stop()

    def _get(self, user=None, password=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/")
        if user is not None:
            token = base64.b64encode(f"{user}:{password}".encode()).decode()
            req.add_header("Authorization", f"Basic {token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_unauthenticated_request_is_rejected(self):
        self.assertEqual(self._get(), 401, "the web terminal served an unauthenticated request")

    def test_wrong_password_is_rejected(self):
        self.assertEqual(self._get(TEST_USER, "not-the-password"), 401)

    def test_wrong_user_is_rejected(self):
        self.assertEqual(self._get("someone-else", TEST_PASS), 401)

    def test_configured_credentials_are_accepted(self):
        self.assertEqual(
            self._get(TEST_USER, TEST_PASS), 200,
            "the credentials set in the plugin's Security form were rejected by ttyd",
        )


if __name__ == "__main__":
    unittest.main()
