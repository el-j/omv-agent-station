"""
LiteLLM routing coverage, split into what each test actually proves.

TestLiteLLMConfigStaticAssertions parses litellm/config.yaml as text/YAML and
cross-checks it against the /modelhelp doc strings. It catches a fallback
target being renamed or deleted, but never runs LiteLLM -- it moved here from
tests/test_blackbox.py, where it was neither black-box nor about routing
behavior (GitHub issue #60).

TestLiteLLMFailoverExecuted starts a real `litellm` proxy against two fake
upstream providers served from this process (GitHub issue #64). The first
provider answers 429 and the second answers 200, so a request that comes back
with the second provider's content is proof the router really failed over --
not that a YAML key exists. No paid API is contacted: both "providers" are
local HTTP handlers on 127.0.0.1.
"""

import json
import os
import shutil
import socket
import subprocess  # nosec B404
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

LITELLM_BIN = shutil.which("litellm")
PROXY_STARTUP_TIMEOUT = float(os.environ.get("LITELLM_TEST_STARTUP_TIMEOUT", "120"))
MASTER_KEY = "sk-test-master-key"
FALLBACK_CONTENT = "answer from the fallback provider"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeProviderHandler(BaseHTTPRequestHandler):
    """Two OpenAI-compatible upstreams on one port.

    /rate-limited/... always answers 429 (the provider that is out of quota);
    /healthy/... always answers a normal completion. Every hit is recorded on
    the server so a test can assert on the order providers were tried in.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _respond(self, status: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)

        if self.path.startswith("/rate-limited"):
            self.server.record("rate-limited")
            self._respond(429, {"error": {"message": "rate limit exceeded", "type": "rate_limit_error"}})
            return

        if self.path.startswith("/healthy"):
            self.server.record("healthy")
            self._respond(200, {
                "id": "chatcmpl-fake",
                "object": "chat.completion",
                "created": 0,
                "model": "fake-healthy",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": FALLBACK_CONTENT},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })
            return

        self._respond(404, {"error": {"message": f"no fake provider at {self.path}"}})


class FakeProviderServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, FakeProviderHandler)
        self.hits = []
        self._lock = threading.Lock()

    def record(self, name: str):
        with self._lock:
            self.hits.append(name)


class TestLiteLLMConfigStaticAssertions(unittest.TestCase):
    """Static consistency checks over litellm/config.yaml. No LiteLLM process runs."""

    def test_router_fallback_continuity(self):
        import yaml
        config_path = ROOT_DIR / "litellm" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        all_models = {m["model_name"] for m in data["model_list"]}
        fallbacks = data.get("router_settings", {}).get("fallbacks", [])

        for fb in fallbacks:
            for primary, secondary_list in fb.items():
                self.assertIn(primary, all_models, f"Fallback primary model '{primary}' not registered in model_list!")
                for sec in secondary_list:
                    self.assertIn(sec, all_models, f"Fallback target '{sec}' for '{primary}' not in model_list!")

    def test_modelhelp_text_matches_config_fallbacks(self):
        """Regression coverage for issue #13: /modelhelp's described fallback
        chains must match litellm/config.yaml's real router_settings.fallbacks,
        in both the agent_station_core copy (Discord/Signal) and Telegram's
        independent copy in handlers/ai_chat.py."""
        import yaml
        config_path = ROOT_DIR / "litellm" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        fallbacks = {}
        for fb in data["router_settings"]["fallbacks"]:
            fallbacks.update(fb)

        # Human-readable labels used in the doc text for each model_name that
        # appears in a fallback chain /modelhelp documents.
        label = {
            "gemini-3.7-pro": "Gemini 3.7 Pro",
            "gemini-3.7-flash": "Gemini 3.7 Flash",
            "gemini-2.5-flash": "Gemini 2.5 Flash",
            "github-gpt-4o": "GPT-4o",
            "github-deepseek-r1": "DeepSeek-R1",
            "github-o3-mini": "o3-mini",
        }

        sys.path.insert(0, str(ROOT_DIR))
        try:
            import agent_station_core.ai_service as ai_service
            shared_text = ai_service.get_modelhelp_markdown()
        finally:
            if str(ROOT_DIR) in sys.path:
                sys.path.remove(str(ROOT_DIR))

        telegram_text = (ROOT_DIR / "telegram-agent-bot" / "handlers" / "ai_chat.py").read_text(encoding="utf-8")

        for router in ("coder-smart", "reasoning-heavy"):
            chain = fallbacks[router]
            expected = " ➔ ".join(label[m] for m in chain)
            self.assertIn(expected, shared_text, f"agent_station_core modelhelp text out of sync with {router}'s real fallback chain")
            self.assertIn(expected, telegram_text, f"Telegram modelhelp text out of sync with {router}'s real fallback chain")


@unittest.skipIf(LITELLM_BIN is None, "litellm CLI not installed (pip install 'litellm[proxy]')")
class TestLiteLLMFailoverExecuted(unittest.TestCase):
    """Starts a real litellm proxy and observes a real provider switch."""

    def setUp(self):
        self.provider = FakeProviderServer(("127.0.0.1", 0))
        self.provider_port = self.provider.server_address[1]
        self._provider_thread = threading.Thread(target=self.provider.serve_forever, daemon=True)
        self._provider_thread.start()

        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.proxy_port = _free_port()
        self.proxy = None

    def tearDown(self):
        if self.proxy is not None and self.proxy.poll() is None:
            self.proxy.terminate()
            try:
                self.proxy.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proxy.kill()
                self.proxy.wait(timeout=20)
        self.provider.shutdown()
        self.provider.server_close()
        self._tmpdir.cleanup()

    def _write_config(self) -> Path:
        base = f"http://127.0.0.1:{self.provider_port}"
        config = {
            "model_list": [
                {
                    "model_name": "primary-model",
                    "litellm_params": {
                        "model": "openai/fake-primary",
                        "api_base": f"{base}/rate-limited",
                        "api_key": "fake-key",
                    },
                },
                {
                    "model_name": "backup-model",
                    "litellm_params": {
                        "model": "openai/fake-backup",
                        "api_base": f"{base}/healthy",
                        "api_key": "fake-key",
                    },
                },
            ],
            # Mirrors litellm/config.yaml's router_settings shape; num_retries is
            # 0 so the switch to the backup deployment is unambiguous rather than
            # hidden behind retries of the rate-limited one.
            "router_settings": {
                "routing_strategy": "usage-based-routing",
                "num_retries": 0,
                "allowed_fails": 0,
                "cooldown_time": 30,
                "fallbacks": [{"primary-model": ["backup-model"]}],
            },
            "general_settings": {"master_key": MASTER_KEY, "store_model_in_db": False},
        }
        import yaml
        path = self.tmp / "config.yaml"
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
        return path

    def _start_proxy(self, config_path: Path):
        # cwd is the temp dir, not the repo: the repo root holds a `litellm/`
        # directory that would otherwise shadow the installed package on
        # sys.path and make the proxy unimportable.
        self.proxy = subprocess.Popen(  # nosec B603
            [LITELLM_BIN, "--config", str(config_path), "--host", "127.0.0.1", "--port", str(self.proxy_port)],
            cwd=str(self.tmp),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "LITELLM_MASTER_KEY": MASTER_KEY, "LITELLM_MODE": "PRODUCTION"},
        )
        deadline = time.monotonic() + PROXY_STARTUP_TIMEOUT
        url = f"http://127.0.0.1:{self.proxy_port}/health/readiness"
        while time.monotonic() < deadline:
            if self.proxy.poll() is not None:
                self.fail(f"litellm proxy exited early:\n{self.proxy.stdout.read()[-4000:]}")
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:  # nosec B310
                    if resp.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        self.fail(f"litellm proxy never became ready on port {self.proxy_port}")

    def _chat(self, model: str, timeout=60):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.proxy_port}/v1/chat/completions",
            data=json.dumps({"model": model, "messages": [{"role": "user", "content": "ping"}]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {MASTER_KEY}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            return resp.status, json.loads(resp.read())

    def test_rate_limited_provider_fails_over_to_the_backup(self):
        self._start_proxy(self._write_config())

        status, body = self._chat("primary-model")

        self.assertEqual(status, 200, f"proxy did not serve the request: {body}")
        self.assertEqual(
            body["choices"][0]["message"]["content"], FALLBACK_CONTENT,
            "the answer did not come from the backup provider -- no failover happened",
        )
        self.assertIn("rate-limited", self.provider.hits, "the rate-limited provider was never tried first")
        self.assertIn("healthy", self.provider.hits, "the backup provider was never reached")
        self.assertLess(
            self.provider.hits.index("rate-limited"), self.provider.hits.index("healthy"),
            f"providers were tried in the wrong order: {self.provider.hits}",
        )


if __name__ == "__main__":
    unittest.main()
