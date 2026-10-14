"""
Coverage for the OMV AgentStation RPC service's method registration.

installClaudeCli() was defined and wired up in the AI Models form page
(component.d/omv-services-agentstation-aimodels-form-page.yaml calls it via
method: installClaudeCli), but initialize() never called
registerMethod("installClaudeCli") -- OMV's RPC dispatcher only serves
registered methods, so the "Install Claude CLI" button was a live, broken
UI feature.

Two complementary tests (GitHub issue #61):

TestOmvRpcRegistrationStaticAssertions greps the PHP source as text. It runs
anywhere, including where no PHP interpreter exists, but it only proves the
characters `registerMethod("x")` appear somewhere in initialize()'s body --
it cannot tell whether the file even parses.

TestOmvRpcRegistrationExecuted runs the real agentstation.inc through a real
PHP interpreter against tests/php/stubs/OmvStubs.php and asks the constructed
service which methods it registered. That proves the class loads, initialize()
executes, and each registerMethod() call resolves to a real method -- the
stub's registerMethod() throws when it does not, exactly as OMV's own
ServiceAbstract does. Skipped (not silently passed) where php is absent.
"""

import json
import os
import re
import shutil
import subprocess  # nosec B404
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
RPC_FILE = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "engined" / "rpc" / "agentstation.inc"
PHP_BOOTSTRAP = Path(__file__).parent / "php" / "bootstrap.php"
PHP_BIN = shutil.which("php")

NON_RPC_METHODS = {"getName", "initialize"}


def _publicly_defined_methods() -> set[str]:
    content = RPC_FILE.read_text(encoding="utf-8")
    return set(re.findall(r"public function (\w+)\(", content)) - NON_RPC_METHODS


class TestOmvRpcRegistrationStaticAssertions(unittest.TestCase):
    """Text-level assertions over agentstation.inc. No PHP is executed."""

    def test_every_public_rpc_method_is_registered(self):
        content = RPC_FILE.read_text(encoding="utf-8")

        initialize_match = re.search(r"function initialize\(\):\s*void\s*\{(.*?)\n\s*\}", content, re.DOTALL)
        self.assertIsNotNone(initialize_match, "Could not locate initialize() body in agentstation.inc")
        registered = set(re.findall(r'registerMethod\("([^"]+)"\)', initialize_match.group(1)))

        missing = _publicly_defined_methods() - registered
        self.assertEqual(
            missing, set(),
            f"RPC method(s) {sorted(missing)} are defined but never registered in initialize() "
            "-- they will be unreachable from any UI form or dashboard widget that calls them."
        )


@unittest.skipIf(PHP_BIN is None, "php interpreter not available")
class TestOmvRpcRegistrationExecuted(unittest.TestCase):
    """Runs agentstation.inc for real under PHP and inspects the live service."""

    def _run_php(self, body: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmpdir:
            driver = Path(tmpdir) / "driver.php"
            driver.write_text(
                "<?php\nrequire_once " + json.dumps(str(PHP_BOOTSTRAP)) + ";\n" + textwrap.dedent(body),
                encoding="utf-8",
            )
            env = {**os.environ, "AGENTSTATION_TEST_CONFIG_PATH": str(Path(tmpdir) / "config.json")}
            return subprocess.run(  # nosec B603
                [PHP_BIN, "-d", "error_reporting=E_ALL", str(driver)],
                capture_output=True, text=True, env=env,
            )

    def test_php_parses_and_initialize_registers_every_public_method(self):
        res = self._run_php(
            """
            $service = new \\OMV\\Engined\\Rpc\\AgentStation();
            $service->initialize();
            echo json_encode($service->getRegisteredMethodNames());
            """
        )
        self.assertEqual(res.returncode, 0, f"PHP failed to run agentstation.inc:\n{res.stderr}")

        registered = set(json.loads(res.stdout))
        self.assertEqual(
            _publicly_defined_methods() - registered, set(),
            "initialize() ran under a real PHP interpreter but did not register every public method: "
            f"registered={sorted(registered)}",
        )

    def test_registered_methods_are_dispatchable_after_a_real_initialize(self):
        """registerMethod() only records a name; hasMethod() is what OMV's RPC
        dispatcher consults before serving a call. Both must agree, or the UI
        gets a 500 on a button that looks wired up."""
        res = self._run_php(
            """
            $service = new \\OMV\\Engined\\Rpc\\AgentStation();
            $service->initialize();
            $unreachable = [];
            foreach ($service->getRegisteredMethodNames() as $name) {
                if (!$service->hasMethod($name)) {
                    $unreachable[] = $name;
                }
            }
            echo json_encode($unreachable);
            """
        )
        self.assertEqual(res.returncode, 0, f"PHP failed to run agentstation.inc:\n{res.stderr}")
        self.assertEqual(json.loads(res.stdout), [], "registered RPC names that the dispatcher cannot resolve")

    def test_unregistered_method_is_rejected_by_the_dispatcher(self):
        """Guards the guard: proves this harness would actually catch the
        installClaudeCli-shaped bug rather than reporting success regardless.
        Calling a real, defined method that was never registered must fail."""
        res = self._run_php(
            """
            $service = new \\OMV\\Engined\\Rpc\\AgentStation();
            // deliberately NOT calling initialize()
            try {
                $service->callMethod("getSettings", [], ["username" => "admin", "role" => OMV_ROLE_ADMINISTRATOR]);
                echo "DISPATCHED";
            } catch (\\OMV\\Rpc\\Exception $e) {
                echo "REJECTED";
            }
            """
        )
        self.assertEqual(res.returncode, 0, f"PHP failed to run agentstation.inc:\n{res.stderr}")
        self.assertEqual(res.stdout.strip(), "REJECTED")


class TestRestartServicesAndGetLogsAreWired(unittest.TestCase):
    """Regression coverage for issue #73: restartServices and getLogs were
    registered and implemented in agentstation.inc but no component.d yaml
    ever referenced them, making both permanently unreachable from the
    WebGUI. Both are now wired into the Diagnostics page."""

    def test_restart_services_and_get_logs_referenced_in_workbench(self):
        component_dir = (
            ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault"
            / "workbench" / "component.d"
        )
        combined = "\n".join(p.read_text(encoding="utf-8") for p in component_dir.glob("*.yaml"))
        self.assertIn("restartServices", combined, "restartServices is registered but never called from any component.d yaml")
        self.assertIn("getLogs", combined, "getLogs is registered but never called from any component.d yaml")


if __name__ == "__main__":
    unittest.main()
