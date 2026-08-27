"""
Regression test for the OMV AgentStation RPC service registration.

installClaudeCli() was defined and wired up in the AI Models form page
(component.d/omv-services-agentstation-aimodels-form-page.yaml calls it via
method: installClaudeCli), but initialize() never called
registerMethod("installClaudeCli") -- OMV's RPC dispatcher only serves
registered methods, so the "Install Claude CLI" button was a live, broken
UI feature. This test checks every `public function` in the RPC class has a
matching registerMethod() call, so a future method can't ship unregistered
the same way.
"""

import re
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
RPC_FILE = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "engined" / "rpc" / "agentstation.inc"


class TestOmvRpcRegistration(unittest.TestCase):
    def test_every_public_rpc_method_is_registered(self):
        content = RPC_FILE.read_text(encoding="utf-8")

        initialize_match = re.search(r"function initialize\(\):\s*void\s*\{(.*?)\n\s*\}", content, re.DOTALL)
        self.assertIsNotNone(initialize_match, "Could not locate initialize() body in agentstation.inc")
        registered = set(re.findall(r'registerMethod\("([^"]+)"\)', initialize_match.group(1)))

        defined = set(re.findall(r"public function (\w+)\(", content))
        defined -= {"getName", "initialize"}

        missing = defined - registered
        self.assertEqual(
            missing, set(),
            f"RPC method(s) {sorted(missing)} are defined but never registered in initialize() "
            "-- they will be unreachable from any UI form or dashboard widget that calls them."
        )


if __name__ == "__main__":
    unittest.main()
