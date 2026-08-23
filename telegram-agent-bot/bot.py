#!/usr/bin/env python3
"""
Telegram Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8
Provides remote command execution, autonomous coding agent dispatch (Hermes/Aider/Claude Code),
Obsidian second-brain integration, and LiteLLM gateway telemetry.
"""

import os
import sys
import re
import shutil
import logging
import asyncio
import subprocess  # nosec B404
from pathlib import Path
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
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
LITELLM_KEY = os.environ.get("LITELLM_API_KEY", "sk-omv-master-key")  # nosec B105
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "/data/obsidian"))
WORKSPACE = Path(os.environ.get("WORKSPACE_PATH", "/data/workspace"))

# Git Provider & Identity Configuration
GIT_AUTHOR_NAME = os.environ.get("GIT_AUTHOR_NAME", "OMV AI Agent")
GIT_AUTHOR_EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "agent@omv-server.local")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
BITBUCKET_USER = os.environ.get("BITBUCKET_USERNAME", "")
BITBUCKET_PASS = os.environ.get("BITBUCKET_APP_PASSWORD", "")

GIT_BIN = shutil.which("git") or "/usr/bin/git"
TMUX_BIN = shutil.which("tmux") or "/usr/bin/tmux"
UPTIME_BIN = shutil.which("uptime") or "/usr/bin/uptime"
DF_BIN = shutil.which("df") or "/bin/df"
AIDER_BIN = shutil.which("aider") or "aider"

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
        if BITBUCKET_USER and BITBUCKET_PASS:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://{BITBUCKET_USER}:{BITBUCKET_PASS}@bitbucket.org/.insteadOf",
                "https://bitbucket.org/"
            ], check=True)
            logger.info("Configured automated git auth for Bitbucket.")

    except Exception as e:
        logger.warning(f"Could not configure global git credentials: {e}")

init_git_credentials()

# OpenAI Client pointing to local LiteLLM Proxy
ai_client = OpenAI(
    api_key=LITELLM_KEY,
    base_url=f"{LITELLM_BASE}/v1"
)

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
        "⚡ *Core Commands:*\n"
        "• `/task <project> <prompt>` - Run autonomous coding agent on git branch\n"
        "• `/chat <message>` - Ask questions using Gemini 3.7 / Claude 3.7\n"
        "• `/projects` - List all workspace repositories\n"
        "• `/clone <url> [name]` - Clone GitHub / GitLab / Bitbucket repo\n"
        "• `/pull <project>` - Pull latest changes from remote\n"
        "• `/push <project> [branch]` - Push commits to remote\n"
        "• `/branch <project> [name]` - List or switch git branch\n"
        "• `/diff <project>` - View git diff & status summary\n"
        "• `/vault` - Inspect Obsidian notes\n"
        "• `/note <Title> | <Content>` - Quick note to Obsidian\n"
        "• `/models` - Check available models & health\n"
        "• `/status` - Server CPU/RAM & active tmux sessions\n"
        "• `/help` - Show detailed documentation"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    text = (
        "📖 *Git & Agent Remote Control Handbook:*\n\n"
        "1️⃣ *Clone Repo:* `/clone https://github.com/user/my-repo`\n"
        "   - Works with GitHub, GitLab, Bitbucket (HTTPS or SSH)\n"
        "   - Automatically authenticates using your configured tokens\n\n"
        "2️⃣ *Autonomous Task:* `/task my-repo \"Add authentication middleware\"`\n"
        "   - Automatically cuts branch `agent/task-<timestamp>`\n"
        "   - Reads context & project specs from Obsidian vault\n"
        "   - Runs coding agent, runs tests & commits\n"
        "   - Automatically pushes branch to remote repository!\n\n"
        "3️⃣ *Git Management:*\n"
        "   - `/pull my-repo` - Rebase latest commits\n"
        "   - `/push my-repo` - Push local commits\n"
        "   - `/branch my-repo feature-x` - Switch/create branch\n"
        "   - `/diff my-repo` - Inspect current modifications\n\n"
        "4️⃣ *Direct Chat:* `/chat How do I optimize SQLite WAL in Go?`\n"
        "5️⃣ *Obsidian Memo:* `/note Topic | Content`"
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
        tmux_out = subprocess.check_output(  # nosec B603,B607
            [TMUX_BIN, "list-sessions"],
            stderr=subprocess.STDOUT,
            text=True
        ).strip()
    except Exception:
        tmux_out = "No active tmux sessions."

    # Check uptime & memory
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

async def clone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/clone <git-url> [custom-folder-name]`", parse_mode="Markdown")
        return

    raw_git_url = context.args[0].strip()
    git_url = sanitize_git_url(raw_git_url)
    if not git_url:
        await update.message.reply_text("❌ Invalid git URL format.", parse_mode="Markdown")
        return

    if len(context.args) > 1:
        folder_name = context.args[1].strip()
    else:
        folder_name = git_url.rstrip("/").split("/")[-1].replace(".git", "")

    target_dir = sanitize_project_path(WORKSPACE, folder_name)
    if not target_dir:
        await update.message.reply_text("❌ Invalid folder name.", parse_mode="Markdown")
        return

    if target_dir.exists():
        await update.message.reply_text(f"⚠️ Destination folder `{folder_name}` already exists in `/data/workspace`.", parse_mode="Markdown")
        return

    msg = await update.message.reply_text(f"⏳ Cloning `{git_url}` into `{folder_name}`...", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "clone", "--", git_url, str(target_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await msg.edit_text(f"✅ Successfully cloned `{folder_name}`!\n\nYou can now run:\n`/task {folder_name} \"your prompt\"`", parse_mode="Markdown")
        else:
            err = stderr.decode("utf-8", errors="replace")
            await msg.edit_text(f"❌ Git clone failed:\n```\n{err}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error during git clone: {e}")

