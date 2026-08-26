"""
Telegram Native Command Autocomplete Menu Synchronization.
Registers built-in and user-defined custom commands via Telegram setMyCommands API.
"""

from telegram import BotCommand
from core.config import logger
from handlers.custom_cmds import load_custom_commands

async def sync_bot_commands(target):
    """Registers built-in and user custom commands for Telegram auto-complete menu."""
    bot = target.bot if hasattr(target, "bot") else target
    commands = [
        BotCommand("chat", "💬 Ask AI (smart router or specific model)"),
        BotCommand("gemini", "⚡ Quick ask Google Gemini 3.6 Flash"),
        BotCommand("gpt4", "🤖 Quick ask GitHub Models GPT-4o"),
        BotCommand("models", "📋 List active AI models & action dashboard"),
        BotCommand("modelhelp", "📖 Detailed model guide & recommendations"),
        BotCommand("task", "🚀 Dispatch autonomous coding agent loop"),
        BotCommand("claude", "🧠 Run Claude Code CLI on workspace"),
        BotCommand("exec", "🖥️ Execute shell command in workspace"),
        BotCommand("cancel", "🛑 Cancel the currently running task/claude/exec"),
        BotCommand("projects", "📁 List workspaces & git repos"),
        BotCommand("newrepo", "✨ Create a new GitHub repo"),
        BotCommand("clone", "📥 Clone a git repository"),
        BotCommand("createtopic", "🧵 Create project sub-channel topic"),
        BotCommand("bind", "🔗 Bind topic to workspace project"),
        BotCommand("unbind", "🔓 Unbind topic from project"),
        BotCommand("pull", "⬇️ Git pull changes"),
        BotCommand("push", "⬆️ Git push changes"),
        BotCommand("branch", "🌿 List / switch git branches"),
        BotCommand("diff", "🔍 View uncommitted git diff"),
        BotCommand("status", "📊 View server & agent health metrics"),
        BotCommand("note", "📝 Quick note to Obsidian second-brain"),
        BotCommand("vault", "📓 List Obsidian notes & specs"),
        BotCommand("addcmd", "➕ Add custom shortcut command"),
        BotCommand("delcmd", "➖ Delete a custom shortcut"),
        BotCommand("cmds", "📋 View all custom shortcuts"),
        BotCommand("help", "❓ Open interactive help & handbook"),
    ]

    try:
        custom_cmds = load_custom_commands()
        for name, tpl in sorted(custom_cmds.items())[:20]:
            desc = f"⚡ Shortcut: {tpl}"
            if len(desc) > 50:
                desc = desc[:47] + "..."
            commands.append(BotCommand(name, desc))
    except Exception as e:
        logger.warning(f"Could not load custom commands for autocomplete: {e}")

    try:
        await bot.set_my_commands(commands)
        logger.info(f"Synchronized {len(commands)} commands to Telegram autocomplete menu.")
    except Exception as e:
        logger.warning(f"Failed to set Telegram bot commands: {e}")
