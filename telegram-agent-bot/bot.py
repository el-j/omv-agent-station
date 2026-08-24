#!/usr/bin/env python3
"""
Telegram Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8.
Provides remote command execution, autonomous coding agent dispatch (Hermes/Aider/Claude Code),
Obsidian second-brain integration, LiteLLM gateway telemetry, GitHub repo creation,
Telegram Forum Topics (project-scoped sub-channels), and User-Defined Dynamic Custom Commands.
"""

import sys
import os
import json
import re
from pathlib import Path

try:
    _bot_dir = str(Path(__file__).parent.resolve())
except NameError:
    _bot_dir = str(Path("telegram-agent-bot").resolve())

if _bot_dir not in sys.path:
    sys.path.insert(0, _bot_dir)
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Core configurations & defaults
from core.config import (
    BOT_TOKEN,
    ALLOWED_USER_ID,
    LITELLM_BASE,
    LITELLM_KEY,
    WORKSPACE,
    OBSIDIAN_VAULT,
    GIT_BIN,
    GIT_AUTHOR_NAME,
    GIT_AUTHOR_EMAIL,
    GITHUB_USER,
    GITHUB_TOKEN,
    GITLAB_USER,
    GITLAB_TOKEN,
    BITBUCKET_USER,
    BITBUCKET_TOKEN,
    TMUX_BIN,
    UPTIME_BIN,
    DF_BIN,
    AIDER_BIN,
    TOPICS_FILE,
    CUSTOM_CMDS_FILE,
    OBSIDIAN_CMDS_FILE,
    BUILTIN_COMMANDS,
    logger,
)
from core.security import (
    sanitize_project_path,
    sanitize_repo_name,
    sanitize_branch_name,
    sanitize_cmd_name,
    sanitize_git_url,
)
from core.git_auth import init_git_credentials, ai_client

# Handlers & UI Components
from ui.command_menu import sync_bot_commands
from handlers.system import (
    start,
    help_cmd,
    status_cmd,
    exec_cmd,
    task_cmd,
    claude_cmd,
    run_agent_task,
)
from handlers.ai_chat import (
    chat_cmd,
    gemini_cmd,
    gpt4_cmd,
    models_cmd,
    modelhelp_cmd,
)
from handlers.git_ops import (
    projects_cmd,
    newrepo_cmd,
    clone_cmd,
    pull_cmd,
    push_cmd,
    branch_cmd,
    diff_cmd,
)
from handlers.topics import (
    bind_cmd,
    unbind_cmd,
    createtopic_cmd,
)
from handlers.custom_cmds import (
    addcmd_cmd,
    delcmd_cmd,
    customcmds_cmd,
    dynamic_command_handler,
)
from handlers.vault import (
    vault_cmd,
    note_cmd,
    init_obsidian_project_spec,
)
from handlers.interactive import interactive_text_handler
from handlers.callbacks import help_callback_handler

# ---------------------------------------------------------------------------
# Dynamic Core Helpers (Module Globals Bound for Extensibility & Testing)
# ---------------------------------------------------------------------------

def authorized(update: Update) -> bool:
    """Ensure only the configured user can communicate with the bot."""
    if not ALLOWED_USER_ID:
        return True
    if not update.effective_user:
        return False
    user_id = str(update.effective_user.id)
    return user_id == str(ALLOWED_USER_ID)

async def check_auth(update: Update) -> bool:
    """Verifies user authorization and replies with an error if unauthorized."""
    if not authorized(update):
        if update.effective_user:
            logger.warning(f"Unauthorized access attempt from user_id: {update.effective_user.id} (@{update.effective_user.username})")
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ Unauthorized access.\n\n"
                "Please configure your personal numeric Telegram User ID in OMV Services -> Agent Station -> Chat & Messenger."
            )
        return False
    return True

