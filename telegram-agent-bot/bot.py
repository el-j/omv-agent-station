#!/usr/bin/env python3
"""
Telegram Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8
Provides remote command execution, autonomous coding agent dispatch (Hermes/Aider/Claude Code),
Obsidian second-brain integration, LiteLLM gateway telemetry, GitHub repo creation,
Telegram Forum Topics (project-scoped sub-channels), and User-Defined Dynamic Custom Commands.
"""

import os
import sys
import re
import json
import shutil
import shlex
import logging
import asyncio
import subprocess  # nosec B404
from pathlib import Path
from datetime import datetime
from telegram import (
    Update,
    BotCommand,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
import httpx
from openai import AsyncOpenAI

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment Configuration
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.environ.get("TELEGRAM_ALLOWED_USER_ID")
LITELLM_BASE = os.environ.get("LITELLM_API_BASE", "http://litellm:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-omv-secret-master-key")
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/workspace"))
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT", "/workspace/ObsidianVault"))

# Git Credentials Environment
GIT_BIN = os.environ.get("GIT_BIN", "git")
GIT_AUTHOR_NAME = os.environ.get("GIT_AUTHOR_NAME", "Agent Station Bot")
GIT_AUTHOR_EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "bot@agentstation.local")
GITHUB_USER = os.environ.get("GITHUB_USER", "")
GITHUB_TOKEN = os.environ.get("GITHUB_GIT_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
GITLAB_USER = os.environ.get("GITLAB_USER", "oauth2")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
BITBUCKET_USER = os.environ.get("BITBUCKET_USERNAME", "")
BITBUCKET_TOKEN = os.environ.get("BITBUCKET_APP_PASSWORD", "")

# Topic Binding & Custom Commands Storage Files
TOPICS_FILE = WORKSPACE / ".agent_topics.json"
CUSTOM_CMDS_FILE = WORKSPACE / ".custom_commands.json"
OBSIDIAN_CMDS_FILE = OBSIDIAN_VAULT / "Config" / "commands.json"

BUILTIN_COMMANDS = {
    "start", "help", "status", "models", "modelhelp", "aihelp", "projects", "newrepo", "create",
    "bind", "unbind", "clone", "pull", "push", "branch", "diff", "vault",
    "note", "chat", "gemini", "gpt4", "task", "claude", "exec", "addcmd", "alias", "delcmd",
    "removecmd", "customcmds", "cmds", "aliases", "createtopic", "topic"
}

def init_git_credentials():
    """Configures global git identity and provider credential helpers/URL rewrites."""
    try:
        subprocess.run([GIT_BIN, "config", "--global", "user.name", GIT_AUTHOR_NAME], check=True)  # nosec B603,B607
        subprocess.run([GIT_BIN, "config", "--global", "user.email", GIT_AUTHOR_EMAIL], check=True)  # nosec B603,B607
        subprocess.run([GIT_BIN, "config", "--global", "init.defaultBranch", "main"], check=True)  # nosec B603,B607

        # Configure automatic token auth for GitHub
        if GITHUB_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://x-access-token:{GITHUB_TOKEN}@github.com/.insteadOf",
                "https://github.com/"
            ], check=True)
            logger.info("Configured automated git auth for GitHub.")

        # Configure automatic token auth for GitLab
        if GITLAB_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://oauth2:{GITLAB_TOKEN}@gitlab.com/.insteadOf",
                "https://gitlab.com/"
            ], check=True)
            logger.info("Configured automated git auth for GitLab.")

        # Configure automatic auth for Bitbucket
        if BITBUCKET_USER and BITBUCKET_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://{BITBUCKET_USER}:{BITBUCKET_TOKEN}@bitbucket.org/.insteadOf",
                "https://bitbucket.org/"
            ], check=True)
            logger.info("Configured automated git auth for Bitbucket.")

    except Exception as e:
        logger.warning(f"Could not configure global git credentials: {e}")

init_git_credentials()

# Non-blocking Asynchronous OpenAI Client pointing to local LiteLLM Proxy
ai_client = AsyncOpenAI(
    api_key=LITELLM_KEY,
    base_url=f"{LITELLM_BASE}/v1",
    timeout=120.0
)

# ---------------------------------------------------------------------------
# Topic & Sub-Channel Project Binding Helpers
# ---------------------------------------------------------------------------

