"""
AI Chat, Model Querying, and LiteLLM Gateway Telemetry Handlers.
Routes prompts through LiteLLM proxy with fallback chains and interactive dashboards.
"""

import httpx
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.config import LITELLM_BASE, LITELLM_KEY, logger
from core.security import check_auth
from core.git_auth import ai_client

async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queries AI model with support for custom model flags or smart routers."""
    if not await check_auth(update):
        return

    selected_model = "coder-smart"
    prompt_args = list(context.args) if context.args else []

    if prompt_args and prompt_args[0] in ("-m", "--model") and len(prompt_args) > 2:
        selected_model = prompt_args[1]
        prompt_args = prompt_args[2:]

    if not prompt_args:
        await update.effective_message.reply_text(
            "💬 *OMV AI Smart Router*\n\n"
            "Ask any question or specify a model:\n"
            "• `/chat <message>` — Routed to smart multi-tier model\n"
            "• `/gemini <prompt>` — Direct Google Gemini 3.6 Flash\n"
            "• `/gpt4 <prompt>` — Direct GitHub Models GPT-4o\n"
            "• `/chat -m reasoning-heavy <prompt>` — Deep reasoning mode",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Ask AI anything..."
            )
        )
        return

    prompt = " ".join(prompt_args).strip()
    msg = await update.effective_message.reply_text(f"⏳ Querying `{selected_model}`...", parse_mode="Markdown")

    try:
        response = await ai_client.chat.completions.create(
            model=selected_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the OpenMediaVault AI Assistant running on a self-hosted server. "
                        "Provide concise, practical, and highly accurate answers with bash/python examples when appropriate."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content or "No response received."
        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n*(Response truncated due to Telegram message length limits)*"

        await msg.edit_text(answer)
    except Exception as e:
        logger.error(f"LiteLLM chat error: {e}")
        err_msg = str(e)
        if "AuthenticationError" in err_msg or "invalid_api_key" in err_msg or "401" in err_msg:
            hint = (
                "⚠️ *AI Authentication Error*\n\n"
                "Please verify your API keys in OMV WebGUI ➔ **Services ➔ Agent Station ➔ AI Providers**."
            )
        elif "no active route" in err_msg.lower() or "500" in err_msg:
            hint = (
                "⚠️ *No active AI route configured*\n\n"
                "Please ensure at least one valid API Key (e.g. Gemini API Key or GitHub Token) is configured in OMV WebGUI ➔ Agent Station."
            )
        else:
            hint = f"❌ *AI Query Failed:*\n```\n{err_msg[:400]}\n```"

        await msg.edit_text(hint, parse_mode="Markdown")

async def gemini_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct shortcut for Google Gemini 3.6 Flash."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "⚡ *Google Gemini 3.6 Flash (Fast Tier)*\n\nPlease type your question or coding prompt below:",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True, input_field_placeholder="Type your question for Gemini...")
        )
        return
    context.args = ["-m", "gemini-3.6-flash"] + list(context.args)
    await chat_cmd(update, context)

async def gpt4_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Direct shortcut for GitHub Models GPT-4o."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "🤖 *GitHub Models GPT-4o*\n\nPlease type your question or coding prompt below:",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True, input_field_placeholder="Type your question for GPT-4o...")
        )
        return
    context.args = ["-m", "github-gpt-4o"] + list(context.args)
    await chat_cmd(update, context)

async def modelhelp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides an in-depth guide on available AI models, strengths, speed, and usage tips."""
    if not await check_auth(update):
        return

    help_text = (
        "📖 *OMV Agent Station — AI Models Guide*\n\n"
        "Here is the breakdown of available models and router targets:\n\n"
        "⚡ *`gemini-3.6-flash`* (Google Gemini 2.0 Flash)\n"
        "• *Context:* 1,048,576 tokens\n"
        "• *Speed:* Ultra fast (~80 tokens/sec)\n"
        "• *Best for:* Quick questions, code explanation, regex, and large repository scans.\n"
        "• *Shortcut:* `/gemini <question>`\n\n"
        "🚀 *`coder-smart`* (Multi-Tier Router)\n"
        "• *Primary:* Gemini 2.0 Flash ➔ Claude 3.7 Sonnet ➔ DeepSeek R1\n"
        "• *Best for:* Autonomous coding agent loops, bug fixing, test suite generation.\n"
        "• *Command:* `/chat <question>` or `/task <project> <prompt>`\n\n"
        "🧠 *`reasoning-heavy`* (Deep Chain-of-Thought)\n"
        "• *Primary:* DeepSeek-R1 ➔ Gemini 2.5 Pro\n"
        "• *Best for:* Math, system architecture, database optimization, algorithms.\n"
        "• *Command:* `/chat -m reasoning-heavy <prompt>`\n\n"
        "🤖 *`github-gpt-4o`* (GitHub Marketplace)\n"
        "• *Context:* 128,000 tokens\n"
        "• *Best for:* General multi-step logic & code review.\n"
        "• *Shortcut:* `/gpt4 <question>`\n\n"
        "🛠️ *`claude`* (Claude Code CLI)\n"
        "• *Best for:* Multi-file workspace edits & automated git workflows.\n"
        "• *Command:* `/claude <prompt>`"
    )

    keyboard = [
        [
            InlineKeyboardButton("⚡ Ask Gemini", switch_inline_query_current_chat="/gemini "),
            InlineKeyboardButton("🤖 Ask GPT-4o", switch_inline_query_current_chat="/gpt4 "),
        ],
        [
            InlineKeyboardButton("📋 Check Active Endpoints", callback_data="btn_models"),
        ]
    ]

    await update.effective_message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def models_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queries LiteLLM Gateway for configured models and presents interactive action buttons."""
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
                    model_lines = "\n".join([f"• `{m}`" for m in models])
                    text = (
                        f"🤖 *Active LiteLLM Gateway Models ({len(models)}):*\n\n"
                        f"{model_lines}\n\n"
                        f"⚡ *Quick Usage:*\n"
                        f"• `/gemini <prompt>` — Fast Gemini 3.6 Flash\n"
                        f"• `/gpt4 <prompt>` — GitHub GPT-4o\n"
                        f"• `/chat -m <model> <prompt>` — Specific model\n"
                        f"• `/modelhelp` — Detailed capabilities guide"
                    )
                    keyboard = [
                        [
                            InlineKeyboardButton("⚡ Ask Gemini", switch_inline_query_current_chat="/gemini "),
                            InlineKeyboardButton("🤖 Ask GPT-4o", switch_inline_query_current_chat="/gpt4 "),
                        ],
                        [
                            InlineKeyboardButton("📖 Model Guide & Tips", callback_data="btn_modelhelp"),
                        ]
                    ]
                    await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                    return

            await msg.edit_text(
                "ℹ️ *Active Gateway Configuration:*\n\n"
                "• `coder-smart` (Google Gemini 3.6 Flash / Claude 3.7 / DeepSeek-R1)\n"
                "• `coder-fast` (Google Gemini 3.6 Flash)\n"
                "• `reasoning-heavy` (DeepSeek-R1 / Gemini Pro)\n"
                "• `github-gpt-4o` (GitHub Models GPT-4o)\n"
                "• `claude` (Anthropic Claude Code CLI)",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Failed to query LiteLLM models: {e}")
        await msg.edit_text(
            f"ℹ️ *Default Configured AI Routers:*\n\n"
            f"• `coder-smart` — Auto-fallback coding chain\n"
            f"• `gemini-3.6-flash` — High speed Gemini Flash\n"
            f"• `github-gpt-4o` — GitHub Models GPT-4o\n"
            f"• `reasoning-heavy` — Deep logic & math\n\n"
            f"*(LiteLLM Gateway starting up or endpoint unreachable: {e})*",
            parse_mode="Markdown"
        )
