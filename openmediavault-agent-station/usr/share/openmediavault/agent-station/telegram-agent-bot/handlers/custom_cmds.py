"""
User-Defined Dynamic Custom Commands & Template Expansions.
Allows creating and hot-reloading dynamic shortcuts stored on disk and mirrored to Obsidian.
"""

import json
from telegram import Update
from telegram.ext import ContextTypes
from core.config import CUSTOM_CMDS_FILE, OBSIDIAN_CMDS_FILE, BUILTIN_COMMANDS, logger
from core.security import check_auth, sanitize_cmd_name

def load_custom_commands() -> dict[str, str]:
    """Loads user-defined custom commands from disk."""
    if CUSTOM_CMDS_FILE.exists():
        try:
            with open(CUSTOM_CMDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load custom commands: {e}")
    return {}

def save_custom_commands(cmds: dict[str, str]):
    """Persists custom commands to workspace and mirrors to Obsidian vault."""
    try:
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

async def addcmd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds or updates a custom user-defined shortcut command."""
    if not await check_auth(update):
        return
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: `/addcmd <command_name> <command_template>`\n\n"
            "Examples:\n"
            "• `/addcmd test /exec pytest -v`\n"
            "• `/addcmd build /exec npm run build`\n"
            "• `/addcmd review /chat \"Review this code: {args}\"`\n"
            "• `/addcmd pr /task \"Create PR draft & changelog summary\"`",
            parse_mode="Markdown"
        )
        return

    raw_name = context.args[0]
    name = sanitize_cmd_name(raw_name)
    if not name:
        await update.effective_message.reply_text(
            "❌ Invalid command name. Use alphanumeric characters and underscores only (1-32 chars)."
        )
        return

    if name in BUILTIN_COMMANDS:
        await update.effective_message.reply_text(
            f"❌ `{name}` is a reserved built-in command and cannot be overridden.",
            parse_mode="Markdown"
        )
        return

    template = " ".join(context.args[1:]).strip()
    cmds = load_custom_commands()
    cmds[name] = template
    save_custom_commands(cmds)

    # Sync to Telegram autocomplete menu
    try:
        from ui.command_menu import sync_bot_commands
        await sync_bot_commands(context.bot)
    except Exception as se:
        logger.warning(f"Could not refresh autocomplete menu after addcmd: {se}")

    await update.effective_message.reply_text(
        f"✅ *Custom Command Registered!*\n\n"
        f"• *Command:* `/{name}`\n"
        f"• *Template:* `{template}`\n"
        f"• *Autocomplete:* Registered in Telegram menu!\n\n"
        f"Run it anytime via `/{name}` or tap it in autocomplete.",
        parse_mode="Markdown"
    )

async def delcmd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes a custom user-defined shortcut command."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: `/delcmd <command_name>`", parse_mode="Markdown")
        return

    name = sanitize_cmd_name(context.args[0])
    if not name:
        await update.effective_message.reply_text("❌ Invalid command name.")
        return

    cmds = load_custom_commands()
    if name not in cmds:
        await update.effective_message.reply_text(f"⚠️ Custom command `/{name}` does not exist.", parse_mode="Markdown")
        return

    del cmds[name]
    save_custom_commands(cmds)

    try:
        from ui.command_menu import sync_bot_commands
        await sync_bot_commands(context.bot)
    except Exception as se:
        logger.warning(f"Could not refresh autocomplete menu after delcmd: {se}")

    await update.effective_message.reply_text(f"✅ Deleted custom command `/{name}`.", parse_mode="Markdown")

async def customcmds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all user-defined custom commands."""
    if not await check_auth(update):
        return
    cmds = load_custom_commands()
    if not cmds:
        await update.effective_message.reply_text(
            "📋 *No custom commands configured yet.*\n\n"
            "Create your first shortcut with:\n"
            "`/addcmd <name> <template>`\n\n"
            "Example: `/addcmd test /exec pytest -v`",
            parse_mode="Markdown"
        )
        return

    lines = [f"• `/{k}` ➔ `{v}`" for k, v in sorted(cmds.items())]
    await update.effective_message.reply_text(
        f"⚡ *User-Defined Custom Shortcuts ({len(cmds)}):*\n\n" + "\n".join(lines) + "\n\n"
        "*(All shortcuts autocomplete in Telegram automatically!)*",
        parse_mode="Markdown"
    )

async def dynamic_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Intercepts custom dynamic command calls and executes the expanded template."""
    if not await check_auth(update):
        return
    msg = update.effective_message
    if not msg or not msg.text:
        return

    raw_text = msg.text.strip()
    if not raw_text.startswith("/"):
        return

    parts = raw_text.split(maxsplit=1)
    cmd_name = parts[0].lstrip("/").split("@")[0].lower()
    passed_args = parts[1].strip() if len(parts) > 1 else ""

    custom_cmds = load_custom_commands()
    if cmd_name not in custom_cmds:
        return

    template = custom_cmds[cmd_name]

    # Dynamic argument substitution: {args}
    if "{args}" in template:
        expanded = template.replace("{args}", passed_args).strip()
    elif passed_args:
        expanded = f"{template} {passed_args}".strip()
    else:
        expanded = template.strip()

    logger.info(f"Executing dynamic command /{cmd_name} -> {expanded}")

    # Dispatch expanded command
    expanded_parts = expanded.split()
    if not expanded_parts:
        return

    target_cmd = expanded_parts[0].lstrip("/").lower()
    context.args = expanded_parts[1:]

    # Import handler routers
    from .ai_chat import chat_cmd, gemini_cmd, gpt4_cmd
    from .system import exec_cmd, task_cmd, claude_cmd, status_cmd, help_cmd
    from .git_ops import pull_cmd, push_cmd, branch_cmd, diff_cmd, projects_cmd
    from .vault import vault_cmd, note_cmd

    handlers = {
        "exec": exec_cmd,
        "chat": chat_cmd,
        "gemini": gemini_cmd,
        "gpt4": gpt4_cmd,
        "task": task_cmd,
        "claude": claude_cmd,
        "pull": pull_cmd,
        "push": push_cmd,
        "branch": branch_cmd,
        "diff": diff_cmd,
        "projects": projects_cmd,
        "vault": vault_cmd,
        "note": note_cmd,
        "status": status_cmd,
        "help": help_cmd,
    }

    handler = handlers.get(target_cmd)
    if handler:
        await handler(update, context)
    else:
        await msg.reply_text(
            f"⚡ Custom command `/{cmd_name}` expanded to:\n`{expanded}`\n\nTarget handler `/{target_cmd}` not found.",
            parse_mode="Markdown"
        )
