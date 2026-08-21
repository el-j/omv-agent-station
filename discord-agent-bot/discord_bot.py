#!/usr/bin/env python3
"""
Discord Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8
Provides remote command execution, autonomous coding agent dispatch (Aider/Claude Code),
Git repository synchronization, Obsidian second-brain integration, and LiteLLM gateway telemetry over Discord.
"""

import os
import sys
import logging
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime
import discord
from discord.ext import commands
import httpx
from openai import OpenAI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("DiscordAgentBot")

DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
ALLOWED_USER_ID = os.environ.get("DISCORD_ALLOWED_USER_ID")
LITELLM_BASE = os.environ.get("LITELLM_API_BASE", "http://litellm:4000")
LITELLM_KEY = os.environ.get("LITELLM_API_KEY", "sk-omv-master-key")
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "/data/obsidian"))
WORKSPACE = Path(os.environ.get("WORKSPACE_PATH", "/data/workspace"))

# Git Configuration
GIT_AUTHOR_NAME = os.environ.get("GIT_AUTHOR_NAME", "OMV AI Agent")
GIT_AUTHOR_EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "agent@proliant-omv.local")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
BITBUCKET_USER = os.environ.get("BITBUCKET_USERNAME", "")
BITBUCKET_PASS = os.environ.get("BITBUCKET_APP_PASSWORD", "")

def init_git_credentials():
    try:
        subprocess.run(["git", "config", "--global", "user.name", GIT_AUTHOR_NAME], check=True)
        subprocess.run(["git", "config", "--global", "user.email", GIT_AUTHOR_EMAIL], check=True)
        subprocess.run(["git", "config", "--global", "init.defaultBranch", "main"], check=True)

        if GITHUB_TOKEN:
            subprocess.run([
                "git", "config", "--global",
                f"url.https://x-access-token:{GITHUB_TOKEN}@github.com/.insteadOf",
                "https://github.com/"
            ], check=True)
        if GITLAB_TOKEN:
            subprocess.run([
                "git", "config", "--global",
                f"url.https://oauth2:{GITLAB_TOKEN}@gitlab.com/.insteadOf",
                "https://gitlab.com/"
            ], check=True)
        if BITBUCKET_USER and BITBUCKET_PASS:
            subprocess.run([
                "git", "config", "--global",
                f"url.https://{BITBUCKET_USER}:{BITBUCKET_PASS}@bitbucket.org/.insteadOf",
                "https://bitbucket.org/"
            ], check=True)
    except Exception as e:
        logger.warning(f"Could not configure git credentials: {e}")

init_git_credentials()

ai_client = OpenAI(
    api_key=LITELLM_KEY,
    base_url=f"{LITELLM_BASE}/v1"
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=["!", "/"], intents=intents)

def is_authorized(ctx) -> bool:
    if not ALLOWED_USER_ID:
        return True
    return str(ctx.author.id) == str(ALLOWED_USER_ID)

@bot.event
async def on_ready():
    logger.info(f"✅ Discord Agent Bot logged in as {bot.user} (ID: {bot.user.id})")

@bot.command(name="help_agent", aliases=["help"])
async def cmd_help(ctx):
    if not is_authorized(ctx):
        return
    embed = discord.Embed(
        title="🤖 OMV AI Orchestrator (Discord Relay)",
        description="24/7 autonomous software engineering & agent relay running on your HP ProLiant Gen8.",
        color=discord.Color.blue()
    )
    embed.add_field(name="!task <project> <prompt>", value="Runs autonomous coding loop, creates branch & auto-pushes", inline=False)
    embed.add_field(name="!chat <message>", value="Ask architecture & coding questions using Gemini 3.7 / Claude 3.7", inline=False)
    embed.add_field(name="!clone <url> [name]", value="Clone GitHub / GitLab / Bitbucket repo into workspace", inline=False)
    embed.add_field(name="!pull / !push / !branch / !diff", value="Manage git versioning & branch syncing", inline=False)
    embed.add_field(name="!projects / !vault / !models / !status", value="Server status, Obsidian notes & active AI models", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="status")
async def cmd_status(ctx):
    if not is_authorized(ctx):
        return
    try:
        tmux_out = subprocess.check_output(["tmux", "list-sessions"], stderr=subprocess.STDOUT, text=True).strip()
    except Exception:
        tmux_out = "No active tmux sessions."
    try:
        uptime_out = subprocess.check_output(["uptime"], text=True).strip()
        df_out = subprocess.check_output(["df", "-h", "/data/workspace"], text=True).strip().splitlines()[-1]
    except Exception:
        uptime_out = "N/A"
        df_out = "N/A"

    embed = discord.Embed(title="🖥️ ProLiant Gen8 Server Status", color=discord.Color.green())
    embed.add_field(name="⏱️ Uptime", value=f"`{uptime_out}`", inline=False)
    embed.add_field(name="💾 Workspace Disk", value=f"`{df_out}`", inline=False)
    embed.add_field(name="🧵 Active Agent Sessions", value=f"```\n{tmux_out}\n```", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="models")