async def pull_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/pull <project-folder-name>`", parse_mode="Markdown")
        return

    project_name = context.args[0]
    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.message.reply_text(f"❌ Not a valid git repository: `{project_name}`", parse_mode="Markdown")
        return

    msg = await update.message.reply_text(f"⏳ Pulling latest changes for `{project_name}`...", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "pull", "--rebase",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        await msg.edit_text(f"📥 *Git Pull Result for `{project_name}`:*\n```\n{out}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Git pull failed: {e}")

async def push_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/push <project-folder-name> [branch]`", parse_mode="Markdown")
        return

    project_name = context.args[0]
    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.message.reply_text(f"❌ Not a valid git repository: `{project_name}`", parse_mode="Markdown")
        return

    branch = "HEAD"
    if len(context.args) > 1:
        valid_branch = sanitize_branch_name(context.args[1])
        if not valid_branch:
            await update.message.reply_text("❌ Invalid branch name format.", parse_mode="Markdown")
            return
        branch = valid_branch

    msg = await update.message.reply_text(f"⏳ Pushing `{branch}` for `{project_name}` to remote...", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "push", "origin", "--", branch,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace") + "\n" + stderr.decode("utf-8", errors="replace")
        await msg.edit_text(f"🚀 *Git Push Result for `{project_name}`:*\n```\n{out.strip()}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Git push failed: {e}")