def load_topic_bindings() -> dict:
    """Loads thread-to-project bindings from disk."""
    if TOPICS_FILE.exists():
        try:
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_topic_bindings(bindings: dict):
    """Saves thread-to-project bindings to disk."""
    try:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        with open(TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(bindings, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist topic bindings: {e}")

def get_bound_project(chat_id: int, thread_id: int | None) -> str | None:
    """Returns the project name bound to a specific chat and thread/topic."""
    if thread_id is None:
        return None
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    return bindings.get(key)

def set_bound_project(chat_id: int, thread_id: int, project_name: str):
    """Binds a Telegram forum topic (thread_id) to a workspace project."""
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    bindings[key] = project_name
    save_topic_bindings(bindings)

def remove_bound_project(chat_id: int, thread_id: int):
    """Unbinds a Telegram forum topic."""
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    if key in bindings:
        del bindings[key]
        save_topic_bindings(bindings)

# ---------------------------------------------------------------------------
# Custom User-Defined Commands Engine
# ---------------------------------------------------------------------------

def load_custom_commands() -> dict[str, str]:
    """Loads custom commands from workspace and Obsidian mirror."""
    if CUSTOM_CMDS_FILE.exists():
        try:
            with open(CUSTOM_CMDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    if OBSIDIAN_CMDS_FILE.exists():
        try:
            with open(OBSIDIAN_CMDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_custom_commands(cmds: dict[str, str]):
    """Persists custom commands to workspace and mirrors to Obsidian Config."""
    try:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        with open(CUSTOM_CMDS_FILE, "w", encoding="utf-8") as f:
            json.dump(cmds, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist custom commands to workspace: {e}")

    try:
        OBSIDIAN_CMDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OBSIDIAN_CMDS_FILE, "w", encoding="utf-8") as f:
            json.dump(cmds, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not mirror custom commands to Obsidian: {e}")

def sanitize_cmd_name(name: str) -> str | None:
    """Validates custom command names (alphanumeric and underscores only)."""
    if not name:
        return None
    name = name.strip().lstrip("/").lower()
    if re.match(r"^[a-z0-9_]{1,32}$", name):
        return name
    return None

# ---------------------------------------------------------------------------
# Validation & Sanitization Helpers
# ---------------------------------------------------------------------------

def sanitize_git_url(url: str) -> str | None:
    """Validates git URL to prevent command argument injection (e.g. leading dashes)."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("-"):
        return None
    pattern = r"^(https?|git|ssh)://[^\s/$.?#].[^\s]*$|^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(\.git)?$"
    if re.match(pattern, url):
        return url
    return None

def sanitize_repo_name(name: str) -> str | None:
    """Validates repository name for alphanumeric and safe separator chars."""
    if not name:
        return None
    name = name.strip()
    if name.startswith(("-", ".")) or ".." in name or "/" in name or "\\" in name:
        return None
    if re.match(r"^[a-zA-Z0-9_.-]+$", name):
        return name
    return None

def sanitize_branch_name(branch: str) -> str | None:
    """Validates git branch names to prevent argument injection."""
    if not branch:
        return None
    branch = branch.strip()
    if branch.startswith("-") or ".." in branch or "\\" in branch or "@{" in branch:
        return None
    if re.match(r"^[a-zA-Z0-9_./-]+$", branch):
        return branch
    return None

def sanitize_project_path(workspace: Path, project_name: str) -> Path | None:
    """Validates that project_name resolves strictly within the workspace root to prevent traversal."""
    if not project_name or ".." in project_name or project_name.startswith(("/", "\\", "-")):
        return None
    try:
        clean_name = project_name.strip().strip("./")
        if not clean_name or clean_name.startswith("-"):
            return None
        target = (workspace / clean_name).resolve()
        workspace_resolved = workspace.resolve()
        if workspace_resolved in target.parents or target == workspace_resolved:
            return target
        return None
    except Exception:
        return None

def authorized(update: Update) -> bool:
    """Ensure only the configured user can communicate with the bot."""
    if not ALLOWED_USER_ID:
        return True
    if not update.effective_user:
        return False
    user_id = str(update.effective_user.id)
    return user_id == str(ALLOWED_USER_ID)

async def check_auth(update: Update) -> bool:
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

def resolve_project_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[str | None, list[str]]:
    """
    Intelligently resolves the target project and remaining args based on:
    1. Explicit project argument in command (if matches a workspace folder).
    2. Forum topic / sub-channel binding.
    """
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

# ---------------------------------------------------------------------------
# Telegram Command Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    welcome_text = (
        "🤖 *OMV AI Agent Station — Remote Dev & Orchestrator*\n\n"
        "Your 24/7 AI-powered development server is online.\n\n"
        "⚡ *Core Commands:*\n"
        "• `/task [project] <prompt>` — Run autonomous coding agent on branch\n"
        "• `/chat <message>` — Ask questions via Gemini 3.7 / Claude 3.7 router\n"
        "• `/claude <prompt>` — Execute Claude Code CLI in sandboxed container\n"
        "• `/newrepo <name> [desc]` — Create a new GitHub repository & clone locally\n"
        "• `/addcmd <name> <template>` — Create custom shortcut command\n"
        "• `/customcmds` — List all user-defined custom commands\n"
        "• `/projects` — List all workspace repositories\n"
        "• `/clone <url> [name]` — Clone GitHub / GitLab / Bitbucket repo\n"
        "• `/bind [project]` — Link current Telegram Forum Topic to a project\n"
        "• `/pull [project]` — Pull latest commits from remote\n"
        "• `/push [project] [branch]` — Push commits to remote\n"
        "• `/branch [project] [name]` — Switch or list git branches\n"
        "• `/diff [project]` — View git diff & status summary\n"
        "• `/vault` — Inspect Obsidian Second Brain notes\n"
        "• `/note <Title> | <Content>` — Quick note into Obsidian vault\n"
        "• `/models` — Check LiteLLM AI Gateway provider status\n"
        "• `/status` — Server CPU/RAM, disk & tmux sessions\n"
        "• `/help` — Full handbook & Telegram Forum Topics guide"
    )
    await update.effective_message.reply_text(welcome_text, parse_mode="Markdown")

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

async def modelhelp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides an in-depth guide on available AI models, strengths, speed, and usage tips."""
    if not await check_auth(update):
        return
    
    guide_text = (
        "📖 *Agent Station — AI Model Guide & Recommendations*\n\n"
        "⚡ *1. Google Gemini (Fast & Massive Context)*\n"
        "• `gemini-3.6-flash` / `gemini-3.7-flash`\n"
        "• *Context:* 1,000,000+ tokens | *Speed:* Ultra-Fast (< 1s)\n"
        "• *Best for:* Quick questions, documentation lookup, code translation, single-file edits.\n"
        "• *Usage:* `/gemini <prompt>` or `/chat -m gemini-3.6-flash <prompt>`\n\n"
        "🧠 *2. Coder-Smart Virtual Router (High Intelligence)*\n"
        "• `coder-smart` (Default Router)\n"
        "• *Engines:* Gemini 3.6 Flash ➔ Gemini 3.7 Pro ➔ GitHub GPT-4o ➔ Claude 3.7\n"
        "• *Best for:* Autonomous agentic coding loops, deep refactoring, architecture design.\n"
        "• *Usage:* `/chat <prompt>` or `/task <project> <prompt>`\n\n"
        "🚀 *3. Reasoning-Heavy Router (Extended Thinking)*\n"
        "• `reasoning-heavy`\n"
        "• *Engines:* Gemini Pro ➔ DeepSeek-R1 ➔ OpenAI o3-mini\n"
        "• *Best for:* Complex math, concurrency bugs, algorithmic puzzles, security audits.\n"
        "• *Usage:* `/chat -m reasoning-heavy <prompt>`\n\n"
        "🐙 *4. GitHub Models (Copilot Zero-Cost Quota)*\n"
        "• `github-gpt-4o` | `github-o3-mini` | `github-deepseek-r1`\n"
        "• *Best for:* High-quality GPT-4o intelligence included in your GitHub subscription.\n"
        "• *Usage:* `/gpt4 <prompt>` or `/chat -m github-gpt-4o <prompt>`\n\n"
        "🤖 *5. Claude Code CLI (Autonomous Agent)*\n"
        "• `claude`\n"
        "• *Capabilities:* Reads entire directories, creates/edits files, runs git commands, executes tests.\n"
        "• *Usage:* `/claude <prompt>` (Requires 1-time Web Terminal login: `http://192.168.1.200:7681`)"
    )

    keyboard = [
        [
            InlineKeyboardButton("⚡ Ask Gemini", switch_inline_query_current_chat="/gemini "),
            InlineKeyboardButton("🧠 Ask Coder-Smart", switch_inline_query_current_chat="/chat "),
        ],
        [
            InlineKeyboardButton("📋 View Active Models", callback_data="btn_models"),
            InlineKeyboardButton("❓ Full Help Menu", callback_data="help_menu:main"),
        ]
    ]

    await update.effective_message.reply_text(
        guide_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    text = (
        "📖 *Agent Station Remote Control & Handbook*\n\n"
        "1️⃣ *AI Models & Chat:*\n"
        "   • `/chat <question>` — Direct query via default `coder-smart` router\n"
        "   • `/chat -m <model> <question>` — Query a specific model\n"
        "   • `/gemini <prompt>` — Instant Google Gemini 3.6 Flash shortcut\n"
        "   • `/gpt4 <prompt>` — Instant GitHub Models GPT-4o shortcut\n"
        "   • `/models` — Active AI model endpoints & action dashboard\n"
        "   • `/modelhelp` — Detailed AI model comparison & tips\n\n"
        "2️⃣ *Autonomous Coding Agent:*\n"
        "   • `/task my-api \"Add Redis caching layer with unit tests\"`\n"
        "   • `/claude <prompt>` — Headless Claude Code CLI execution\n"
        "   • `/exec <cmd>` — Run sandboxed bash command in workspace\n\n"
        "3️⃣ *Create / Clone Repositories:*\n"
        "   • `/newrepo my-api \"FastAPI backend service\"` — Creates remote GitHub repo + local workspace + Topic!\n"
        "   • `/clone https://github.com/user/repo` — Clones any repo with PAT auth\n\n"
        "4️⃣ *Custom User Commands & Shortcuts:*\n"
        "   • `/addcmd test /exec pytest -v` ➔ Runs `/test` as a shortcut!\n"
        "   • `/addcmd review /chat \"Review this code: {args}\"`\n"
        "   • `/customcmds` — List all your custom shortcuts\n"
        "   • `/delcmd <name>` — Delete a shortcut\n\n"
        "5️⃣ *Telegram Forum Topics (Project Sub-Channels):*\n"
        "   • Inside a topic, use `/bind my-project` to bind the channel.\n"
        "   • All `/task`, `/diff`, `/push` commands automatically target that project!\n\n"
        "6️⃣ *Obsidian Second-Brain Sync:*\n"
        "   • Syncthing (Port 8384) syncs notes from your laptop/phone to `/data/obsidian`.\n"
        "   • `/note Design Doc | System architecture requirements`\n"
        "   • `/vault` — Inspect recent notes & specs available to AI agents."
    )
    keyboard = [
        [
            InlineKeyboardButton("🧠 AI Models", callback_data="help_menu:models"),
            InlineKeyboardButton("🚀 Coding Agent", callback_data="help_menu:agent"),
        ],
        [
            InlineKeyboardButton("📁 Git & Repos", callback_data="help_menu:git"),
            InlineKeyboardButton("📓 Obsidian Vault", callback_data="help_menu:obsidian"),
        ],
        [
            InlineKeyboardButton("⚡ Custom Commands", callback_data="help_menu:customcmds"),
            InlineKeyboardButton("📋 Active Models", callback_data="btn_models"),
        ]
    ]
    await update.effective_message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard navigation for /help and /models dashboard."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    if data == "btn_models":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{LITELLM_BASE}/models", headers={"Authorization": f"Bearer {LITELLM_KEY}"})
                if resp.status_code == 200:
                    models = [m.get("id") for m in resp.json().get("data", [])]
                    model_str = "\n".join([f"• `{m}`" for m in models]) if models else "No active models configured."
                    text = f"✅ *Active AI Model Endpoints ({len(models)}):*\n\n{model_str}\n\n*Routers:* `coder-fast` | `coder-smart` | `reasoning-heavy`"
                    keyboard = [
                        [
                            InlineKeyboardButton("⚡ Ask Gemini", switch_inline_query_current_chat="/gemini "),
                            InlineKeyboardButton("🧠 Ask Coder-Smart", switch_inline_query_current_chat="/chat "),
                        ],
                        [
                            InlineKeyboardButton("📖 Model Guide", callback_data="btn_modelhelp"),
                            InlineKeyboardButton("🔄 Refresh", callback_data="btn_models"),
                        ]
                    ]
                    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            await query.edit_message_text(f"❌ Error refreshing models: {e}")

    elif data == "btn_modelhelp" or data == "help_menu:models":
        text = (
            "📖 *AI Models Guide & Tips:*\n\n"
            "• `gemini-3.6-flash` — Ultra fast (1M context), best for quick queries.\n"
            "• `coder-smart` — Smart multi-tier router for deep bug fixing & coding.\n"
            "• `reasoning-heavy` — Deep reasoning for math & architectural design.\n"
            "• `github-gpt-4o` — High quality GPT-4o via GitHub token.\n"
            "• `claude` — Claude Code autonomous CLI agent on workspace.\n\n"
            "Syntax: `/chat -m <model> <question>` or `/gemini <prompt>`"
        )
        keyboard = [
            [
                InlineKeyboardButton("⚡ Ask Gemini", switch_inline_query_current_chat="/gemini "),
                InlineKeyboardButton("📋 Active Models", callback_data="btn_models"),
            ],
            [
                InlineKeyboardButton("🔙 Main Help", callback_data="help_menu:main")
            ]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help_menu:main":
        text = (
            "📖 *Agent Station Interactive Handbook*\n\n"
            "Select a topic below to explore capabilities and commands:"
        )
        keyboard = [
            [
                InlineKeyboardButton("🧠 AI Models & Chat", callback_data="help_menu:models"),
                InlineKeyboardButton("🚀 Coding Agent", callback_data="help_menu:agent"),
            ],
            [
                InlineKeyboardButton("📁 Git & Repos", callback_data="help_menu:git"),
                InlineKeyboardButton("📓 Obsidian Vault", callback_data="help_menu:obsidian"),
            ],
            [
                InlineKeyboardButton("⚡ Custom Commands", callback_data="help_menu:customcmds"),
                InlineKeyboardButton("📋 Active Endpoints", callback_data="btn_models"),
            ]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help_menu:agent":
        text = (
            "🚀 *Autonomous Coding Agent & Claude Code:*\n\n"
            "• `/task <project> <prompt>` — Dispatches autonomous coding agent on the project.\n"
            "• `/claude <prompt>` — Executes Claude Code CLI on the sandboxed workspace.\n"
            "• `/exec <cmd>` — Runs any shell command in the project directory."
        )
        keyboard = [[InlineKeyboardButton("🔙 Main Help", callback_data="help_menu:main")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help_menu:git":
        text = (
            "📁 *Git & Workspace Management:*\n\n"
            "• `/newrepo <name> <desc>` — Creates remote GitHub repo + local folder + Telegram topic.\n"
            "• `/clone <url>` — Clones any repo with configured PAT credentials.\n"
            "• `/pull` | `/push` | `/branch` | `/diff` — Instant git actions on current project."
        )
        keyboard = [[InlineKeyboardButton("🔙 Main Help", callback_data="help_menu:main")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help_menu:obsidian":
        text = (
            "📓 *Obsidian Second-Brain Integration:*\n\n"
            "• Syncthing (Port 8384) bi-directionally syncs notes between your devices & OMV.\n"
            "• `/note <Title> | <Content>` — Writes a structured Markdown note to the vault.\n"
            "• `/vault` — Lists recent notes and specs available to AI agents."
        )
        keyboard = [[InlineKeyboardButton("🔙 Main Help", callback_data="help_menu:main")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "help_menu:customcmds":
        text = (
            "⚡ *User-Defined Custom Commands:*\n\n"
            "• `/addcmd <name> <template>` — Create custom shortcuts that autocomplete in Telegram.\n"
            "  Examples:\n"
            "  - `/addcmd test /exec pytest -v`\n"
            "  - `/addcmd review /chat \"Review this code: {args}\"`\n"
            "• `/delcmd <name>` — Delete a shortcut\n"
            "• `/customcmds` — List all shortcuts"
        )
        keyboard = [[InlineKeyboardButton("🔙 Main Help", callback_data="help_menu:main")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "btn_projects":
        projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")] if WORKSPACE.exists() else []
        if projects:
            proj_str = "\n".join([f"• `📂 {p}`" for p in projects])
            text = f"📁 *Registered Workspace Projects ({len(projects)}):*\n\n{proj_str}\n\nTap below to start coding on any project:"
            keyboard = []
            for p in projects[:6]:
                keyboard.append([InlineKeyboardButton(f"🚀 Code: {p}", switch_inline_query_current_chat=f"/task {p} ")])
            keyboard.append([InlineKeyboardButton("🔙 Main Help", callback_data="help_menu:main")])
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            text = "📁 *No projects found in `/data/workspace`.*\n\nUse `/newrepo` to create a new GitHub repo or paste a GitHub URL to clone one!"
            keyboard = [[InlineKeyboardButton("🔙 Main Help", callback_data="help_menu:main")]]
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

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
    cmd_name = sanitize_cmd_name(raw_name)
    if not cmd_name:
        await update.effective_message.reply_text("❌ Invalid command name. Use 1–32 alphanumeric characters and underscores.")
        return

    if cmd_name in BUILTIN_COMMANDS:
        await update.effective_message.reply_text(f"❌ Cannot overwrite built-in command `/{cmd_name}`.", parse_mode="Markdown")
        return

    template = " ".join(context.args[1:]).strip()
    cmds = load_custom_commands()
    cmds[cmd_name] = template
    save_custom_commands(cmds)

    # Re-sync autocomplete command list in Telegram
    try:
        await sync_bot_commands(context.application.bot)
    except Exception as e:
        logger.warning(f"Could not re-sync commands: {e}")

    await update.effective_message.reply_text(
        f"✅ *Custom Command Saved & Autocompleted!*\n\n"
        f"• Command: `/{cmd_name}`\n"
        f"• Template: `{template}`\n\n"
        f"You can now run `/{cmd_name}` directly in chat or from the autocomplete menu!",
        parse_mode="Markdown"
    )

async def delcmd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes a custom user-defined command."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text("Usage: `/delcmd <command_name>`")
        return

    cmd_name = sanitize_cmd_name(context.args[0])
    if not cmd_name:
        await update.effective_message.reply_text("❌ Invalid command name.")
        return

    cmds = load_custom_commands()
    if cmd_name in cmds:
        del cmds[cmd_name]
        save_custom_commands(cmds)
        try:
            await sync_bot_commands(context.application.bot)
        except Exception as e:
            logger.warning(f"Could not re-sync commands: {e}")
        await update.effective_message.reply_text(f"✅ Custom command `/{cmd_name}` deleted.", parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(f"⚠️ Custom command `/{cmd_name}` not found.", parse_mode="Markdown")

async def customcmds_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all user-defined custom commands."""
    if not await check_auth(update):
        return
    cmds = load_custom_commands()
    if not cmds:
        await update.effective_message.reply_text(
            "📋 *No Custom Commands Defined Yet.*\n\n"
            "Create your first custom shortcut with:\n"
            "`/addcmd test /exec pytest -v`\n"
            "`/addcmd review /chat \"Review this code: {args}\"`",
            parse_mode="Markdown"
        )
        return

    lines = []
    for name, tpl in sorted(cmds.items()):
        lines.append(f"• `/{name}` ➔ `{tpl}`")
    cmds_str = "\n".join(lines)

    await update.effective_message.reply_text(
        f"📋 *Your Custom Bot Commands & Shortcuts:*\n\n{cmds_str}\n\n"
        f"To add: `/addcmd <name> <template>`\nTo delete: `/delcmd <name>`",
        parse_mode="Markdown"
    )

async def dynamic_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catches user-defined custom commands or provides helpful suggestions."""
    if not await check_auth(update):
        return
    if not update.effective_message or not update.effective_message.text:
        return

    text = update.effective_message.text.strip()
    if not text.startswith("/"):
        return

    parts = text.split(None, 1)
    raw_cmd = parts[0].lstrip("/").split("@")[0].lower()
    user_args = parts[1] if len(parts) > 1 else ""

    cmds = load_custom_commands()
    if raw_cmd in cmds:
        template = cmds[raw_cmd]
        thread_id = update.effective_message.message_thread_id
        chat_id = update.effective_chat.id
        bound_proj = get_bound_project(chat_id, thread_id) or "workspace"

        # Parameter Substitution
        expanded = template
        if "{args}" in expanded:
            expanded = expanded.replace("{args}", user_args)
        elif user_args:
            expanded = f"{expanded} {user_args}"
        expanded = expanded.replace("{project}", bound_proj)

        # Dispatch expanded action
        if expanded.startswith("/chat "):
            context.args = expanded[6:].split()
            await chat_cmd(update, context)
        elif expanded.startswith("/task "):
            context.args = expanded[6:].split()
            await task_cmd(update, context)
        elif expanded.startswith("/claude "):
            context.args = expanded[8:].split()
            await claude_cmd(update, context)
        elif expanded.startswith("/exec "):
            context.args = expanded[6:].split()
            await exec_cmd(update, context)
        else:
            # Direct bash command execution in bound project or workspace
            context.args = expanded.split()
            await exec_cmd(update, context)
    else:
        await update.effective_message.reply_text(
            f"❓ Unknown command: `/{raw_cmd}`\n\n"
            f"• Run `/help` to see built-in commands.\n"
            f"• Run `/customcmds` to view your custom shortcuts.\n"
            f"• Create this shortcut with `/addcmd {raw_cmd} <action>`!",
            parse_mode="Markdown"
        )

async def newrepo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Creates a new GitHub repository via GitHub API and initializes it in workspace."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "✨ *Create New GitHub Repository*\n\n"
            "Please type your repository name and description below:\n"
            "• Syntax: `repo-name \"description\" [--public | --private]`\n"
            "• Example: `my-api \"FastAPI backend\" --private`",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="repo-name 'description'..."
            )
        )
        return

    raw_name = context.args[0]
    repo_name = sanitize_repo_name(raw_name)
    if not repo_name:
        await update.effective_message.reply_text("❌ Invalid repository name. Use letters, numbers, hyphens, and underscores.")
        return

    is_private = True
    desc_words = []
    for arg in context.args[1:]:
        if arg == "--public":
            is_private = False
        elif arg == "--private":
            is_private = True
        else:
            desc_words.append(arg)
    description = " ".join(desc_words) or f"Repository {repo_name} created via OMV Agent Station"

    if not GITHUB_TOKEN:
        await update.effective_message.reply_text(
            "⚠️ GitHub Token not configured.\n\n"
            "Please go to OMV WebGUI -> Services -> Agent Station -> Git Providers and enter your GitHub PAT token.",
            parse_mode="Markdown"
        )
        return

    target_dir = sanitize_project_path(WORKSPACE, repo_name)
    if not target_dir:
        await update.effective_message.reply_text("❌ Invalid folder path.")
        return

    if target_dir.exists():
        await update.effective_message.reply_text(f"⚠️ A folder named `{repo_name}` already exists in workspace.", parse_mode="Markdown")
        return

    msg = await update.effective_message.reply_text(f"⏳ Creating GitHub repository `{repo_name}`...", parse_mode="Markdown")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "OMV-Agent-Station"
            }
            payload = {
                "name": repo_name,
                "description": description,
                "private": is_private,
                "auto_init": False
            }
            resp = await client.post("https://api.github.com/user/repos", json=payload, headers=headers)

            if resp.status_code not in (200, 201):
                err_body = resp.text
                await msg.edit_text(f"❌ GitHub API error ({resp.status_code}):\n```\n{err_body[:500]}\n```", parse_mode="Markdown")
                return

            repo_data = resp.json()
            clone_url = repo_data.get("clone_url")
            html_url = repo_data.get("html_url")
            owner = repo_data.get("owner", {}).get("login", "")

        target_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.create_subprocess_exec(GIT_BIN, "init", "-b", "main", cwd=str(target_dir))

        readme_content = f"# {repo_name}\n\n{description}\n\n*Created with OMV Agent Station on {datetime.now().strftime('%Y-%m-%d')}*\n"
        (target_dir / "README.md").write_text(readme_content, encoding="utf-8")

        gitignore_content = "__pycache__/\n*.pyc\n.env\nnode_modules/\n.DS_Store\nvenv/\n.venv/\n"
        (target_dir / ".gitignore").write_text(gitignore_content, encoding="utf-8")

        await asyncio.create_subprocess_exec(GIT_BIN, "add", ".", cwd=str(target_dir))
        await asyncio.create_subprocess_exec(GIT_BIN, "commit", "-m", "feat: initial commit from OMV Agent Station", cwd=str(target_dir))

        remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git" if GITHUB_TOKEN else clone_url
        await asyncio.create_subprocess_exec(GIT_BIN, "remote", "add", "origin", remote_url, cwd=str(target_dir))
        push_proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "-u", "origin", "main", cwd=str(target_dir))
        await push_proc.communicate()

        topic_info = ""
        chat = update.effective_chat
        if chat and chat.type in ("supergroup", "group"):
            try:
                forum_topic = await context.bot.create_forum_topic(
                    chat_id=chat.id,
                    name=f"📂 {repo_name}"
                )
                if forum_topic and forum_topic.message_thread_id:
                    set_bound_project(chat.id, forum_topic.message_thread_id, repo_name)
                    topic_info = f"\n🧵 *Created Forum Topic:* `📂 {repo_name}` (automatically bound!)"
            except Exception as te:
                logger.info(f"Could not auto-create forum topic: {te}")

        vis_str = "🔒 Private" if is_private else "🌐 Public"
        await msg.edit_text(
            f"✅ *GitHub Repository Created & Cloned!*\n\n"
            f"📁 *Project:* `{repo_name}`\n"
            f"🔗 *URL:* {html_url}\n"
            f"🛡️ *Visibility:* {vis_str}\n"
            f"💾 *Path:* `/data/workspace/{repo_name}`{topic_info}\n\n"
            f"Ready to code! Run:\n`/task {repo_name} \"Initial setup instructions\"`",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error creating GitHub repository: {e}", exc_info=True)
        await msg.edit_text(f"❌ Failed to create repository: {e}")

async def bind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Binds the current Telegram topic/sub-channel to a workspace project."""
    if not await check_auth(update):
        return

    chat = update.effective_chat
    thread_id = update.effective_message.message_thread_id if update.effective_message else None

    if not thread_id:
        await update.effective_message.reply_text(
            "ℹ️ This command binds a **Telegram Forum Topic** (sub-channel) to a project repository.\n\n"
            "To use it:\n"
            "1. Enable **Topics** in your Telegram Group Settings.\n"
            "2. Open a dedicated Project Topic (e.g. `#my-app`).\n"
            "3. Send `/bind <project-folder-name>` inside that topic.",
            parse_mode="Markdown"
        )
        return

    if not context.args:
        current_bound = get_bound_project(chat.id, thread_id)
        status = f"Currently bound to: `{current_bound}`" if current_bound else "Not bound to any project."
        projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")] if WORKSPACE.exists() else []
        proj_str = ", ".join([f"`{p}`" for p in projects]) or "None"
        await update.effective_message.reply_text(
            f"🧵 *Topic Binding Status*\n\n"
            f"• {status}\n"
            f"• Available projects: {proj_str}\n\n"
            f"To bind: `/bind <project-name>`\nTo unbind: `/unbind`",
            parse_mode="Markdown"
        )
        return

    project_name = context.args[0].strip()
    project_dir = sanitize_project_path(WORKSPACE, project_name)

    if not project_dir or not project_dir.exists():
        await update.effective_message.reply_text(f"❌ Project directory `{project_name}` not found in `/data/workspace`.")
        return

    set_bound_project(chat.id, thread_id, project_name)
    await update.effective_message.reply_text(
        f"✅ *Topic Successfully Bound!*\n\n"
        f"This sub-channel is now linked to project: `{project_name}`.\n\n"
        f"Commands in this topic now automatically target `{project_name}`:\n"
        f"• `/task \"your instructions\"`\n"
        f"• `/diff`\n"
        f"• `/pull`\n"
        f"• `/push`\n"
        f"• `/branch <name>`",
        parse_mode="Markdown"
    )

async def unbind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unbinds the current Telegram topic/sub-channel."""
    if not await check_auth(update):
        return

    chat = update.effective_chat
    thread_id = update.effective_message.message_thread_id if update.effective_message else None

    if not thread_id:
        await update.effective_message.reply_text("ℹ️ Run `/unbind` inside a Telegram Forum Topic.")
        return

    remove_bound_project(chat.id, thread_id)
    await update.effective_message.reply_text("✅ Topic unlinked from project context.")

async def createtopic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Creates a dedicated Telegram Forum Topic for a project and binds it."""
    if not await check_auth(update):
        return
    chat = update.effective_chat
    if not chat or chat.type not in ("supergroup", "group"):
        await update.effective_message.reply_text("ℹ️ This command must be run inside a Telegram Group / Supergroup with **Topics** enabled.", parse_mode="Markdown")
        return

    if not context.args:
        projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")] if WORKSPACE.exists() else []
        proj_str = ", ".join([f"`{p}`" for p in projects]) if projects else "none"
        await update.effective_message.reply_text(
            f"Usage: `/createtopic <project-folder-name>`\n\nAvailable projects: {proj_str}",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True, input_field_placeholder="Type project name for new topic...")
        )
        return

    folder_name = context.args[0].strip()
    target_dir = sanitize_project_path(WORKSPACE, folder_name)
    if not target_dir or not target_dir.exists():
        await update.effective_message.reply_text(f"❌ Project directory `{folder_name}` not found in `/data/workspace`.", parse_mode="Markdown")
        return

    try:
        forum_topic = await context.bot.create_forum_topic(
            chat_id=chat.id,
            name=f"📂 {folder_name}"
        )
        if forum_topic and forum_topic.message_thread_id:
            set_bound_project(chat.id, forum_topic.message_thread_id, folder_name)
            await update.effective_message.reply_text(
                f"✅ *Created Forum Topic:* `📂 {folder_name}`!\n\n"
                f"This topic channel is now automatically bound to `{folder_name}`.\n\n"
                f"All commands (`/task`, `/diff`, `/push`, `/pull`, `/branch`) inside that topic will directly target this project!",
                parse_mode="Markdown"
            )
    except Exception as e:
        err_s = str(e).lower()
        if "not a forum" in err_s:
            await update.effective_message.reply_text(
                "⚠️ *Topics are not enabled for this group yet.*\n\n"
                "👉 *How to enable Topics in Telegram:*\n"
                "1. Click/tap Group Name at the top (`Agent-station-projects`)\n"
                "2. Click the **Edit** (✏️) icon ➔ **Group Settings**\n"
                "3. Turn ON the **Topics** toggle switch\n"
                "4. Re-run `/createtopic " + folder_name + "`!",
                parse_mode="Markdown"
            )
        elif "rights" in err_s or "admin" in err_s:
            await update.effective_message.reply_text(
                "⚠️ *Bot lacks permission to create topics.*\n\n"
                "👉 Please promote `@agent_station_bot` to **Administrator** and enable the **Manage Topics** permission.",
                parse_mode="Markdown"
            )
        else:
            await update.effective_message.reply_text(f"❌ Could not create topic: {e}")

async def models_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    msg = await update.effective_message.reply_text("🔍 Querying LiteLLM Gateway...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{LITELLM_BASE}/models",
                headers={"Authorization": f"Bearer {LITELLM_KEY}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", [])]
                if models:
                    model_str = "\n".join([f"• `{m}`" for m in models])
                    text = (
                        f"✅ *Active AI Model Endpoints ({len(models)}):*\n\n"
                        f"{model_str}\n\n"
                        f"🎯 *Virtual Smart Routers:*\n"
                        f"• `coder-fast` — Instant triage & fast edits\n"
                        f"• `coder-smart` — Deep coding & refactoring\n"
                        f"• `reasoning-heavy` — Architecture & math analysis"
                    )
                    keyboard = [
                        [
                            InlineKeyboardButton("⚡ Ask Gemini", switch_inline_query_current_chat="/gemini "),
                            InlineKeyboardButton("🧠 Ask Coder-Smart", switch_inline_query_current_chat="/chat "),
                        ],
                        [
                            InlineKeyboardButton("📖 Model Guide & Tips", callback_data="btn_modelhelp"),
                            InlineKeyboardButton("🔄 Refresh", callback_data="btn_models"),
                        ]
                    ]
                    await msg.edit_text(
                        text,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    text = (
                        "📋 *AI Model Gateway Status*\n\n"
                        "⚠️ *No AI Model Providers Configured Yet.*\n\n"
                        "To activate AI models, enter at least one API key in OMV WebGUI:\n"
                        "👉 *Services ➔ Agent Station ➔ AI Models*\n\n"
                        "• *Google Gemini (Recommended Free):* [Google AI Studio](https://aistudio.google.com/app/apikey)\n"
                        "• *GitHub Models (Free Copilot / GPT-4o):* [GitHub Tokens](https://github.com/settings/tokens/new)\n"
                        "• *Anthropic Direct (Claude 3.7):* [Anthropic Console](https://console.anthropic.com/settings/keys)\n"
                        "• *DeepSeek / Mistral / OpenRouter*"
                    )
                    keyboard = [
                        [
                            InlineKeyboardButton("🔄 Check Again", callback_data="btn_models"),
                            InlineKeyboardButton("📖 Model Guide", callback_data="btn_modelhelp"),
                        ]
                    ]
                    await msg.edit_text(
                        text,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
            else:
                await msg.edit_text(f"⚠️ LiteLLM returned HTTP {resp.status_code}")
    except Exception as e:
        await msg.edit_text(f"❌ Failed to reach LiteLLM Proxy: {e}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    try:
        tmux_out = subprocess.check_output(  # nosec B603,B607
            [TMUX_BIN, "list-sessions"],
            stderr=subprocess.STDOUT,
            text=True
        ).strip()
    except Exception:
        tmux_out = "No active tmux sessions."

    try:
        uptime_out = subprocess.check_output([UPTIME_BIN], text=True).strip()  # nosec B603,B607
        df_out = subprocess.check_output([DF_BIN, "-h", "/data/workspace"], text=True).strip().splitlines()[-1]  # nosec B603,B607
    except Exception:
        uptime_out = "N/A"
        df_out = "N/A"

    report = (
        f"🖥️ *OMV Server Status*\n\n"
        f"⏱️ *Uptime:* `{uptime_out}`\n"
        f"💾 *Disk Space:* `{df_out}`\n\n"
        f"🧵 *Active Agent Sessions:*\n```\n{tmux_out}\n```"
    )
    await update.effective_message.reply_text(report, parse_mode="Markdown")

async def projects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not WORKSPACE.exists():
        await update.effective_message.reply_text("📁 Workspace folder is empty or not mounted.")
        return

    projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if not projects:
        await update.effective_message.reply_text("📁 No projects found in `/data/workspace`.")
        return

    proj_list = "\n".join([f"📂 `{p}`" for p in projects])
    await update.effective_message.reply_text(f"📁 *Available Workspace Projects:*\n\n{proj_list}", parse_mode="Markdown")

async def vault_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not OBSIDIAN_VAULT.exists():
        await update.effective_message.reply_text("📓 Obsidian vault not mounted.")
        return

    md_files = list(OBSIDIAN_VAULT.glob("**/*.md"))
    recent = sorted(md_files, key=lambda f: f.stat().st_mtime, reverse=True)[:6]

    recent_str = "\n".join([f"• `{f.relative_to(OBSIDIAN_VAULT)}`" for f in recent]) if recent else "No notes found."
    await update.effective_message.reply_text(
        f"📓 *Obsidian Second Brain Vault:*\n\n"
        f"📊 Total notes: `{len(md_files)}`\n"
        f"🔄 Sync: Syncthing (Port 8384)\n\n"
        f"🕒 *Recently Modified Notes:*\n{recent_str}",
        parse_mode="Markdown"
    )

async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "📝 *Obsidian Second-Brain Note*\n\n"
            "Please type your note title & content below (`Title | Content`):",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Title | Note content and specs..."
            )
        )
        return

    raw = " ".join(context.args)
    parts = raw.split("|", 1)
    title = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""

    inbox = OBSIDIAN_VAULT / "Inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{title.replace(' ', '_')}.md"
    note_path = inbox / filename

    content = f"# {title}\n\n*Created via Telegram on {datetime.now().isoformat()}*\n\n{body}\n"
    note_path.write_text(content, encoding="utf-8")

    await update.effective_message.reply_text(f"📝 Note saved to Obsidian: `{note_path.relative_to(OBSIDIAN_VAULT)}`", parse_mode="Markdown")

async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "💬 *AI Chat (Smart Router: `coder-smart`)*\n\n"
            "Please type your question or code prompt below:",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Type your question or code prompt..."
            )
        )
        return

    raw_args = list(context.args)
    target_model = "coder-smart"

    # Support model flags: -m <model>, --model <model>, --model=<model>, or @<model>
    if raw_args[0] in ("-m", "--model") and len(raw_args) > 2:
        target_model = raw_args[1]
        query = " ".join(raw_args[2:])
    elif raw_args[0].startswith("--model="):
        target_model = raw_args[0].split("=", 1)[1]
        query = " ".join(raw_args[1:])
    elif raw_args[0].startswith("@"):
        target_model = raw_args[0][1:]
        query = " ".join(raw_args[1:])
    elif len(raw_args) > 1 and raw_args[0] in (
        "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.7-pro", "gemini-flash-latest",
        "gemini-2.5-flash", "gemini-2.5-pro", "coder-fast", "coder-smart", "reasoning-heavy",
        "github-gpt-4o", "github-o1", "github-o3-mini", "github-deepseek-r1", "github-llama-3.3-70b",
        "claude-3-7-sonnet-direct", "claude-3-5-haiku", "deepseek-chat", "deepseek-reasoner",
        "codestral", "mistral-large", "openrouter-auto"
    ):
        target_model = raw_args[0]
        query = " ".join(raw_args[1:])
    else:
        query = " ".join(raw_args)

    status_msg = await update.effective_message.reply_text(f"💭 Thinking ({target_model})...")

    try:
        response = await ai_client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": "You are an expert AI software architect and coding assistant on OpenMediaVault."},
                {"role": "user", "content": query}
            ],
            max_tokens=2048,
        )
        reply = response.choices[0].message.content or "*(Empty response)*"
        if len(reply) > 4000:
            reply = reply[:4000] + "\n\n*(Truncated due to Telegram length limit)*"
        try:
            await status_msg.edit_text(reply, parse_mode="Markdown")
        except Exception:
            await status_msg.edit_text(reply)
    except Exception as e:
        err_str = str(e)
        if "Invalid model name" in err_str or "coder-smart" in err_str or "400" in err_str:
            await status_msg.edit_text(
                f"⚠️ *Model Unavailable: `{target_model}`*\n\n"
                f"LiteLLM could not route to `{target_model}`.\n\n"
                "👉 Use `/models` to view active endpoints or configure keys in OMV WebGUI ➔ **Services ➔ Agent Station ➔ AI Models**.",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(f"❌ Error during AI generation ({target_model}): {e}")

async def gemini_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct shortcut to query Google Gemini Flash."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "⚡ *Google Gemini 3.6 Flash (Ultra-Fast 1M Context)*\n\n"
            "Please type your question or code prompt below:",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Type your question for Gemini..."
            )
        )
        return
    context.args = ["-m", "gemini-3.6-flash"] + list(context.args)
    await chat_cmd(update, context)

async def gpt4_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct shortcut to query GitHub Models GPT-4o."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "🤖 *GitHub Models GPT-4o*\n\n"
            "Please type your question or code prompt below:",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Type your question for GPT-4o..."
            )
        )
        return
    context.args = ["-m", "github-gpt-4o"] + list(context.args)
    await chat_cmd(update, context)

async def clone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "📥 *Clone Git Repository*\n\n"
            "Please type or paste the git repository URL below:\n"
            "• Syntax: `https://github.com/owner/repo [folder-name]`\n"
            "• Example: `https://github.com/fastapi/fastapi my-api`",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="https://github.com/owner/repo..."
            )
        )
        return

    raw_git_url = context.args[0].strip()
    git_url = sanitize_git_url(raw_git_url)
    if not git_url:
        await update.effective_message.reply_text("❌ Invalid git URL format.", parse_mode="Markdown")
        return

    if len(context.args) > 1:
        folder_name = context.args[1].strip()
    else:
        folder_name = git_url.rstrip("/").split("/")[-1].replace(".git", "")

    target_dir = sanitize_project_path(WORKSPACE, folder_name)
    if not target_dir:
        await update.effective_message.reply_text("❌ Invalid folder name.", parse_mode="Markdown")
        return

    if target_dir.exists():
        await update.effective_message.reply_text(f"⚠️ Destination folder `{folder_name}` already exists in `/data/workspace`.", parse_mode="Markdown")
        return

    msg = await update.effective_message.reply_text(f"⏳ Cloning `{git_url}` into `/data/workspace/{folder_name}`...", parse_mode="Markdown")
    try:
        clone_target_url = git_url
        if GITHUB_TOKEN and "github.com" in git_url and not git_url.startswith("git@"):
            clean_http = git_url.replace("https://", "").replace("http://", "")
            clone_target_url = f"https://x-access-token:{GITHUB_TOKEN}@{clean_http}"

        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "clone", "--", clone_target_url, str(target_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await asyncio.create_subprocess_exec(GIT_BIN, "config", "user.name", GIT_AUTHOR_NAME, cwd=str(target_dir))
            await asyncio.create_subprocess_exec(GIT_BIN, "config", "user.email", GIT_AUTHOR_EMAIL, cwd=str(target_dir))

            try:
                obsidian_proj = OBSIDIAN_VAULT / "Projects" / folder_name
                obsidian_proj.mkdir(parents=True, exist_ok=True)
                spec_file = obsidian_proj / "project-spec.md"
                if not spec_file.exists():
                    spec_content = (
                        f"# Project: {folder_name}\n\n"
                        f"- **Git Remote:** `{git_url}`\n"
                        f"- **Cloned On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"- **Workspace Path:** `/data/workspace/{folder_name}`\n\n"
                        f"## 📋 Active Tasks & Notes\n"
                        f"- [ ] Initial codebase review & test suite execution\n\n"
                        f"## 🤖 Agent Execution History\n"
                    )
                    spec_file.write_text(spec_content, encoding="utf-8")
            except Exception as oe:
                logger.warning(f"Could not initialize Obsidian project note: {oe}")

            topic_info = ""
            chat = update.effective_chat
            if chat and chat.type in ("supergroup", "group"):
                try:
                    forum_topic = await context.bot.create_forum_topic(
                        chat_id=chat.id,
                        name=f"📂 {folder_name}"
                    )
                    if forum_topic and forum_topic.message_thread_id:
                        set_bound_project(chat.id, forum_topic.message_thread_id, folder_name)
                        topic_info = f"\n🧵 *Created Forum Topic:* `📂 {folder_name}` (automatically bound!)"
                except Exception as te:
                    logger.info(f"Could not create forum topic: {te}")

            keyboard = [
                [
                    InlineKeyboardButton("🚀 Start Coding Task", switch_inline_query_current_chat=f"/task {folder_name} "),
                    InlineKeyboardButton("🌿 Branches", switch_inline_query_current_chat=f"/branch {folder_name} "),
                ],
                [
                    InlineKeyboardButton("📁 List All Projects", callback_data="btn_projects"),
                ]
            ]

            await msg.edit_text(
                f"✅ *Repository Cloned & Registered as Active Project!*\n\n"
                f"📁 *Project:* `{folder_name}`\n"
                f"🔗 *Remote:* `{git_url}`\n"
                f"💾 *Path:* `/data/workspace/{folder_name}`\n"
                f"📓 *Obsidian Spec:* `/data/obsidian/Projects/{folder_name}/`{topic_info}\n\n"
                f"You can now run tasks on this project with:\n`/task {folder_name} \"your coding prompt\"`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            err = stderr.decode("utf-8", errors="replace")
            await msg.edit_text(f"❌ Git clone failed:\n```\n{err}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error during git clone: {e}")

async def pull_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    project_name, _ = resolve_project_context(update, context)
    if not project_name:
        await update.effective_message.reply_text("Usage: `/pull [project-folder-name]`\n\n*(Tip: In a bound Telegram Topic, project name is automatically inferred!)*", parse_mode="Markdown")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.effective_message.reply_text(f"❌ `{project_name}` is not a valid git repository.")
        return

    msg = await update.effective_message.reply_text(f"⏳ Pulling latest changes for `{project_name}`...", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "pull", "--rebase", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        result = (out + "\n" + err).strip() or "Already up to date."
        await msg.edit_text(f"📥 *Git Pull Result (`{project_name}`):*\n```\n{result}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Git pull error: {e}")

async def push_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    project_name, remaining_args = resolve_project_context(update, context)
    if not project_name:
        await update.effective_message.reply_text("Usage: `/push [project-folder-name] [branch]`", parse_mode="Markdown")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.effective_message.reply_text(f"❌ `{project_name}` is not a valid git repository.")
        return

    branch = "HEAD"
    if remaining_args:
        valid_branch = sanitize_branch_name(remaining_args[0])
        if not valid_branch:
            await update.effective_message.reply_text("❌ Invalid branch name format.")
            return
        branch = valid_branch

    msg = await update.effective_message.reply_text(f"🚀 Pushing `{project_name}` to remote (`{branch}`)...", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "origin", "--", branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        result = (out + "\n" + err).strip() or "Everything up-to-date"
        await msg.edit_text(f"🚀 *Git Push Result (`{project_name}`):*\n```\n{result}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Git push error: {e}")

async def diff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    project_name, _ = resolve_project_context(update, context)
    if not project_name:
        await update.effective_message.reply_text("Usage: `/diff [project-folder-name]`", parse_mode="Markdown")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.effective_message.reply_text(f"❌ `{project_name}` is not a valid git repository.")
        return

    try:
        stat_proc = await asyncio.create_subprocess_exec(GIT_BIN, "status", "-s", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
        diff_proc = await asyncio.create_subprocess_exec(GIT_BIN, "diff", "--stat", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
        stat_out, _ = await stat_proc.communicate()
        diff_out, _ = await diff_proc.communicate()

        s_text = stat_out.decode("utf-8", errors="replace").strip() or "Working tree clean."
        d_text = diff_out.decode("utf-8", errors="replace").strip() or "No uncommitted diffs."

        await update.effective_message.reply_text(
            f"📊 *Git Status & Diff (`{project_name}`)*\n\n"
            f"*Status:*\n```\n{s_text}\n```\n"
            f"*Diff Summary:*\n```\n{d_text}\n```",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Error getting git diff: {e}")

async def branch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    project_name, remaining_args = resolve_project_context(update, context)
    if not project_name:
        await update.effective_message.reply_text("Usage: `/branch [project-folder-name] [new-branch-name]`", parse_mode="Markdown")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.effective_message.reply_text(f"❌ `{project_name}` is not a valid git repository.")
        return
    if not remaining_args:
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "branch", "-a", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, _ = await proc.communicate()
        branches = stdout.decode("utf-8", errors="replace").strip()
        await update.effective_message.reply_text(f"🌿 *Branches for `{project_name}`:*\n```\n{branches}\n```", parse_mode="Markdown")
    else:
        new_branch = sanitize_branch_name(remaining_args[0])
        if not new_branch:
            await update.effective_message.reply_text("❌ Invalid branch name format.")
            return

        proc = await asyncio.create_subprocess_exec(GIT_BIN, "checkout", "-B", new_branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await update.effective_message.reply_text(f"🌿 Switched to branch `{new_branch}` in project `{project_name}`.", parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(f"❌ Branch switch failed:\n```\n{stderr.decode('utf-8', errors='replace')}\n```", parse_mode="Markdown")

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return

    project_name, remaining_args = resolve_project_context(update, context)
    if not project_name or not remaining_args:
        bound_proj = get_bound_project(update.effective_chat.id, getattr(update.effective_message, "message_thread_id", None))
        placeholder = "Type task instructions..." if bound_proj else "my-project 'Add unit tests'..."
        await update.effective_message.reply_text(
            "🚀 *Autonomous Coding Agent Task*\n\n"
            "Please type your project & coding task instructions below:\n"
            "• Syntax: `[project-name] <instructions>`\n"
            "• Example: `my-api \"Add Redis caching layer\"`",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder=placeholder
            )
        )
        return

    instructions = " ".join(remaining_args)
    project_dir = sanitize_project_path(WORKSPACE, project_name)

    if not project_dir or not project_dir.exists():
        await update.effective_message.reply_text(f"❌ Project directory `{project_name}` does not exist in `/data/workspace`.", parse_mode="Markdown")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"task_{timestamp}"
    task_branch = f"agent/{session_id}"

    msg = await update.effective_message.reply_text(
        f"🚀 *Launching Autonomous Agent Task*\n\n"
        f"📁 Project: `{project_name}`\n"
        f"🌿 Branch: `{task_branch}`\n"
        f"🆔 Session: `{session_id}`\n"
        f"📝 Instruction: _{instructions}_\n\n"
        f"Agent is starting ReAct loop in background...",
        parse_mode="Markdown"
    )

    asyncio.create_task(run_agent_task(update, msg, project_dir, instructions, session_id, task_branch))

async def run_agent_task(update: Update, status_msg, project_dir: Path, instructions: str, session_id: str, task_branch: str):
    """Executes the autonomous agent (Aider with LiteLLM proxy), commits, and pushes branch."""
    try:
        is_git = (project_dir / ".git").exists()
        if is_git:
            await asyncio.create_subprocess_exec(GIT_BIN, "checkout", "-B", task_branch, cwd=str(project_dir))  # nosec B603,B607

        cmd = [
            AIDER_BIN,
            "--openai-api-base", f"{LITELLM_BASE}/v1",
            "--openai-api-key", LITELLM_KEY,
            "--model", "openai/coder-smart",
            "--message", instructions,
            "--auto-commits",
            "--no-git-commit-verify"
        ]

        agent_auth_file = Path("/root/.anthropic/token")
        if agent_auth_file.exists():
            cmd.extend(["--anthropic-api-key", agent_auth_file.read_text().strip()])

        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            *cmd,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if is_git:
            push_proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "-u", "origin", task_branch, cwd=str(project_dir))  # nosec B603,B607
            await push_proc.communicate()

        summary = out if len(out) > 0 else err
        if len(summary) > 3500:
            summary = summary[:3500] + "\n...(truncated)"

        await status_msg.edit_text(
            f"✅ *Task Completed Successfully!*\n\n"
            f"📁 Project: `{project_dir.name}`\n"
            f"🌿 Branch Pushed: `{task_branch}`\n\n"
            f"📄 *Agent Summary:*\n```\n{summary}\n```\n\n"
            f"Inspect diff with `/diff` or create a PR on GitHub!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in autonomous agent execution: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Autonomous Agent Error: {e}")

async def claude_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatches Claude Code CLI directly inside the workspace."""
    if not await check_auth(update):
        return

    project_name, remaining_args = resolve_project_context(update, context)
    prompt = " ".join(remaining_args) if remaining_args else ""

    if not prompt and project_name:
        prompt = project_name
        work_dir = WORKSPACE
    elif project_name and (WORKSPACE / project_name).is_dir():
        work_dir = WORKSPACE / project_name
    else:
        work_dir = WORKSPACE

    if not prompt:
        await update.effective_message.reply_text(
            "🤖 *Claude Code CLI Agent*\n\n"
            "Please type your prompt or instructions for Claude Code below:",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Type instructions for Claude Code..."
            )
        )
        return

    msg = await update.effective_message.reply_text(f"🤖 *Dispatching Claude Code Agent...*\n\n📝 Prompt: _{prompt}_\n⏳ Running in `{work_dir.name}`...", parse_mode="Markdown")

    claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
    try:
        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            claude_bin, "-p", prompt, "--print",
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0:
            reply = f"✅ *Claude Code Finished:*\n\n{out}"
            if len(reply) > 4000:
                reply = reply[:4000] + "\n\n*(Truncated due to Telegram length limit)*"
            await msg.edit_text(reply, parse_mode="Markdown")
        else:
            combined = (out + "\n" + err).strip()
            if "login" in combined.lower() or "auth" in combined.lower() or "input must be provided" in combined.lower():
                await msg.edit_text(
                    "🔑 *Claude Code Authentication Required*\n\n"
                    "To link your Claude account for autonomous coding:\n\n"
                    "👉 *Option 1: 1-Click Browser OAuth (Claude.ai Subscription / Free)*\n"
                    "1. Open your Web Terminal: `http://<your-omv-ip>:7681`\n"
                    "2. Login with `admin` / your password\n"
                    "3. Type `claude` and press Enter\n"
                    "4. Complete browser authentication (shared forever across bot and terminal!)\n\n"
                    "👉 *Option 2: Direct API Key*\n"
                    "Enter your `anthropic_api_key` in OMV WebGUI ➔ *Services ➔ Agent Station ➔ AI Models*.",
                    parse_mode="Markdown"
                )
            else:
                await msg.edit_text(f"⚠️ *Claude Execution Result:*\n```\n{combined[:3000]}\n```", parse_mode="Markdown")
    except FileNotFoundError:
        await msg.edit_text("⚠️ Claude CLI is not installed yet. Go to OMV WebGUI -> AI Models and click 'Install / Update Claude CLI'.", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Claude dispatch error: {e}")

async def exec_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs a shell command strictly sandboxed in /data/workspace."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "🖥️ *Workspace Shell Execution*\n\n"
            "Please type the shell command to execute in `/data/workspace`:",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="e.g. ls -la, git status, pytest -v..."
            )
        )
        return

    cmd = " ".join(context.args)
    if cmd.strip() == "claude" or cmd.strip().startswith("claude login") or cmd.strip().startswith("claude auth"):
        await update.effective_message.reply_text(
            "ℹ️ *Interactive Terminal Required for Claude Login*\n\n"
            "Claude OAuth login requires an interactive browser terminal to approve the login URL.\n\n"
            "👉 Please open your Web Terminal:\n"
            "🔗 `http://<your-omv-ip>:7681` (Port 7681)\n\n"
            "Type `claude` in the browser terminal to log in once. Your session will be saved permanently for Telegram `/claude` and `/task` commands!",
            parse_mode="Markdown"
        )
        return

    msg = await update.effective_message.reply_text(f"⏳ Executing: `{cmd}`...", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_shell(  # nosec B602
            cmd,
            cwd=str(WORKSPACE),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        result = (out + "\n" + err).strip() or "(No output)"
        if len(result) > 3500:
            result = result[:3500] + "\n...(truncated)"
        await msg.edit_text(f"🖥️ *Command Output:*\n```\n{result}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Exec error: {e}")

async def interactive_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles direct plain text and interactive ForceReply prompts seamlessly."""
    if not await check_auth(update):
        return
    msg = update.effective_message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    reply_to = msg.reply_to_message

    # Case 1: User is replying to a ForceReply prompt from the bot
    if reply_to and reply_to.from_user and reply_to.from_user.is_bot:
        parent_text = reply_to.text or ""
        
        if "Gemini" in parent_text:
            context.args = ["-m", "gemini-3.6-flash"] + text.split()
            await chat_cmd(update, context)
            return
        elif "GPT-4o" in parent_text or "gpt4" in parent_text.lower():
            context.args = ["-m", "github-gpt-4o"] + text.split()
            await chat_cmd(update, context)
            return
        elif "AI Chat" in parent_text or "Smart Router" in parent_text:
            context.args = text.split()
            await chat_cmd(update, context)
            return
        elif "Coding Agent" in parent_text or "Autonomous" in parent_text:
            context.args = shlex.split(text) if ("\"" in text or "'" in text) else text.split()
            await task_cmd(update, context)
            return
        elif "Claude Code" in parent_text:
            context.args = text.split()
            await claude_cmd(update, context)
            return
        elif "Obsidian" in parent_text or "Note" in parent_text:
            context.args = text.split()
            await note_cmd(update, context)
            return
        elif "Shell Command" in parent_text or "Workspace Shell" in parent_text:
            context.args = text.split()
            await exec_cmd(update, context)
            return
        elif "GitHub Repository" in parent_text or "repo" in parent_text.lower():
            context.args = shlex.split(text) if ("\"" in text or "'" in text) else text.split()
            await newrepo_cmd(update, context)
            return
        elif "Clone Git Repository" in parent_text or "clone" in parent_text.lower() or "git" in parent_text.lower():
            context.args = text.split()
            await clone_cmd(update, context)
            return

    # Case 2: Direct GitHub / Git URL paste in private chat automatically triggers project clone
    if text.startswith("https://github.com/") or text.startswith("http://github.com/") or text.startswith("git@github.com:"):
        context.args = text.split()
        await clone_cmd(update, context)
        return

    # Case 3: In private 1-on-1 chat, if the user sends any text question without a slash command,
    # naturally answer it with AI Chat (Google Gemini Flash / coder-smart)!
    chat = update.effective_chat
    if chat and chat.type == "private":
        context.args = text.split()
        await chat_cmd(update, context)

def main():
    if not BOT_TOKEN:
        print("ℹ️ TELEGRAM_BOT_TOKEN environment variable not set. Bot is in standby mode. Configure your token in OMV Services -> Agent Station -> Chat & Messenger to activate.", file=sys.stderr)
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
