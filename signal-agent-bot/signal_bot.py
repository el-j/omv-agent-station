#!/usr/bin/env python3
"""
Signal Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8
Provides end-to-end encrypted remote command execution, autonomous coding agent dispatch (Aider/Claude Code),
Git repository synchronization, Obsidian second-brain integration, and LiteLLM gateway telemetry over Signal.
"""

import os
import sys
import json
import logging
import asyncio
import subprocess  # nosec B404
from pathlib import Path
from datetime import datetime
import httpx
import websockets
from openai import OpenAI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("SignalAgentBot")

# Environment Configuration
SIGNAL_API_URL = os.environ.get("SIGNAL_CLI_URL", "http://signal-cli:8080")
SIGNAL_PHONE_NUMBER = os.environ.get("SIGNAL_PHONE_NUMBER", "")
SIGNAL_ALLOWED_NUMBER = os.environ.get("SIGNAL_ALLOWED_PHONE_NUMBER", "")
LITELLM_BASE = os.environ.get("LITELLM_API_BASE", "http://litellm:4000")
LITELLM_KEY = os.environ.get("LITELLM_API_KEY", "sk-omv-master-key")
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "/data/obsidian"))
WORKSPACE = Path(os.environ.get("WORKSPACE_PATH", "/data/workspace"))

# Git Configuration
GIT_AUTHOR_NAME = os.environ.get("GIT_AUTHOR_NAME", "OMV AI Agent")
GIT_AUTHOR_EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "agent@omv-box.local")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
BITBUCKET_USER = os.environ.get("BITBUCKET_USERNAME", "")
BITBUCKET_PASS = os.environ.get("BITBUCKET_APP_PASSWORD", "")

import shutil

GIT_BIN = shutil.which("git") or "/usr/bin/git"
TMUX_BIN = shutil.which("tmux") or "/usr/bin/tmux"
UPTIME_BIN = shutil.which("uptime") or "/usr/bin/uptime"
DF_BIN = shutil.which("df") or "/bin/df"
AIDER_BIN = shutil.which("aider") or "aider"

def init_git_credentials():
    try:
        subprocess.run([GIT_BIN, "config", "--global", "user.name", GIT_AUTHOR_NAME], check=True)  # nosec B603,B607
        subprocess.run([GIT_BIN, "config", "--global", "user.email", GIT_AUTHOR_EMAIL], check=True)  # nosec B603,B607
        subprocess.run([GIT_BIN, "config", "--global", "init.defaultBranch", "main"], check=True)  # nosec B603,B607

        if GITHUB_TOKEN:
            subprocess.run([
                GIT_BIN, "config", "--global",
                f"url.https://x-access-token:{GITHUB_TOKEN}@github.com/.insteadOf",
                "https://github.com/"
            ], check=True)  # nosec B603,B607
        if GITLAB_TOKEN:
            subprocess.run([
                GIT_BIN, "config", "--global",
                f"url.https://oauth2:{GITLAB_TOKEN}@gitlab.com/.insteadOf",
                "https://gitlab.com/"
            ], check=True)  # nosec B603,B607
        if BITBUCKET_USER and BITBUCKET_PASS:
            subprocess.run([
                GIT_BIN, "config", "--global",
                f"url.https://{BITBUCKET_USER}:{BITBUCKET_PASS}@bitbucket.org/.insteadOf",
                "https://bitbucket.org/"
            ], check=True)  # nosec B603,B607
    except Exception as e:
        logger.warning(f"Could not configure git credentials: {e}")

import re

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

ai_client = OpenAI(
    api_key=LITELLM_KEY,
    base_url=f"{LITELLM_BASE}/v1"
)