async def diff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/diff <project-folder-name>`", parse_mode="Markdown")
        return

    project_name = context.args[0]
    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.message.reply_text(f"❌ Not a valid git repository: `{project_name}`", parse_mode="Markdown")
        return

    try:
        # Get status and diff
        proc_status = await asyncio.create_subprocess_exec(GIT_BIN, "status", "-s", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
        proc_diff = await asyncio.create_subprocess_exec(GIT_BIN, "diff", "--stat", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
        out_status, _ = await proc_status.communicate()
        out_diff, _ = await proc_diff.communicate()

        status_text = out_status.decode("utf-8", errors="replace").strip() or "Working tree clean."
        diff_text = out_diff.decode("utf-8", errors="replace").strip() or "No uncommitted modifications."

        report = (
            f"📊 *Git Status & Diff for `{project_name}`:*\n\n"
            f"*Modified Files:*\n```\n{status_text}\n```\n\n"
            f"*Diff Summary:*\n```\n{diff_text}\n```"
        )
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to get git diff: {e}")

async def branch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/branch <project-name> [new-branch-to-create-or-checkout]`", parse_mode="Markdown")
        return

    project_name = context.args[0]
    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.message.reply_text(f"❌ Not a valid git repository: `{project_name}`", parse_mode="Markdown")
        return

    if len(context.args) == 1:
        # List branches
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "branch", "-a", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
        out, _ = await proc.communicate()
        await update.message.reply_text(f"🌿 *Branches for `{project_name}`:*\n```\n{out.decode('utf-8', errors='replace')}\n```", parse_mode="Markdown")
    else:
        # Checkout / create branch
        raw_branch = context.args[1].strip()
        new_branch = sanitize_branch_name(raw_branch)
        if not new_branch:
            await update.message.reply_text("❌ Invalid branch name format.", parse_mode="Markdown")
            return
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "checkout", "-B", new_branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await update.message.reply_text(f"✅ Switched to branch `{new_branch}` in `{project_name}`.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ Branch switch failed:\n```\n{stderr.decode('utf-8', errors='replace')}\n```", parse_mode="Markdown")

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/task <project-folder-name> <your instructions>`\n\n"
            "Example: `/task my-web-app Add dark mode toggle and unit tests`",
            parse_mode="Markdown"
        )
        return

    project_name = context.args[0]
    instructions = " ".join(context.args[1:])
    project_dir = sanitize_project_path(WORKSPACE, project_name)

    if not project_dir or not project_dir.exists():
        await update.message.reply_text(f"❌ Project directory `{project_name}` does not exist in `/data/workspace`.", parse_mode="Markdown")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"task_{timestamp}"
    task_branch = f"agent/{session_id}"

    msg = await update.message.reply_text(
        f"🚀 *Launching Autonomous Agent Task*\n\n"
        f"📁 Project: `{project_name}`\n"
        f"🌿 Branch: `{task_branch}`\n"
        f"🆔 Session: `{session_id}`\n"
        f"📝 Instruction: _{instructions}_\n\n"
        f"Agent is starting ReAct loop in background...",
        parse_mode="Markdown"
    )

    # Spawn Aider / Hermes agent in background asyncio task
    asyncio.create_task(run_agent_task(update, msg, project_dir, instructions, session_id, task_branch))

async def run_agent_task(update: Update, status_msg, project_dir: Path, instructions: str, session_id: str, task_branch: str):
    """Executes the autonomous agent (Aider with LiteLLM proxy), commits, and pushes branch."""
    try:
        # If git repo, checkout dedicated task branch
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

        logger.info(f"Executing agent task in {project_dir} with command: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(  # nosec B603,B607
            *cmd,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, _ = await process.communicate()
        agent_out = stdout.decode("utf-8", errors="replace")

        # Capture git diff after execution
        diff_summary = "No git changes recorded."
        push_status = ""
        if is_git:
            try:
                diff_proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
                    GIT_BIN, "diff", "main..." + task_branch, "--stat",
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                diff_out, _ = await diff_proc.communicate()
                diff_summary = diff_out.decode("utf-8", errors="replace").strip() or "Changes committed."

                # Automatically push task branch to remote origin
                push_proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
                    GIT_BIN, "push", "-u", "origin", task_branch,
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await push_proc.communicate()
                if push_proc.returncode == 0:
                    push_status = f"🚀 *Branch Pushed to Remote:* `{task_branch}`\n"
            except Exception as pe:
                logger.info(f"Remote push skipped: {pe}")

        # Save log entry to Obsidian
        try:
            obsidian_proj = OBSIDIAN_VAULT / "Projects" / project_dir.name
            obsidian_proj.mkdir(parents=True, exist_ok=True)
            log_file = obsidian_proj / "agent-log.md"
            log_entry = (
                f"\n## Task `{session_id}` - {datetime.now().isoformat()}\n"
                f"- **Branch:** `{task_branch}`\n"
                f"- **Instruction:** {instructions}\n"
                f"- **Diff Summary:**\n```\n{diff_summary}\n```\n"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as oe:
            logger.warning(f"Could not write log to Obsidian: {oe}")

        result_text = (
            f"✅ *Agent Task Completed!* (`{session_id}`)\n\n"
            f"📁 *Project:* `{project_dir.name}`\n"
            f"🌿 *Branch:* `{task_branch}`\n"
            f"{push_status}"
            f"📊 *Git Changes:*\n```\n{diff_summary[:1000]}\n```\n\n"
            f"🔍 *Agent Log Excerpt:*\n```\n{agent_out[-1500:] if agent_out else 'Done.'}\n```"
        )
        await status_msg.edit_text(result_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error during agent run: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Task `{session_id}` failed:\n`{str(e)}`", parse_mode="Markdown")

async def claude_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes Claude Code CLI in non-interactive/headless mode inside the workspace."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/claude <your prompt or coding request>`\n\nExample: `/claude Create a FastAPI healthcheck endpoint in workspace`", parse_mode="Markdown")
        return

    prompt = " ".join(context.args)
    msg = await update.message.reply_text(f"🤖 *Dispatching Claude Code Agent...*\n\n📝 Prompt: _{prompt}_\n⏳ Running in sandboxed workspace...", parse_mode="Markdown")

    claude_bin = shutil.which("claude") or "/usr/local/bin/claude"
    try:
        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            claude_bin, "-p", prompt, "--print",
            cwd=str(WORKSPACE),
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
            if "login" in combined.lower() or "auth" in combined.lower():
                await msg.edit_text(
                    "🔑 *Claude.ai Authentication Required*\n\n"
                    "Please open your Web Terminal (`:7681`) or run `/exec claude` once to complete browser OAuth login with your `claude.ai` subscription!",
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
        await update.message.reply_text("Usage: `/exec <shell-command>`\n\nExample: `/exec ls -la`", parse_mode="Markdown")
        return

    cmd = " ".join(context.args)
    msg = await update.message.reply_text(f"⏳ Executing: `{cmd}`...", parse_mode="Markdown")
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
    app.add_handler(CommandHandler("clone", clone_cmd))
    app.add_handler(CommandHandler("pull", pull_cmd))
    app.add_handler(CommandHandler("push", push_cmd))
    app.add_handler(CommandHandler("branch", branch_cmd))
    app.add_handler(CommandHandler("diff", diff_cmd))
    app.add_handler(CommandHandler("vault", vault_cmd))
    app.add_handler(CommandHandler("note", note_cmd))
    app.add_handler(CommandHandler("chat", chat_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("claude", claude_cmd))
    app.add_handler(CommandHandler("exec", exec_cmd))

    print("🤖 Telegram Agent Relay Bot starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
