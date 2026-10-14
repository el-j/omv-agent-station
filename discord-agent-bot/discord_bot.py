#!/usr/bin/env python3
"""
Discord Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8.
Provides remote command execution, autonomous coding agent dispatch (Aider/Claude Code),
Git repository synchronization, Obsidian second-brain integration, and LiteLLM gateway telemetry over Discord.
Powered by agent_station_core.
"""

import os
import sys
from pathlib import Path

# Auto-resolve agent_station_core in sys.path
_bot_dir = Path(__file__).parent.resolve()
_root_dir = _bot_dir.parent.resolve()
for path_cand in [str(_bot_dir), str(_root_dir)]:
    if path_cand not in sys.path:
        sys.path.insert(0, path_cand)

import discord
from discord.ext import commands

from agent_station_core import logger, init_git_credentials, expand_custom_command

from core.security import is_authorized  # noqa: F401 -- re-exported for tests/tooling
from handlers.system import start_cmd, help_cmd, status_cmd, exec_cmd, task_cmd, claude_cmd, cancel_cmd
from handlers.ai_chat import chat_cmd, gemini_cmd, gpt4_cmd, models_cmd, modelhelp_cmd
from handlers.git_ops import projects_cmd, newrepo_cmd, clone_cmd, pull_cmd, push_cmd, branch_cmd, diff_cmd
from handlers.custom_cmds import addcmd_cmd, delcmd_cmd, customcmds_cmd
from handlers.vault import note_cmd, vault_cmd
from handlers.topics import bind_cmd, unbind_cmd
from handlers.upload import handle_discord_upload, MAX_UPLOAD_BYTES  # noqa: F401 -- re-exported for tests

DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents, help_command=None)

# ---------------------------------------------------------------------------
# Command Registration (All 25 Shared Capabilities)
# ---------------------------------------------------------------------------
_COMMANDS = [
    ("start", start_cmd, []),
    ("help", help_cmd, []),
    ("chat", chat_cmd, []),
    ("gemini", gemini_cmd, []),
    ("gpt4", gpt4_cmd, []),
    ("models", models_cmd, []),
    ("modelhelp", modelhelp_cmd, []),
    ("projects", projects_cmd, []),
    ("clone", clone_cmd, []),
    ("newrepo", newrepo_cmd, []),
    ("pull", pull_cmd, []),
    ("push", push_cmd, []),
    ("branch", branch_cmd, []),
    ("diff", diff_cmd, []),
    ("task", task_cmd, []),
    ("claude", claude_cmd, []),
    ("exec", exec_cmd, []),
    ("cancel", cancel_cmd, ["stop"]),
    ("status", status_cmd, []),
    ("note", note_cmd, []),
    ("vault", vault_cmd, []),
    ("addcmd", addcmd_cmd, []),
    ("delcmd", delcmd_cmd, []),
    ("cmds", customcmds_cmd, []),
    ("bind", bind_cmd, []),
    ("unbind", unbind_cmd, []),
]
for _name, _func, _aliases in _COMMANDS:
    bot.add_command(commands.Command(_func, name=_name, aliases=_aliases))


@bot.event
async def on_ready():
    """Runs once the Discord gateway connection is established."""
    init_git_credentials()
    logger.info(f"Discord Agent Bot logged in as {bot.user.name} (ID: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message):
    """Routes attachments to the upload handler and slash text through custom
    shortcut expansion before falling back to normal command processing."""
    if message.author.bot:
        return
    if message.attachments:
        await handle_discord_upload(message)
        return
    if message.content.startswith("/"):
        parts = message.content.lstrip("/").split(maxsplit=1)
        cmd_name = parts[0].lower()
        passed_args = parts[1] if len(parts) > 1 else ""
        expanded = expand_custom_command(cmd_name, passed_args)
        if expanded and not bot.get_command(cmd_name):
            ctx = await bot.get_context(message)
            exp_parts = expanded.split()
            target_cmd = bot.get_command(exp_parts[0].lstrip("/"))
            if target_cmd:
                await target_cmd(ctx, *exp_parts[1:])
                return
    await bot.process_commands(message)


def main():
    """Starts the Discord bot, or idles in standby if no token is configured."""
    if not DISCORD_TOKEN:
        print("ℹ️ DISCORD_BOT_TOKEN environment variable not set. Bot in standby mode.", file=sys.stderr)
        import time
        while True:
            time.sleep(3600)
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
