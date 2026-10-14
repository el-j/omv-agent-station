"""
Helpers for the tests that need a real Docker daemon (GitHub issue #64).

Docker is not available in every environment the suite runs in, so tests
built on this skip -- loudly, with the reason -- rather than failing or
quietly asserting nothing. `docker_unavailable_reason()` is what test modules
should feed to unittest.skipIf so the skip message names the actual problem.
"""

import json
import shutil
import socket
import subprocess  # nosec B404
import time
import uuid

DOCKER_BIN = shutil.which("docker")


def docker_unavailable_reason() -> str | None:
    """None when a usable Docker daemon is reachable, else why it is not."""
    if DOCKER_BIN is None:
        return "docker CLI not installed"
    try:
        res = subprocess.run(  # nosec B603
            [DOCKER_BIN, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"docker info failed: {e}"
    if res.returncode != 0:
        return f"docker daemon not reachable: {res.stderr.strip()[:200]}"
    return None


def image_exists(image: str) -> bool:
    res = subprocess.run(  # nosec B603
        [DOCKER_BIN, "image", "inspect", image],
        capture_output=True, text=True,
    )
    return res.returncode == 0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Container:
    """A `docker run -d` container scoped to one test, always torn down."""

    def __init__(self, image: str, *, command=None, env=None, ports=None, extra_args=None):
        self.image = image
        self.command = list(command or [])
        self.env = dict(env or {})
        self.ports = dict(ports or {})  # host_port -> container_port
        self.extra_args = list(extra_args or [])
        self.name = f"omv-agent-station-test-{uuid.uuid4().hex[:12]}"
        self.id = None

    def start(self):
        args = [DOCKER_BIN, "run", "-d", "--name", self.name]
        for host_port, container_port in self.ports.items():
            args += ["-p", f"127.0.0.1:{host_port}:{container_port}"]
        for key, value in self.env.items():
            args += ["-e", f"{key}={value}"]
        args += self.extra_args + [self.image] + self.command

        res = subprocess.run(args, capture_output=True, text=True)  # nosec B603
        if res.returncode != 0:
            raise RuntimeError(f"docker run failed: {res.stderr.strip()}")
        self.id = res.stdout.strip()
        return self

    def logs(self) -> str:
        if self.id is None:
            return ""
        res = subprocess.run(  # nosec B603
            [DOCKER_BIN, "logs", self.name], capture_output=True, text=True,
        )
        return res.stdout + res.stderr

    def is_running(self) -> bool:
        res = subprocess.run(  # nosec B603
            [DOCKER_BIN, "inspect", "--format", "{{json .State}}", self.name],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            return False
        return json.loads(res.stdout).get("Running", False)

    def wait_for_port(self, host_port: int, timeout=90.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_running():
                raise RuntimeError(f"container {self.image} exited early:\n{self.logs()[-4000:]}")
            try:
                with socket.create_connection(("127.0.0.1", host_port), timeout=1):
                    return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError(
            f"container {self.image} never opened port {host_port}:\n{self.logs()[-4000:]}"
        )

    def wait_for_http(self, url: str, timeout=90.0, accept=(200, 401, 403)):
        """An open TCP port is not the same as a server ready to answer: a
        container can accept a connection and then reset it while still
        starting up. Poll until an HTTP status actually comes back."""
        import urllib.error
        import urllib.request

        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:  # nosec B310
                    if resp.status in accept:
                        return resp.status
                    last = resp.status
            except urllib.error.HTTPError as e:
                if e.code in accept:
                    return e.code
                last = e.code
            except (urllib.error.URLError, OSError) as e:
                last = e
            time.sleep(0.5)
        raise RuntimeError(f"{url} never answered with {accept} (last: {last!r})\n{self.logs()[-4000:]}")

    def stop(self):
        if self.id is None:
            return
        subprocess.run(  # nosec B603
            [DOCKER_BIN, "rm", "-f", self.name], capture_output=True, text=True,
        )
        self.id = None
