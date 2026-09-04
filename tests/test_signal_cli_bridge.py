"""
signal-cli bridge integration (GitHub issue #64).

signal-agent-bot talks to the signal-cli-rest-api container two ways: it POSTs
to /v2/send, and it holds a WebSocket open on /v1/receive/<number>, which only
exists when the container runs in MODE=json-rpc. Every existing Signal test
replaces both with fakes, so nothing proved the compose-declared container
speaks the protocol the bot expects.

These tests start the real bbernhard/signal-cli-rest-api container using the
image and environment declared in docker-compose.yml, then drive the bot's own
unmodified client code against it.

Honest boundary: delivering an actual Signal message requires an account
registered to a real phone number (SMS/captcha verification), which cannot be
automated and would send traffic over Signal's live network. So what is
verified here is that the bridge really comes up in JSON-RPC mode, that the
bot's real WebSocket listener connects to it, and that the bot's real send and
attachment-download paths reach the real endpoints and get signal-cli's real
answers. The end-to-end delivery test is present but skipped unless
SIGNAL_TEST_NUMBER names a registered account.
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dockerutil
import stubs

COMPOSE_FILE = ROOT_DIR / "docker-compose.yml"
SERVICE = "signal-cli"
DOCKER_SKIP_REASON = dockerutil.docker_unavailable_reason()
REGISTERED_TEST_NUMBER = os.environ.get("SIGNAL_TEST_NUMBER")

# A number the container has no account for. Requests using it still exercise
# the full transport; signal-cli answers with its own "account does not exist".
UNREGISTERED_NUMBER = "+15550001111"


def _compose_service() -> dict:
    import yaml
    with open(COMPOSE_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["services"][SERVICE]


def _compose_environment(service: dict) -> dict:
    env = service.get("environment") or []
    if isinstance(env, dict):
        return {k: str(v) for k, v in env.items()}
    return dict(item.split("=", 1) for item in env)


class TestSignalComposeStaticAssertions(unittest.TestCase):
    """Reads docker-compose.yml. No container is started."""

    def test_bridge_runs_in_json_rpc_mode(self):
        """signal_bot.signal_event_listener() opens a WebSocket on
        /v1/receive/<number>, which the REST API only serves in json-rpc mode."""
        self.assertEqual(_compose_environment(_compose_service()).get("MODE"), "json-rpc")

    def test_bot_points_at_the_bridge_service(self):
        import yaml
        with open(COMPOSE_FILE, "r", encoding="utf-8") as f:
            services = yaml.safe_load(f)["services"]
        bot_env = _compose_environment(services["signal-bot"])
        self.assertEqual(bot_env.get("SIGNAL_CLI_URL"), "http://signal-cli:8080")
        self.assertIn(SERVICE, services["signal-bot"]["depends_on"])


@unittest.skipIf(DOCKER_SKIP_REASON is not None, f"requires a Docker daemon ({DOCKER_SKIP_REASON})")
class TestSignalCliBridgeLive(unittest.TestCase):
    """Runs the real signal-cli container and drives the bot's real client code."""

    container = None
    port = None

    @classmethod
    def setUpClass(cls):
        service = _compose_service()
        image = service["image"]
        if not dockerutil.image_exists(image):
            raise unittest.SkipTest(f"image {image} not present -- run `docker pull {image}` first")

        cls.port = dockerutil.free_port()
        cls.container = dockerutil.Container(
            image, env=_compose_environment(service), ports={cls.port: 8080},
        ).start()
        try:
            cls.container.wait_for_port(cls.port, timeout=180)
            cls._wait_for_rest_api()
        except Exception:
            cls.container.stop()
            raise

    @classmethod
    def _wait_for_rest_api(cls, timeout=180.0):
        import json
        import time
        import urllib.error
        import urllib.request
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(  # nosec B310
                    f"http://127.0.0.1:{cls.port}/v1/about", timeout=5
                ) as resp:
                    if resp.status == 200:
                        cls.about = json.loads(resp.read())
                        return
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        raise RuntimeError(f"signal-cli REST API never answered:\n{cls.container.logs()[-4000:]}")

    @classmethod
    def tearDownClass(cls):
        if cls.container is not None:
            cls.container.stop()

    def setUp(self):
        # stubs.py replaces httpx/websockets with MagicMocks for the bots that
        # never touch a real network. This suite does, so the real libraries go
        # back for its duration and the mocks are restored afterwards.
        self._swapped = {}
        for name in ("httpx", "websockets"):
            current = sys.modules.get(name)
            if isinstance(current, MagicMock):
                self._swapped[name] = current
                del sys.modules[name]
        __import__("httpx")
        __import__("websockets")

        stubs.purge_bot_modules("core", "handlers", "signal_bot")
        sys.path.insert(0, str(ROOT_DIR / "signal-agent-bot"))
        import core.messaging as messaging
        import handlers.upload as upload
        import signal_bot
        self.messaging = messaging
        self.upload = upload
        self.signal_bot = signal_bot

        # SIGNAL_API_URL is imported by value into every module that uses it.
        bridge_url = f"http://127.0.0.1:{self.port}"
        for mod in (messaging, signal_bot, upload):
            mod.SIGNAL_API_URL = bridge_url
        for mod in (messaging, signal_bot):
            mod.SIGNAL_PHONE_NUMBER = REGISTERED_TEST_NUMBER or UNREGISTERED_NUMBER

    def tearDown(self):
        if str(ROOT_DIR / "signal-agent-bot") in sys.path:
            sys.path.remove(str(ROOT_DIR / "signal-agent-bot"))
        stubs.purge_bot_modules("core", "handlers", "signal_bot")
        for name, mock in self._swapped.items():
            sys.modules[name] = mock

    def test_bridge_reports_json_rpc_mode(self):
        """The compose-declared MODE really produces the JSON-RPC bridge; in
        the default 'normal' mode /v1/receive is polling-only and the bot's
        WebSocket listener would never receive anything."""
        self.assertEqual(self.about.get("mode"), "json-rpc", f"/v1/about reported {self.about}")

    def test_bot_websocket_listener_connects_to_the_real_bridge(self):
        """Runs signal_bot.signal_event_listener() unmodified against the live
        container. Its own log line is the evidence the connection was
        established rather than falling into the reconnect loop."""
        async def scenario():
            task = asyncio.create_task(self.signal_bot.signal_event_listener())
            await asyncio.sleep(6)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        with self.assertLogs("agent_station", level="INFO") as captured:
            asyncio.run(scenario())

        self.assertTrue(
            any("Connected to Signal WebSocket stream." in line for line in captured.output),
            f"listener never connected to the bridge: {captured.output}",
        )
        self.assertFalse(
            any("WebSocket disconnected" in line for line in captured.output),
            f"listener fell into its reconnect loop: {captured.output}",
        )

    def test_bot_send_path_reaches_the_real_send_endpoint(self):
        """send_signal_message() swallows transport errors by design, so the
        warning it logs is what proves the POST reached signal-cli's real
        /v2/send and came back with signal-cli's own answer -- rather than,
        say, a 404 from a wrong path or a refused connection."""
        with self.assertLogs("agent_station", level="WARNING") as captured:
            asyncio.run(self.messaging.send_signal_message("+15550002222", "hello from the test suite"))

        joined = "\n".join(captured.output)
        self.assertIn("Failed to send Signal message: 400", joined)
        self.assertIn("account does not exist", joined)

    def test_bot_attachment_download_reaches_the_real_attachment_endpoint(self):
        """download_signal_attachment() builds /v1/attachments/<id> and calls
        raise_for_status(); an unknown id must come back as a real 404 from
        signal-cli, not a connection error or a 405 from a wrong route."""
        import httpx

        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            asyncio.run(self.upload.download_signal_attachment("no-such-attachment"))
        self.assertEqual(ctx.exception.response.status_code, 404)

    @unittest.skipIf(
        REGISTERED_TEST_NUMBER is None,
        "end-to-end Signal delivery needs an account registered to a real phone "
        "number (SMS/captcha verification cannot be automated); set "
        "SIGNAL_TEST_NUMBER and mount a linked ./signal-data volume to run it",
    )
    def test_send_and_receive_round_trip(self):
        recipient = os.environ.get("SIGNAL_TEST_RECIPIENT", REGISTERED_TEST_NUMBER)
        marker = f"omv-agent-station round trip {os.getpid()}"

        async def scenario():
            received = []

            async def listen():
                import json
                import websockets
                ws_url = f"ws://127.0.0.1:{self.port}/v1/receive/{REGISTERED_TEST_NUMBER}"
                async with websockets.connect(ws_url) as ws:
                    while True:
                        envelope = json.loads(await ws.recv()).get("envelope", {})
                        message = (envelope.get("dataMessage") or {}).get("message")
                        if message:
                            received.append(message)
                            if marker in message:
                                return

            listener = asyncio.create_task(listen())
            await asyncio.sleep(2)
            await self.messaging.send_signal_message(recipient, marker)
            await asyncio.wait_for(listener, timeout=120)
            return received

        received = asyncio.run(scenario())
        self.assertTrue(any(marker in m for m in received), f"marker never came back: {received}")


if __name__ == "__main__":
    unittest.main()