def load_topic_bindings() -> dict:
    """Loads thread-to-project bindings from disk using current module TOPICS_FILE."""
    tf = TOPICS_FILE
    if tf.exists():
        try:
            with open(tf, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {tf}: {e}")
    return {}

def save_topic_bindings(bindings: dict):
    """Saves thread-to-project bindings to disk using current module TOPICS_FILE."""
    tf = TOPICS_FILE
    try:
        tf.parent.mkdir(parents=True, exist_ok=True)
        with open(tf, "w", encoding="utf-8") as f:
            json.dump(bindings, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write {tf}: {e}")

def get_bound_project(chat_id: int, thread_id: int | None) -> str | None:
    """Returns the project folder name bound to a given (chat_id, thread_id) pair."""
    if not thread_id:
        return None
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    return bindings.get(key)

def set_bound_project(chat_id: int, thread_id: int, project_name: str):
    """Binds a project folder name to a given (chat_id, thread_id) pair."""
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    bindings[key] = project_name
    save_topic_bindings(bindings)

def remove_bound_project(chat_id: int, thread_id: int):
    """Removes the project binding for a given (chat_id, thread_id) pair."""
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    if key in bindings:
        del bindings[key]
        save_topic_bindings(bindings)

def resolve_project_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[str | None, list[str]]:
    """Intelligently resolves target project using current module WORKSPACE and topic context."""
    thread_id = update.effective_message.message_thread_id if update.effective_message else None
    chat_id = update.effective_chat.id if update.effective_chat else 0
    bound_project = get_bound_project(chat_id, thread_id)

    args = list(context.args) if context.args else []
    if not args:
        return (bound_project, [])

    first_arg = args[0]
    candidate_dir = WORKSPACE / first_arg
    if candidate_dir.exists() and candidate_dir.is_dir() and not first_arg.startswith("."):
        return (first_arg, args[1:])

    if bound_project:
        return (bound_project, args)

    return (first_arg, args[1:])

def load_custom_commands() -> dict[str, str]:
    """Loads user-defined custom commands from disk using current module CUSTOM_CMDS_FILE."""
    cf = CUSTOM_CMDS_FILE
    if cf.exists():
        try:
            with open(cf, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load custom commands from {cf}: {e}")
    return {}

def save_custom_commands(cmds: dict[str, str]):
    """Persists custom commands to disk using current module CUSTOM_CMDS_FILE and OBSIDIAN_CMDS_FILE."""
    cf = CUSTOM_CMDS_FILE
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        with open(cf, "w", encoding="utf-8") as f:
            json.dump(cmds, f, indent=2)
    except Exception as e:
        logger.error(f"Could not save custom commands to {cf}: {e}")

    try:
        OBSIDIAN_CMDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OBSIDIAN_CMDS_FILE, "w", encoding="utf-8") as f:
            json.dump(cmds, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not mirror custom commands to Obsidian: {e}")

# ---------------------------------------------------------------------------
# Main Application Lifecycle
# ---------------------------------------------------------------------------

def main():
    """Main application lifecycle runner and handler orchestrator."""
    init_git_credentials()

    if not BOT_TOKEN:
        print(
            "ℹ️ TELEGRAM_BOT_TOKEN environment variable not set. Bot is in standby mode. "
            "Configure your token in OMV Services -> Agent Station -> Chat & Messenger to activate.",
            file=sys.stderr
        )
        import time
        while True:
            time.sleep(3600)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(sync_bot_commands).build()

    # Core Built-in Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("models", models_cmd))
    app.add_handler(CommandHandler("modelhelp", modelhelp_cmd))
    app.add_handler(CommandHandler("aihelp", modelhelp_cmd))
    app.add_handler(CommandHandler("projects", projects_cmd))
    app.add_handler(CommandHandler("newrepo", newrepo_cmd))
    app.add_handler(CommandHandler("create", newrepo_cmd))
    app.add_handler(CommandHandler("addcmd", addcmd_cmd))
    app.add_handler(CommandHandler("alias", addcmd_cmd))
    app.add_handler(CommandHandler("delcmd", delcmd_cmd))
    app.add_handler(CommandHandler("removecmd", delcmd_cmd))
    app.add_handler(CommandHandler("customcmds", customcmds_cmd))
    app.add_handler(CommandHandler("cmds", customcmds_cmd))
    app.add_handler(CommandHandler("aliases", customcmds_cmd))
    app.add_handler(CommandHandler("bind", bind_cmd))
    app.add_handler(CommandHandler("unbind", unbind_cmd))
    app.add_handler(CommandHandler("createtopic", createtopic_cmd))
    app.add_handler(CommandHandler("topic", createtopic_cmd))
    app.add_handler(CommandHandler("clone", clone_cmd))
    app.add_handler(CommandHandler("pull", pull_cmd))
    app.add_handler(CommandHandler("push", push_cmd))
    app.add_handler(CommandHandler("branch", branch_cmd))
    app.add_handler(CommandHandler("diff", diff_cmd))
    app.add_handler(CommandHandler("vault", vault_cmd))
    app.add_handler(CommandHandler("note", note_cmd))
    app.add_handler(CommandHandler("chat", chat_cmd))
    app.add_handler(CommandHandler("gemini", gemini_cmd))
    app.add_handler(CommandHandler("gpt4", gpt4_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("claude", claude_cmd))
    app.add_handler(CommandHandler("exec", exec_cmd))

    # Interactive Inline Keyboard Callback Handler
    app.add_handler(CallbackQueryHandler(help_callback_handler))

    # Interactive Plain Text & ForceReply Prompt Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, interactive_text_handler))

    # Dynamic Custom Command Fallback Handler
    app.add_handler(MessageHandler(filters.COMMAND, dynamic_command_handler))

    print("🤖 Telegram Agent Relay Bot starting polling with autocomplete & dashboard support...")
    app.run_polling()

if __name__ == "__main__":
    main()
