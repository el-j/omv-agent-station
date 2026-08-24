"""
User-Defined Custom Command Persistence and Expansion Service.
Loads and saves shortcuts across workspaces and mirrors configurations to Obsidian.
"""

import json
from .config import CUSTOM_CMDS_FILE, OBSIDIAN_CMDS_FILE, logger

def load_custom_commands() -> dict[str, str]:
    """Loads user-defined custom commands from disk."""
    if CUSTOM_CMDS_FILE.exists():
        try:
            with open(CUSTOM_CMDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load custom commands: {e}")
    if OBSIDIAN_CMDS_FILE.exists():
        try:
            with open(OBSIDIAN_CMDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_custom_commands(cmds: dict[str, str]):
    """Persists custom commands to disk and mirrors to Obsidian vault."""
    try:
        CUSTOM_CMDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CUSTOM_CMDS_FILE, "w", encoding="utf-8") as f:
            json.dump(cmds, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save custom commands: {e}")

    try:
        OBSIDIAN_CMDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OBSIDIAN_CMDS_FILE, "w", encoding="utf-8") as f:
            json.dump(cmds, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not mirror custom commands to Obsidian: {e}")

def expand_custom_command(cmd_name: str, passed_args: str = "") -> str | None:
    """Expands a custom command template with optional {args} substitution."""
    cmds = load_custom_commands()
    if cmd_name not in cmds:
        return None
    template = cmds[cmd_name]
    if "{args}" in template:
        return template.replace("{args}", passed_args).strip()
    elif passed_args:
        return f"{template} {passed_args}".strip()
    return template.strip()
