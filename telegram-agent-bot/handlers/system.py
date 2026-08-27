"""
System Control, Telemetry, Shell Execution, and Autonomous Agent Runner Handlers.
Implements /start, /help, /status, /exec, /task, and /claude CLI operations.
"""

import asyncio
import subprocess  # nosec B404
import shutil
from datetime import datetime
from pathlib import Path
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.config import (
    WORKSPACE,
    TMUX_BIN,
    UPTIME_BIN,
    DF_BIN,
    AIDER_BIN,
    GIT_BIN,
    LITELLM_BASE,
    LITELLM_KEY,
    logger,
)
from core.security import check_auth, sanitize_project_path
from core import task_registry
from .topics import resolve_project_context, get_bound_project

def _chat_scope(update: Update) -> tuple[int, int | None]:
    """Returns the (chat_id, thread_id) scope key used to track this chat's active task."""
    chat_id = update.effective_chat.id if update.effective_chat else 0
    thread_id = update.effective_message.message_thread_id if update.effective_message else None
    return chat_id, thread_id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and presents available core capabilities."""
    if not await check_auth(update):
        return
    welcome_text = (
        "🤖 *OMV AI Agent Station — Remote Dev & Orchestrator*\n\n"
        "Your 24/7 AI-powered development server is online.\n\n"
        "⚡ *Core Commands:*\n"
        "• `/task [project] <prompt>` — Run autonomous coding agent on branch\n"
        "• `/chat <message>` — Ask questions via Gemini 3.7 / Claude 3.7 router\n"
        "• `/claude <prompt>` — Execute Claude Code CLI in sandboxed container\n"
        "• `/cancel` — Stop the currently running task/claude/exec command\n"
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

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays interactive multi-category help handbook."""
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
        "   • `/exec <cmd>` — Run sandboxed bash command in workspace\n"
        "   • `/cancel` — Stop the task/claude/exec command currently running here\n\n"
        "3️⃣ *Create / Clone Repositories:*\n"
        "   • `/newrepo my-api \"FastAPI backend service\"` — Creates remote GitHub repo + local workspace + Topic!\n"
        "   • `/clone https://github.com/user/repo` — Clones any repo with PAT auth\n"
        "   • Send any file/photo to upload it into the bound project's repo — caption sets the path (e.g. `docs/notes.md`), always pushed to a new `upload/<timestamp>` branch for review\n\n"
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

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides real-time system metrics, uptime, disk space, and active tmux sessions."""
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

    try:
        meminfo = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                meminfo[key] = int(rest.strip().split()[0])
        total_mb = meminfo["MemTotal"] // 1024
        avail_mb = meminfo.get("MemAvailable", meminfo["MemTotal"]) // 1024
        used_mb = max(0, total_mb - avail_mb)
        pct = round((used_mb / total_mb) * 100) if total_mb else 0
        ram_out = f"{used_mb} MB used of {total_mb} MB ({pct}%)"
    except Exception:
        ram_out = "N/A"

    report = (
        f"🖥️ *OMV Server Status*\n\n"
        f"⏱️ *Uptime:* `{uptime_out}`\n"
        f"🧠 *RAM:* `{ram_out}`\n"
        f"💾 *Disk Space:* `{df_out}`\n\n"
        f"🧵 *Active Agent Sessions:*\n```\n{tmux_out}\n```"
    )
    await update.effective_message.reply_text(report, parse_mode="Markdown")

async def exec_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes a shell command inside the workspace directory."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: `/exec <shell-command>`\n\nExample: `/exec ls -la`",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="ls -la, git status, pytest..."
            )
        )
        return

    chat_id, thread_id = _chat_scope(update)
    if task_registry.get(chat_id, thread_id):
        await update.effective_message.reply_text(
            "⚠️ Another task is already running here. Use `/cancel` to stop it first.",
            parse_mode="Markdown"
        )
        return

    cmd = " ".join(context.args)
    msg = await update.effective_message.reply_text(f"⏳ Executing: `{cmd}`...", parse_mode="Markdown")
    t = asyncio.create_task(run_exec_task(chat_id, thread_id, msg, cmd))
    task_registry.start(chat_id, thread_id, label=f"exec: {cmd}", asyncio_task=t)

async def run_exec_task(chat_id: int, thread_id: int | None, status_msg, cmd: str):
    """Runs a shell command in the background so it never blocks the bot's update loop."""
    try:
        proc = await asyncio.create_subprocess_shell(  # nosec B602
            cmd,
            cwd=str(WORKSPACE),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        task_registry.attach_proc(chat_id, thread_id, proc)
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        result = (out + "\n" + err).strip() or "(No output)"
        if len(result) > 3500:
            result = result[:3500] + "\n...(truncated)"
        await status_msg.edit_text(f"🖥️ *Command Output:*\n```\n{result}\n```", parse_mode="Markdown")
    except asyncio.CancelledError:
        await status_msg.edit_text(f"🛑 *Cancelled:* `{cmd}`", parse_mode="Markdown")
        raise
    except Exception as e:
        await status_msg.edit_text(f"❌ Exec error: {e}")
    finally:
        task_registry.finish(chat_id, thread_id)

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatches autonomous coding agent on a project branch."""
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

    chat_id, thread_id = _chat_scope(update)
    if task_registry.get(chat_id, thread_id):
        await update.effective_message.reply_text(
            "⚠️ Another task is already running here. Use `/cancel` to stop it first.",
            parse_mode="Markdown"
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

    t = asyncio.create_task(run_agent_task(chat_id, thread_id, msg, project_dir, instructions, session_id, task_branch))
    task_registry.start(chat_id, thread_id, label=f"task: {instructions}", asyncio_task=t)

async def run_agent_task(chat_id: int, thread_id: int | None, status_msg, project_dir: Path, instructions: str, session_id: str, task_branch: str):
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
        task_registry.attach_proc(chat_id, thread_id, proc)
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
    except asyncio.CancelledError:
        await status_msg.edit_text(
            f"🛑 *Task Cancelled*\n\n📁 Project: `{project_dir.name}`\n🌿 Branch: `{task_branch}`",
            parse_mode="Markdown"
        )
        raise
    except Exception as e:
        logger.error(f"Error in autonomous agent execution: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Autonomous Agent Error: {e}")
    finally:
        task_registry.finish(chat_id, thread_id)

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

    chat_id, thread_id = _chat_scope(update)
    if task_registry.get(chat_id, thread_id):
        await update.effective_message.reply_text(
            "⚠️ Another task is already running here. Use `/cancel` to stop it first.",
            parse_mode="Markdown"
        )
        return

    msg = await update.effective_message.reply_text(f"🤖 *Dispatching Claude Code Agent...*\n\n📝 Prompt: _{prompt}_\n⏳ Running in `{work_dir.name}`...", parse_mode="Markdown")
    t = asyncio.create_task(run_claude_task(chat_id, thread_id, msg, work_dir, prompt))
    task_registry.start(chat_id, thread_id, label=f"claude: {prompt}", asyncio_task=t)

async def run_claude_task(chat_id: int, thread_id: int | None, status_msg, work_dir: Path, prompt: str):
    """Runs the Claude Code CLI in the background so it never blocks the bot's update loop."""
    claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
    try:
        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            claude_bin, "-p", prompt, "--print",
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        task_registry.attach_proc(chat_id, thread_id, proc)
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0:
            reply = f"✅ *Claude Code Finished:*\n\n{out}"
        else:
            reply = f"⚠️ *Claude Code Output:*\n\n{out}\n\n*Error:*\n{err}"

        if len(reply) > 4000:
            reply = reply[:4000] + "\n...(truncated)"
        await status_msg.edit_text(reply)
    except asyncio.CancelledError:
        await status_msg.edit_text(f"🛑 *Claude Code Cancelled*\n\n📝 Prompt: _{prompt}_", parse_mode="Markdown")
        raise
    except FileNotFoundError:
        await status_msg.edit_text(
            "⚠️ Claude Code CLI is not initialized on the server.\n\n"
            "👉 Please open your Web Terminal:\n"
            "🔗 `http://<your-omv-ip>:7681` (Port 7681)\n\n"
            "Type `claude` in the browser terminal to log in once. Your session will be saved permanently for Telegram `/claude` and `/task` commands!",
            parse_mode="Markdown"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Error running Claude Code: {e}")
    finally:
        task_registry.finish(chat_id, thread_id)

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the currently running /task, /claude, or /exec command in this chat/topic."""
    if not await check_auth(update):
        return

    chat_id, thread_id = _chat_scope(update)
    label = await task_registry.cancel(chat_id, thread_id)

    if label is None:
        await update.effective_message.reply_text("ℹ️ Nothing is currently running here to cancel.")
        return

    await update.effective_message.reply_text(f"🛑 Cancelling: `{label}`...", parse_mode="Markdown")