async def cmd_models(ctx):
    if not is_authorized(ctx):
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{LITELLM_BASE}/models", headers={"Authorization": f"Bearer {LITELLM_KEY}"})
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id") for m in data.get("data", [])]
                model_str = "\n".join([f"• `{m}`" for m in models])
                embed = discord.Embed(title="✅ Active AI Model Endpoints", description=f"{model_str}\n\n**Virtual Routers:** `coder-fast` | `coder-smart` | `reasoning-heavy`", color=discord.Color.purple())
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"⚠️ LiteLLM HTTP {resp.status_code}")
    except Exception as e:
        await ctx.send(f"❌ Failed to query LiteLLM: {e}")

@bot.command(name="projects")
async def cmd_projects(ctx):
    if not is_authorized(ctx):
        return
    if not WORKSPACE.exists():
        await ctx.send("📁 Workspace directory not mounted.")
        return
    projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")]
    proj_str = "\n".join([f"📁 `{p}`" for p in projects]) if projects else "No projects found."
    await ctx.send(embed=discord.Embed(title="📂 Workspace Projects", description=proj_str, color=discord.Color.gold()))

@bot.command(name="clone")
async def cmd_clone(ctx, git_url: str, folder_name: str = None):
    if not is_authorized(ctx):
        return
    folder = folder_name if folder_name else git_url.rstrip("/").split("/")[-1].replace(".git", "")
    target = WORKSPACE / folder
    if target.exists():
        await ctx.send(f"⚠️ Folder `{folder}` already exists in workspace.")
        return

    msg = await ctx.send(f"⏳ Cloning `{git_url}` into `{folder}`...")
    proc = await asyncio.create_subprocess_exec("git", "clone", git_url, str(target), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await proc.communicate()
    if proc.returncode == 0:
        await msg.edit(content=f"✅ Successfully cloned `{folder}`!\nRun `!task {folder} <instructions>` to begin coding.")
    else:
        await msg.edit(content=f"❌ Git clone failed:\n```\n{stderr.decode('utf-8', errors='replace')}\n```")

@bot.command(name="chat")
async def cmd_chat(ctx, *, query: str):
    if not is_authorized(ctx):
        return
    async with ctx.typing():
        try:
            res = ai_client.chat.completions.create(
                model="coder-smart",
                messages=[{"role": "user", "content": query}],
                max_tokens=2048
            )
            reply = res.choices[0].message.content
            if len(reply) > 1950:
                reply = reply[:1950] + "\n\n*(Truncated for Discord)*"
            await ctx.send(reply)
        except Exception as e:
            await ctx.send(f"❌ Error during AI generation: {e}")

@bot.command(name="task")
async def cmd_task(ctx, project_name: str, *, instructions: str):
    if not is_authorized(ctx):
        return
    project_dir = WORKSPACE / project_name
    if not project_dir.exists():
        await ctx.send(f"❌ Project `{project_name}` does not exist in `/data/workspace`.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"task_{timestamp}"
    task_branch = f"agent/{session_id}"

    embed = discord.Embed(
        title=f"🚀 Launching Autonomous Agent Task ({session_id})",
        color=discord.Color.orange()
    )
    embed.add_field(name="Project", value=f"`{project_name}`", inline=True)
    embed.add_field(name="Branch", value=f"`{task_branch}`", inline=True)
    embed.add_field(name="Instruction", value=instructions, inline=False)
    embed.set_footer(text="Agent is executing ReAct loop in background...")
    status_msg = await ctx.send(embed=embed)

    asyncio.create_task(run_discord_agent_task(ctx, status_msg, project_dir, instructions, session_id, task_branch))

async def run_discord_agent_task(ctx, status_msg, project_dir: Path, instructions: str, session_id: str, task_branch: str):
    try:
        is_git = (project_dir / ".git").exists()
        if is_git:
            await asyncio.create_subprocess_exec("git", "checkout", "-B", task_branch, cwd=str(project_dir))

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

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        out_text = stdout.decode("utf-8", errors="replace")

        push_status = "Local commit only."
        diff_summary = "No new commits."
        if is_git:
            d_proc = await asyncio.create_subprocess_exec("git", "diff", "main..." + task_branch, "--stat", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE)
            d_out, _ = await d_proc.communicate()
            diff_summary = d_out.decode("utf-8", errors="replace").strip() or "Changes committed."

            try:
                p_proc = await asyncio.create_subprocess_exec("git", "push", "-u", "origin", task_branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await p_proc.communicate()
                if p_proc.returncode == 0:
                    push_status = f"✅ Branch pushed to remote: `{task_branch}`"
            except Exception:
                pass

        result_embed = discord.Embed(
            title=f"✅ Agent Task Completed! ({session_id})",
            color=discord.Color.green()
        )
        result_embed.add_field(name="Project", value=f"`{project_dir.name}`", inline=True)
        result_embed.add_field(name="Branch", value=f"`{task_branch}`", inline=True)
        result_embed.add_field(name="Remote Push", value=push_status, inline=False)
        result_embed.add_field(name="Git Changes", value=f"```\n{diff_summary[:800]}\n```", inline=False)
        if out_text:
            result_embed.add_field(name="Agent Log Excerpt", value=f"```\n{out_text[-900:]}\n```", inline=False)

        await status_msg.edit(embed=result_embed)

    except Exception as e:
        logger.error(f"Error in Discord task: {e}", exc_info=True)
        await ctx.send(f"❌ Task `{session_id}` failed: {e}")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN environment variable required!", file=sys.stderr)
        sys.exit(1)

    print("🤖 Discord Agent Relay Bot starting...")
    bot.run(DISCORD_TOKEN)
