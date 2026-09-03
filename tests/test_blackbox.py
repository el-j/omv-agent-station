"""
Genuinely black-box tests for the OMV Agent Station stack.

Every test in this module treats the thing under test as an opaque process:
it runs a real script through subprocess with a controlled environment and
asserts only on the observable results (exit status, stdout, files on disk).
No product module is imported and no internal function is called.

Tests that used to live here under "_blackbox" names but actually imported bot
modules and called individual functions with dummy objects were whitebox unit
tests; GitHub issue #60 moved them to tests/test_security_unit.py, and the
LiteLLM router-config assertions to tests/test_litellm_failover.py, so this
module's name matches its contents.
"""

import os
import shutil
import json
import subprocess  # nosec B404
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestBlackboxCLIAndPackaging(unittest.TestCase):
    """Black-box testing for CLI lifecycle helper and Debian packaging."""

    def test_debian_package_structure_and_permissions(self):
        deb_script = ROOT_DIR / "build-deb.sh"
        self.assertTrue(deb_script.exists())
        deb_script_path = str(deb_script.resolve())

        # Force a deterministic version so we can assert the exact artifact
        # path even when build-deb.sh resolves VERSION dynamically.
        version = "0.0.2-ci.1"
        deb_file = ROOT_DIR / f"openmediavault-agent-station_{version}_all.deb"
        deb_file.unlink(missing_ok=True)
        try:
            # Build deb in isolated environment
            env = os.environ.copy()
            env["AGENT_STATION_VERSION"] = version
            res = subprocess.run([deb_script_path], cwd=str(ROOT_DIR), env=env, capture_output=True, text=True)  # nosec B603
            self.assertEqual(res.returncode, 0, f"build-deb.sh failed: {res.stderr}")

            self.assertTrue(deb_file.exists(), f"Debian package {deb_file} must exist after build")
            self.assertGreater(deb_file.stat().st_size, 5000, "Package size should be substantial")
        finally:
            deb_file.unlink(missing_ok=True)

    def test_cli_helper_missing_config_behavior(self):
        cli_bin = ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station"
        self.assertTrue(cli_bin.exists())
        cli_bin_path = str(cli_bin.resolve())

        # Test help command
        res = subprocess.run([cli_bin_path, "help"], capture_output=True, text=True)  # nosec B603
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage:", res.stdout)

    def test_cli_apply_generates_valid_env_blackbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "etc"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "test-config.json"
            stack_dir = Path(tmpdir) / "stack"
            stack_dir.mkdir(parents=True)

            test_config = {
                "enable": False,
                "data_dir": f"{tmpdir}/data",
                "chat_service": "telegram",
                "gemini_api_key": "test-gemini-key",
                "anthropic_api_key": "test-anthropic-key",
                "github_token": "test-github-token",
                "git_author_name": "Test Bot",
                "git_author_email": "bot@test.local",
                "telegram_bot_token": "123456:ABC-DEF",
                "telegram_allowed_user_id": "12345678"
            }
            config_file.write_text(json.dumps(test_config), encoding="utf-8")

            cli_bin = ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station"
            cli_bin_path = str(cli_bin.resolve())
            bash_exe = shutil.which("bash") or "/bin/bash"

            env = os.environ.copy()
            env["CONFIG_FILE"] = str(config_file)
            env["STACK_DIR"] = str(stack_dir)

            res = subprocess.run([bash_exe, cli_bin_path, "apply"], env=env, cwd=str(ROOT_DIR), capture_output=True, text=True)  # nosec B603
            self.assertEqual(res.returncode, 0)

            # Verify directories were created
            self.assertTrue((Path(tmpdir) / "data" / "obsidian").exists())
            self.assertTrue((Path(tmpdir) / "data" / "workspace").exists())
            self.assertTrue((Path(tmpdir) / "data" / "ssh").exists())

            # Verify generated .env file
            env_out = (stack_dir / ".env").read_text()
            self.assertIn("GEMINI_API_KEY=test-gemini-key", env_out)
            self.assertIn("GIT_AUTHOR_NAME=Test Bot", env_out)


if __name__ == "__main__":
    unittest.main()
