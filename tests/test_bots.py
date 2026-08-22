"""
Unit tests for bot files, syntax, and build scripts.
"""

import os
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

class TestBotsAndPackaging(unittest.TestCase):
    def test_telegram_bot_syntax(self):
        bot_file = ROOT_DIR / "telegram-agent-bot" / "bot.py"
        self.assertTrue(bot_file.exists())
        with open(bot_file, "r", encoding="utf-8") as f:
            code = f.read()
        compile(code, str(bot_file), "exec")

    def test_signal_bot_syntax(self):
        bot_file = ROOT_DIR / "signal-agent-bot" / "signal_bot.py"
        self.assertTrue(bot_file.exists())
        with open(bot_file, "r", encoding="utf-8") as f:
            code = f.read()
        compile(code, str(bot_file), "exec")

    def test_discord_bot_syntax(self):
        bot_file = ROOT_DIR / "discord-agent-bot" / "discord_bot.py"
        self.assertTrue(bot_file.exists())
        with open(bot_file, "r", encoding="utf-8") as f:
            code = f.read()
        compile(code, str(bot_file), "exec")

    def test_deb_build_script_exists(self):
        build_script = ROOT_DIR / "build-deb.sh"
        self.assertTrue(build_script.exists())
        self.assertTrue(os.access(build_script, os.X_OK))

    def test_omv_plugin_files_exist(self):
        rpc_file = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "engined" / "rpc" / "agentstation.inc"
        yaml_page = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "workbench" / "component.d" / "omv-services-agentstation-form-page.yaml"
        cli_helper = ROOT_DIR / "openmediavault-agent-station" / "usr" / "sbin" / "omv-agent-station"
        self.assertTrue(rpc_file.exists())
        self.assertTrue(yaml_page.exists())
        self.assertTrue(cli_helper.exists())

if __name__ == "__main__":
    unittest.main()
