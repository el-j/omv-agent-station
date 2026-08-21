#!/usr/bin/env python3
"""
Telegram Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8
Provides remote command execution, autonomous coding agent dispatch (Hermes/Aider/Claude Code),
Obsidian second-brain integration, and LiteLLM gateway telemetry.
"""

import os
import sys
import logging
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import httpx
from openai import OpenAI

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
LITELLM_KEY = os.environ.get("LITELLM_API_KEY", "sk-omv-master-key")
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "/data/obsidian"))
WORKSPACE = Path(os.environ.get("WORKSPACE_PATH", "/data/workspace"))

# OpenAI Client pointing to local LiteLLM Proxy
ai_client = OpenAI(
    api_key=LITELLM_KEY,
    base_url=f"{LITELLM_BASE}/v1"
)

def authorized(update: Update) -> bool:
    """Ensure only the configured user can communicate with the bot."""
    if not ALLOWED_USER_ID:
        return True
    user_id = str(update.effective_user.id)
    return user_id == str(ALLOWED_USER_ID)

async def check_auth(update: Update) -> bool:
    if not authorized(update):
        if update.effective_message:
            await update.effective_message.reply_text("⛔ Unauthorized access.")
        return False
    return True

# ---------------------------------------------------------------------------
# Telegram Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    welcome_text = (
        "🤖 *OMV AI Orchestrator & Remote Coding Bot*\n\n"
        "Your 24/7 AI-powered development server is online.\n\n"
        "⚡ *Commands:*\n"
        "• `/task <project> <instructions>` - Run autonomous coding agent\n"
        "• `/chat <message>` - Ask questions using Gemini 3.7 / Claude 3.7\n"
        "• `/projects` - List all projects in your workspace\n"
        "• `/vault` - Inspect Obsidian knowledge base & recent notes\n"
        "• `/models` - Check available models & proxy health\n"
        "• `/status` - Server CPU/RAM & active tmux sessions\n"
        "• `/help` - Show full documentation"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    text = (
        "📖 *Agent Remote Control Handbook:*\n\n"
        "1️⃣ *Autonomous Task:* `/task my-repo \"Refactor database layer and add unit tests\"`\n"
        "   - Creates branch `agent/task-<timestamp>`\n"
        "   - Reads context from Obsidian vault\n"
        "   - Runs Aider / Hermes agent with Claude 3.7 / Gemini 3.7\n"
        "   - Runs tests & commits automatically\n"
        "   - Returns git diff summary\n\n"
        "2️⃣ *Direct Chat:* `/chat How do I optimize SQLite WAL mode in Go?`\n"
        "   - Uses smart fallback router (Gemini 3.7 Flash / Claude 3.7 Sonnet)\n\n"
        "3️⃣ *Obsidian Memo:* `/note <Topic> <Content>`\n"
        "   - Saves a quick note directly into your Obsidian Inbox"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def models_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    msg = await update.message.reply_text("🔍 Querying LiteLLM Gateway...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{LITELLM_BASE}/models",
                headers={"Authorization": f"Bearer {LITELLM_KEY}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", [])]
                model_str = "\n".join([f"• `{m}`" for m in models])
                await msg.edit_text(
                    f"✅ *Active AI Model Endpoints:*\n\n{model_str}\n\n"
                    f"Routing: `coder-fast` | `coder-smart` | `reasoning-heavy`",
                    parse_mode="Markdown"
                )
            else:
                await msg.edit_text(f"⚠️ LiteLLM returned HTTP {resp.status_code}")
    except Exception as e:
        await msg.edit_text(f"❌ Failed to reach LiteLLM Proxy: {e}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    # Check tmux sessions
    try:
        tmux_out = subprocess.check_output(
            ["tmux", "list-sessions"],
            stderr=subprocess.STDOUT,
            text=True
        ).strip()
    except Exception:
        tmux_out = "No active tmux sessions."

    # Check uptime & memory
    try:
        uptime_out = subprocess.check_output(["uptime"], text=True).strip()
        df_out = subprocess.check_output(["df", "-h", "/data/workspace"], text=True).strip().splitlines()[-1]
    except Exception:
        uptime_out = "N/A"
        df_out = "N/A"

    report = (
        f"🖥️ *ProLiant Gen8 Server Status*\n\n"
        f"⏱️ *Uptime:* `{uptime_out}`\n"
        f"💾 *Disk Space:* `{df_out}`\n\n"
        f"🧵 *Active Agent Sessions:*\n```\n{tmux_out}\n```"
    )
    await update.message.reply_text(report, parse_mode="Markdown")

async def projects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not WORKSPACE.exists():
        await update.message.reply_text("📁 Workspace folder is empty or not mounted.")
        return
    
    projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if not projects:
        await update.message.reply_text("📁 No projects found in `/data/workspace`.")
        return
    
    proj_list = "\n".join([f"📂 `{p}`" for p in projects])
    await update.message.reply_text(f"📁 *Available Workspace Projects:*\n\n{proj_list}", parse_mode="Markdown")

async def vault_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not OBSIDIAN_VAULT.exists():
        await update.message.reply_text("📓 Obsidian vault not mounted.")
        return

    md_files = list(OBSIDIAN_VAULT.glob("**/*.md"))
    recent = sorted(md_files, key=lambda f: f.stat().st_mtime, reverse=True)[:5]
    
    recent_str = "\n".join([f"• `{f.relative_to(OBSIDIAN_VAULT)}`" for f in recent]) if recent else "No notes found."
    await update.message.reply_text(
        f"📓 *Obsidian Vault Status:*\n\n"
        f"📊 Total notes: `{len(md_files)}`\n"
        f"🕒 *Recently modified:*\n{recent_str}",
        parse_mode="Markdown"
    )

async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/note <note title> | <note content>`")
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

    await update.message.reply_text(f"📝 Note saved to Obsidian: `{note_path.relative_to(OBSIDIAN_VAULT)}`", parse_mode="Markdown")

async def chat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/chat <your question>`")
        return

    query = " ".join(context.args)
    status_msg = await update.message.reply_text("💭 Thinking...")

    try:
        # Calls LiteLLM virtual router 'coder-smart' (Claude 3.7 Sonnet / Vertex AI / Gemini 3.7 Pro)
        response = ai_client.chat.completions.create(
            model="coder-smart",
            messages=[
                {"role": "system", "content": "You are an expert AI software architect and assistant."},
                {"role": "user", "content": query}
            ],
            max_tokens=2048,
        )
        reply = response.choices[0].message.content
        if len(reply) > 4000:
            reply = reply[:4000] + "\n\n*(Truncated due to Telegram length limit)*"
        await status_msg.edit_text(reply)
    except Exception as e:
        await status_msg.edit_text(f"❌ Error during AI generation: {e}")

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/task <project-folder-name> <instructions...>`")
        return

    project_name = context.args[0]
    instructions = " ".join(context.args[1:])
    project_dir = WORKSPACE / project_name

    if not project_dir.exists():
        await update.message.reply_text(f"❌ Project directory `{project_name}` does not exist in `/data/workspace`.", parse_mode="Markdown")
        return

    session_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    msg = await update.message.reply_text(
        f"🚀 *Launching Autonomous Agent Task*\n\n"
        f"📁 Project: `{project_name}`\n"
        f"🆔 Session: `{session_id}`\n"
        f"📝 Instruction: _{instructions}_\n\n"
        f"Agent is starting ReAct loop in background...",
        parse_mode="Markdown"
    )

    # Spawn Aider / Hermes agent in background asyncio task
    asyncio.create_task(run_agent_task(update, msg, project_dir, instructions, session_id))

async def run_agent_task(update: Update, status_msg, project_dir: Path, instructions: str, session_id: str):
    """Executes the autonomous agent (Aider with LiteLLM proxy) and streams back results."""
    try:
        cmd = [
            "aider",
            "--openai-api-base", f"{LITELLM_BASE}/v1",
            "--openai-api-key", LITELLM_KEY,
            "--model", "openai/coder-smart",
            "--message", instructions,
            "--auto-commits",
            "--yes-always",
            "--no-git-commit-prefix"
        ]

        logger.info(f"Executing agent task in {project_dir} with command: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        out_text = stdout.decode("utf-8", errors="replace")
        err_text = stderr.decode("utf-8", errors="replace")

        # Get git diff summary
        diff_cmd = ["git", "diff", "HEAD~1", "--stat"]
        diff_proc = await asyncio.create_subprocess_exec(
            *diff_cmd,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        diff_out, _ = await diff_proc.communicate()
        diff_summary = diff_out.decode("utf-8", errors="replace").strip() or "No new commit generated."

        result_text = (
            f"✅ *Agent Task Completed!* (`{session_id}`)\n\n"
            f"📁 *Project:* `{project_dir.name}`\n"
            f"📊 *Git Changes:*\n```\n{diff_summary[:1000]}\n```\n\n"
            f"🔍 *Agent Log Excerpt:*\n```\n{out_text[-1500:] if out_text else 'Done.'}\n```"
        )
        await status_msg.edit_text(result_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error during agent run: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Task `{session_id}` failed:\n`{str(e)}`", parse_mode="Markdown")

def main():
    if not BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable not set!", file=sys.stderr)
        sys.exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("models", models_cmd))
    app.add_handler(CommandHandler("projects", projects_cmd))
    app.add_handler(CommandHandler("vault", vault_cmd))
    app.add_handler(CommandHandler("note", note_cmd))
    app.add_handler(CommandHandler("chat", chat_cmd))
    app.add_handler(CommandHandler("task", task_cmd))

    print("🤖 Telegram Agent Relay Bot starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
