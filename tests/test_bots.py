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
        base_dir = ROOT_DIR / "openmediavault-agent-station"
        rpc_file = base_dir / "usr" / "share" / "openmediavault" / "engined" / "rpc" / "agentstation.inc"
        cli_helper = base_dir / "usr" / "sbin" / "omv-agent-station"
        dash_file = base_dir / "usr" / "share" / "openmediavault" / "workbench" / "dashboard.d" / "agentstation.yaml"

        self.assertTrue(rpc_file.exists())
        self.assertTrue(cli_helper.exists())
        self.assertTrue(dash_file.exists())

        # Check navigation files (root-level 'Agent Station' menu, not buried
        # under Services -- see issue #4)
        nav_dir = base_dir / "usr" / "share" / "openmediavault" / "workbench" / "navigation.d"
        for nav_name in [
            "agentstation",
            "agentstation.overview",
            "agentstation.aimodels",
            "agentstation.git",
            "agentstation.chat",
            "agentstation.security",
            "agentstation.diagnostics"
        ]:
            self.assertTrue((nav_dir / f"{nav_name}.yaml").exists(), f"Missing nav file: {nav_name}.yaml")

        # The root nav item is a container only (no url), so it has no route
        route_dir = base_dir / "usr" / "share" / "openmediavault" / "workbench" / "route.d"
        for route_name in [
            "agentstation.overview",
            "agentstation.aimodels",
            "agentstation.git",
            "agentstation.chat",
            "agentstation.security",
            "agentstation.diagnostics"
        ]:
            self.assertTrue((route_dir / f"{route_name}.yaml").exists(), f"Missing route file: {route_name}.yaml")

        # Check component files
        comp_dir = base_dir / "usr" / "share" / "openmediavault" / "workbench" / "component.d"
        for comp_name in [
            "omv-services-agentstation-overview-page",
            "omv-services-agentstation-aimodels-form-page",
            "omv-services-agentstation-git-form-page",
            "omv-services-agentstation-chat-form-page",
            "omv-services-agentstation-security-form-page",
            "omv-services-agentstation-diagnostics-page"
        ]:
            self.assertTrue((comp_dir / f"{comp_name}.yaml").exists(), f"Missing component file: {comp_name}.yaml")

    def test_agentstation_is_a_root_level_menu_not_buried_under_services(self):
        """Regression coverage for issue #4: 'Agent Station' must be a root
        sidebar item alongside System/Storage/Services, not nested under the
        Services submenu."""
        nav_dir = ROOT_DIR / "openmediavault-agent-station" / "usr" / "share" / "openmediavault" / "workbench" / "navigation.d"

        # No leftover navigation entries nested under Services.
        self.assertEqual(list(nav_dir.glob("services.agentstation*.yaml")), [])

        root_text = (nav_dir / "agentstation.yaml").read_text(encoding="utf-8")
        self.assertIn('path: "agentstation"', root_text)
        self.assertNotIn("url:", root_text, "Root nav item must be a container only (no url)")

        for sub in ["overview", "aimodels", "git", "chat", "security", "diagnostics"]:
            sub_text = (nav_dir / f"agentstation.{sub}.yaml").read_text(encoding="utf-8")
            self.assertIn(f'path: "agentstation.{sub}"', sub_text)
            self.assertIn(f'url: "/agentstation/{sub}"', sub_text)

if __name__ == "__main__":
    unittest.main()
