"""
Tests for the container status classification in get_container_info()
(issue #18: getStatus() must distinguish a stack that's still provisioning
from one that crashed on startup).

get_container_info() is defined inline inside a Python heredoc embedded in
the omv-agent-station bash script (`omv-agent-station performance`), not a
standalone importable module, and there's no PHP test harness yet (issue
#21) to exercise agentstation.inc's getStatus() directly. To test the real
shipped logic without either of those, this extracts the function's exact
source text from the script and exec()s it with a fake `subprocess` --
so a change to the real implementation is what these tests exercise, not
a hand-copied duplicate that could quietly drift out of sync.
"""

import re
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
CLI_BIN = ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station"


class FakeCompletedProcess:
    def __init__(self, stdout):
        self.stdout = stdout


class FakeSubprocess:
    """Stands in for the `subprocess` module inside the extracted function.
    Maps a container name (parsed out of the --filter name=X arg) to either
    a canned `docker ps` stdout string or an Exception to raise."""

    responses = {}
    PIPE = None
    STDOUT = None

    @staticmethod
    def run(args, **kwargs):
        filter_arg = next(a for a in args if a.startswith("name="))
        name = filter_arg.split("=", 1)[1]
        result = FakeSubprocess.responses.get(name, "")
        if isinstance(result, Exception):
            raise result
        return FakeCompletedProcess(stdout=result)


def _load_get_container_info():
    text = CLI_BIN.read_text(encoding="utf-8")
    match = re.search(
        r'(def get_container_info\(filter_names\):.*?'
        r'return \{"running": False, "status": "Not created", "state": "not_created"\}\n)',
        text, re.DOTALL,
    )
    assert match, "get_container_info() source not found in omv-agent-station -- did its shape change?"
    namespace = {"subprocess": FakeSubprocess, "re": re}
    exec(match.group(1), namespace)  # noqa: S102 -- exec'ing the real shipped source under test, not arbitrary input
    return namespace["get_container_info"]


class TestContainerStateClassification(unittest.TestCase):
    def setUp(self):
        self.get_container_info = _load_get_container_info()
        FakeSubprocess.responses = {}

    def test_running_container(self):
        FakeSubprocess.responses = {"litellm-proxy": "Up 5 minutes"}
        info = self.get_container_info(["litellm-proxy", "litellm"])
        self.assertTrue(info["running"])
        self.assertEqual(info["state"], "running")

    def test_crashed_container_nonzero_exit_is_distinguishable_from_provisioning(self):
        FakeSubprocess.responses = {"syncthing": "Exited (137) 2 minutes ago"}
        info = self.get_container_info(["syncthing"])
        self.assertFalse(info["running"])
        self.assertEqual(info["state"], "exited_error")

    def test_cleanly_stopped_container_is_not_flagged_as_crashed(self):
        FakeSubprocess.responses = {"telegram-agent-bot": "Exited (0) 10 minutes ago"}
        info = self.get_container_info(["telegram-agent-bot", "telegram-bot"])
        self.assertFalse(info["running"])
        self.assertEqual(info["state"], "exited_clean")

    def test_container_being_created_is_starting_not_crashed(self):
        FakeSubprocess.responses = {"discord-agent-bot": "Created"}
        info = self.get_container_info(["discord-agent-bot", "discord-bot"])
        self.assertFalse(info["running"])
        self.assertEqual(info["state"], "starting")

    def test_no_container_at_all_is_not_created(self):
        info = self.get_container_info(["signal-agent-bot", "signal-bot"])
        self.assertFalse(info["running"])
        self.assertEqual(info["state"], "not_created")


class TestGetStatusAndDashboardWireUpCrashedState(unittest.TestCase):
    """Structural coverage for the PHP/YAML side, since there's no PHP test
    harness yet (issue #21) to actually execute agentstation.inc."""

    def test_getstatus_distinguishes_crashed_from_provisioning(self):
        rpc_file = (
            ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault"
            / "engined" / "rpc" / "agentstation.inc"
        ).read_text(encoding="utf-8")
        self.assertIn("exited_error", rpc_file)
        self.assertIn('"crashed"', rpc_file)
        self.assertIn("Crashed", rpc_file)
        self.assertIn("Provisioning", rpc_file)

    def test_dashboard_widget_shows_distinct_color_for_crashed(self):
        dashboard_file = (
            ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault"
            / "workbench" / "dashboard.d" / "agentstation.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("crashed", dashboard_file)
        self.assertIn("omv-color-red", dashboard_file)


if __name__ == "__main__":
    unittest.main()