async def send_signal_message(recipient: str, text: str):
    """Sends an end-to-end encrypted message via signal-cli-rest-api."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            payload = {
                "message": text,
                "number": SIGNAL_PHONE_NUMBER,
                "recipients": [recipient]
            }
            resp = await client.post(f"{SIGNAL_API_URL}/v2/send", json=payload)
            if resp.status_code not in (200, 201):
                logger.error(f"Failed to send Signal message: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Error sending Signal message: {e}")

async def handle_command(sender: str, message_text: str):
    """Parses and executes agent bot commands received from Signal."""
    parts = message_text.strip().split()
    if not parts:
        return

    cmd = parts[0].lower()
    args = parts[1:]

    logger.info(f"Received command '{cmd}' from {sender}")

    if cmd in ("/start", "/help"):
        help_text = (
            "🤖 OMV AI Orchestrator (Signal E2EE Relay)\n\n"
            "Commands:\n"
            "• /task <project> <instructions> - Run autonomous coding loop on git branch\n"
            "• /chat <message> - Ask architecture & coding questions (Claude 3.7 / Gemini 3.7)\n"
            "• /clone <url> [name] - Clone GitHub / GitLab / Bitbucket repo\n"
            "• /pull <project> - Pull latest changes from remote\n"
            "• /push <project> [branch] - Push local commits to remote\n"
            "• /branch <project> [name] - List or switch branch\n"
            "• /diff <project> - Inspect git changes & modified files\n"
            "• /projects - List all projects in workspace\n"
            "• /vault - View recent Obsidian notes\n"
            "• /note <title> | <content> - Save note to Obsidian Inbox\n"
            "• /models - Check active LiteLLM AI endpoints\n"
            "• /status - Server CPU/RAM & active tmux sessions"
        )
        await send_signal_message(sender, help_text)

    elif cmd == "/status":
        try:
            tmux_out = subprocess.check_output([TMUX_BIN, "list-sessions"], stderr=subprocess.STDOUT, text=True).strip()  # nosec B603,B607
        except Exception:
            tmux_out = "No active tmux sessions."
        try:
            uptime_out = subprocess.check_output([UPTIME_BIN], text=True).strip()  # nosec B603,B607
            df_out = subprocess.check_output([DF_BIN, "-h", "/data/workspace"], text=True).strip().splitlines()[-1]  # nosec B603,B607
        except Exception:
            uptime_out = "N/A"
            df_out = "N/A"

        status_text = (
            f"🖥️ OMV Server Status\n\n"
            f"⏱️ Uptime: {uptime_out}\n"
            f"💾 Disk: {df_out}\n\n"
            f"🧵 Active Agent Sessions:\n{tmux_out}"
        )
        await send_signal_message(sender, status_text)

    elif cmd == "/models":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{LITELLM_BASE}/models", headers={"Authorization": f"Bearer {LITELLM_KEY}"})
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("id") for m in data.get("data", [])]
                    model_str = "\n".join([f"• {m}" for m in models])
                    await send_signal_message(sender, f"✅ Active AI Endpoints:\n\n{model_str}\n\nRouters: coder-fast | coder-smart | reasoning-heavy")
                else:
                    await send_signal_message(sender, f"⚠️ LiteLLM HTTP {resp.status_code}")
        except Exception as e:
            await send_signal_message(sender, f"❌ Failed to reach LiteLLM: {e}")

    elif cmd == "/projects":
        if not WORKSPACE.exists():
            await send_signal_message(sender, "📁 Workspace folder not mounted.")
            return
        projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")]
        proj_str = "\n".join([f"📂 {p}" for p in projects]) if projects else "No projects found."
        await send_signal_message(sender, f"📁 Workspace Projects:\n\n{proj_str}")

    elif cmd == "/clone":
        if not args:
            await send_signal_message(sender, "Usage: /clone <git-url> [folder-name]")
            return
        raw_url = args[0]
        git_url = sanitize_git_url(raw_url)
        if not git_url:
            await send_signal_message(sender, "❌ Invalid git URL format.")
            return

        folder = args[1] if len(args) > 1 else git_url.rstrip("/").split("/")[-1].replace(".git", "")
        target = sanitize_project_path(WORKSPACE, folder)
        if not target:
            await send_signal_message(sender, "❌ Invalid folder name.")
            return

        if target.exists():
            await send_signal_message(sender, f"⚠️ Folder {folder} already exists.")
            return
        await send_signal_message(sender, f"⏳ Cloning {git_url} into {folder}...")
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "clone", "--", git_url, str(target), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            await send_signal_message(sender, f"✅ Successfully cloned {folder}!\nRun /task {folder} \"instructions\" to begin coding.")
        else:
            await send_signal_message(sender, f"❌ Git clone failed:\n{stderr.decode('utf-8', errors='replace')}")

    elif cmd == "/pull":
        if not args:
            await send_signal_message(sender, "Usage: /pull <project-name>")
            return
        pdir = sanitize_project_path(WORKSPACE, args[0])
        if not pdir or not pdir.exists() or not (pdir / ".git").exists():
            await send_signal_message(sender, f"❌ Invalid git repo: {args[0]}")
            return
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "pull", "--rebase", cwd=str(pdir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, _ = await proc.communicate()
        await send_signal_message(sender, f"📥 Git Pull Result for {args[0]}:\n{stdout.decode('utf-8', errors='replace')}")

    elif cmd == "/push":
        if not args:
            await send_signal_message(sender, "Usage: /push <project-name> [branch]")
            return
        pdir = sanitize_project_path(WORKSPACE, args[0])
        if not pdir or not pdir.exists() or not (pdir / ".git").exists():
            await send_signal_message(sender, f"❌ Invalid git repo: {args[0]}")
            return
        branch = "HEAD"
        if len(args) > 1:
            valid_branch = sanitize_branch_name(args[1])
            if not valid_branch:
                await send_signal_message(sender, "❌ Invalid branch name format.")
                return
            branch = valid_branch
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "origin", "--", branch, cwd=str(pdir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace") + "\n" + stderr.decode("utf-8", errors="replace")
        await send_signal_message(sender, f"🚀 Git Push Result:\n{out.strip()}")

    elif cmd == "/diff":
        if not args:
            await send_signal_message(sender, "Usage: /diff <project-name>")
            return
        pdir = sanitize_project_path(WORKSPACE, args[0])
        if not pdir or not pdir.exists() or not (pdir / ".git").exists():
            await send_signal_message(sender, f"❌ Invalid git repo: {args[0]}")
            return
        p_stat = await asyncio.create_subprocess_exec(GIT_BIN, "status", "-s", cwd=str(pdir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
        p_diff = await asyncio.create_subprocess_exec(GIT_BIN, "diff", "--stat", cwd=str(pdir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
        o_stat, _ = await p_stat.communicate()
        o_diff, _ = await p_diff.communicate()
        await send_signal_message(sender, f"📊 Git Diff for {args[0]}:\n\nStatus:\n{o_stat.decode('utf-8', errors='replace')}\nDiff:\n{o_diff.decode('utf-8', errors='replace')}")

    elif cmd == "/chat":
        if not args:
            await send_signal_message(sender, "Usage: /chat <your question>")
            return
        query = " ".join(args)
        await send_signal_message(sender, "💭 Thinking...")
        try:
            res = ai_client.chat.completions.create(
                model="coder-smart",
                messages=[{"role": "user", "content": query}],
                max_tokens=2048
            )
            await send_signal_message(sender, res.choices[0].message.content[:4000])
        except Exception as e:
            await send_signal_message(sender, f"❌ AI Generation Error: {e}")

    elif cmd == "/task":
        if len(args) < 2:
            await send_signal_message(sender, "Usage: /task <project-name> <instructions>")
            return
        pname = args[0]
        instructions = " ".join(args[1:])
        pdir = sanitize_project_path(WORKSPACE, pname)
        if not pdir or not pdir.exists():
            await send_signal_message(sender, f"❌ Project {pname} does not exist.")
            return

        session_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task_branch = f"agent/{session_id}"
        await send_signal_message(sender, f"🚀 Launching Agent Task ({session_id})\nProject: {pname}\nBranch: {task_branch}\nInstruction: {instructions}\n\nAgent is coding in background...")

        asyncio.create_task(run_signal_agent_task(sender, pdir, instructions, session_id, task_branch))

async def run_signal_agent_task(sender: str, project_dir: Path, instructions: str, session_id: str, task_branch: str):
    """Executes coding loop and streams results to Signal."""
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
            "--yes-always",
            "--no-git-commit-prefix"
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )  # nosec B603,B607
        stdout, _ = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace")

        push_status = ""
        diff_summary = "No new commits."
        if is_git:
            d_proc = await asyncio.create_subprocess_exec(GIT_BIN, "diff", "main..." + task_branch, "--stat", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE)  # nosec B603,B607
            d_out, _ = await d_proc.communicate()
            diff_summary = d_out.decode("utf-8", errors="replace").strip() or "Changes committed."

            try:
                p_proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "-u", "origin", task_branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
                await p_proc.communicate()
                if p_proc.returncode == 0:
                    push_status = f"🚀 Branch pushed to remote: {task_branch}\n"
            except Exception as pe:
                logger.info(f"Remote push skipped: {pe}")

        summary = (
            f"✅ Agent Task Completed! ({session_id})\n\n"
            f"📁 Project: {project_dir.name}\n"
            f"🌿 Branch: {task_branch}\n"
            f"{push_status}"
            f"📊 Git Diff Summary:\n{diff_summary[:800]}\n\n"
            f"🔍 Excerpt:\n{out_text[-1000:] if out_text else 'Done.'}"
        )
        await send_signal_message(sender, summary)

    except Exception as e:
        logger.error(f"Signal agent task error: {e}", exc_info=True)
        await send_signal_message(sender, f"❌ Task {session_id} failed: {e}")

async def listen_signal_websocket():
    """Listens for incoming Signal messages over WebSocket."""
    ws_url = f"{SIGNAL_API_URL.replace('http://', 'ws://').replace('https://', 'wss://')}/v1/receive/{SIGNAL_PHONE_NUMBER}"
    logger.info(f"Connecting to Signal WebSocket at {ws_url}...")

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                logger.info("✅ Connected to Signal message stream.")
                while True:
                    raw_msg = await ws.recv()
                    data = json.loads(raw_msg)
                    envelope = data.get("envelope", {})
                    sender = envelope.get("source") or envelope.get("sourceNumber")
                    data_msg = envelope.get("dataMessage", {})
                    text = data_msg.get("message")

                    if not sender or not text:
                        continue

                    # Strict Authorization Check
                    if SIGNAL_ALLOWED_NUMBER and sender != SIGNAL_ALLOWED_NUMBER:
                        logger.warning(f"Unauthorized Signal message from {sender}")
                        continue

                    await handle_command(sender, text)

        except Exception as e:
            logger.warning(f"Signal WebSocket disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    if not SIGNAL_PHONE_NUMBER:
        print("ERROR: SIGNAL_PHONE_NUMBER environment variable is required!", file=sys.stderr)
        sys.exit(1)

    print(f"🔒 Signal Agent Relay Bot starting for {SIGNAL_PHONE_NUMBER}...")
    asyncio.run(listen_signal_websocket())
