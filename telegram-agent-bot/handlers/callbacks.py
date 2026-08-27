"""
Inline Keyboard Callback Query Router for Telegram Bot.
Handles interactive button taps for model selection, documentation tabs, and project actions.
"""

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.config import LITELLM_BASE, LITELLM_KEY, WORKSPACE

async def help_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard navigation for /help, /models, and /projects dashboards."""
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
