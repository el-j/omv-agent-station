#!/usr/bin/env python3
"""
Discord Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8.
Provides remote command execution, autonomous coding agent dispatch (Aider/Claude Code),
Git repository synchronization, Obsidian second-brain integration, and LiteLLM gateway telemetry over Discord.
Powered by agent_station_core.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Auto-resolve agent_station_core in sys.path
_bot_dir = Path(__file__).parent.resolve()
_root_dir = _bot_dir.parent.resolve()
for path_cand in [str(_bot_dir), str(_root_dir)]:
    if path_cand not in sys.path:
        sys.path.insert(0, path_cand)

import asyncio

import discord
from discord.ext import commands

from agent_station_core import task_registry
from agent_station_core import (
    WORKSPACE,
    logger,
    init_git_credentials,
    sanitize_project_path,
    sanitize_branch_name,
    sanitize_cmd_name,
    sanitize_relative_path,
    clone_repository,
    create_new_repository,
    git_pull_repo,
    git_push_repo,
    git_diff_repo,
    list_workspace_projects,
    query_ai_model,
    list_ai_models,
    get_modelhelp_markdown,
    run_autonomous_task,
    run_claude_cli,
    run_shell_exec,
    get_system_status,
    save_obsidian_note,
    list_vault_notes,
    load_custom_commands,
    save_custom_commands,
    expand_custom_command,
    set_bound_project,
    remove_bound_project,
    get_bound_project,
    resolve_project_context_raw,
    MAX_UPLOAD_BYTES,
    parse_upload_caption,
    run_repo_upload,
    build_compare_url,
)

DISCORD_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
ALLOWED_USER_ID = os.environ.get("DISCORD_ALLOWED_USER_ID")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents, help_command=None)

def is_authorized(ctx: commands.Context) -> bool:
    """Verifies that the message sender matches DISCORD_ALLOWED_USER_ID."""
    if not ALLOWED_USER_ID:
        return True
    if not ctx.author:
        return False
    return str(ctx.author.id) == str(ALLOWED_USER_ID)

async def check_auth(ctx: commands.Context) -> bool:
    """Replies with an error if the user is unauthorized."""
    if not is_authorized(ctx):
        logger.warning(f"Unauthorized Discord access attempt from user ID: {ctx.author.id} ({ctx.author.name})")
        await ctx.reply("⛔ **Unauthorized access.** Configure your numeric Discord User ID in OMV Agent Station settings.")
        return False
    return True

def channel_scope(ctx: commands.Context) -> tuple[str, str | None]:
    """Resolves the stable (channel_id, thread_id) binding key for a context.

    A Discord Thread has its own stable id distinct from every message posted
    in it -- using ctx.message.id here (as this used to) makes every message
    look like a different thread, so a binding set by /bind can never be
    found again by a later message.
    """
    if isinstance(ctx.channel, discord.Thread):
        parent_id = ctx.channel.parent_id or ctx.channel.id
        return str(parent_id), str(ctx.channel.id)
    return str(ctx.channel.id), None

def resolve_ctx_project(ctx: commands.Context, args: list[str]) -> tuple[str | None, list[str]]:
    """Resolves project context based on thread ID or channel ID."""
    channel_id, thread_id = channel_scope(ctx)
    return resolve_project_context_raw(channel_id, thread_id, args, WORKSPACE)

# ---------------------------------------------------------------------------
# Discord Bot Commands (All 25 Shared Capabilities)
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    init_git_credentials()
    logger.info(f"Discord Agent Bot logged in as {bot.user.name} (ID: {bot.user.id})")

@bot.command(name="start")
async def start_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    await ctx.reply(
        "🤖 **OMV AI Agent Station — Discord Relay Online**\n\n"
        "24/7 AI-powered development server connected.\n\n"
        "⚡ **Core Commands:**\n"
        "• `/task [project] <prompt>` — Dispatch autonomous coding agent on branch\n"
        "• `/chat <message>` — Ask questions via smart router\n"
        "• `/gemini <prompt>` | `/gpt4 <prompt>` — Direct model shortcuts\n"
        "• `/claude <prompt>` — Run Claude Code CLI in workspace\n"
        "• `/cancel` — Stop the task/claude/exec command currently running\n"
        "• `/projects` — List workspace repositories\n"
        "• `/newrepo <name> [desc]` — Create new GitHub repo\n"
        "• `/clone <url> [name]` — Clone git repository\n"
        "• `/addcmd <name> <template>` — Create custom dynamic shortcuts\n"
        "• `/status` — View server CPU/RAM & tmux sessions\n"
        "• `/help` — Full handbook\n\n"
        "📤 Send any file/image directly to a bound channel to commit it into the project's repo."
    )

@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    await ctx.reply(
        "📖 **Agent Station Handbook & Command Reference**\n\n"
        "**1. AI Models & Chat:**\n"
        "• `/chat [-m model] <question>` — Query smart router or specific model\n"
        "• `/gemini <prompt>` — Google Gemini 3.6 Flash shortcut\n"
        "• `/gpt4 <prompt>` — GitHub Models GPT-4o shortcut\n"
        "• `/models` — List active model endpoints\n"
        "• `/modelhelp` — Detailed capabilities & context sizes\n\n"
        "**2. Coding Agent & Execution:**\n"
        "• `/task [project] <instructions>` — Autonomous coding agent\n"
        "• `/claude <prompt>` — Claude Code CLI execution\n"
        "• `/exec <cmd>` — Sandboxed bash execution\n"
        "• `/cancel` — Stop the task/claude/exec command currently running\n\n"
        "**3. Git & Workspaces:**\n"
        "• `/projects` | `/newrepo` | `/clone` | `/pull` | `/push` | `/branch` | `/diff`\n\n"
        "**4. Notes & Vault:**\n"
        "• `/note <Title> | <Content>` | `/vault`\n\n"
        "**5. Custom Shortcuts:**\n"
        "• `/addcmd <name> <template>` | `/delcmd <name>` | `/cmds`\n\n"
        "**6. File Upload:**\n"
        "• Send any file/image to a bound channel to commit it to the repo\n"
        "• Caption `path/to/file.txt` sets the destination path (defaults to `uploads/<filename>`)\n"
        "• Caption `project: path/to/file.txt` targets a project without binding\n"
        "• `/bind <project>` | `/unbind` — bind this channel to a project"
    )

@bot.command(name="chat")
async def chat_cmd(ctx: commands.Context, *, message: str = ""):
    if not await check_auth(ctx):
        return
    if not message:
        await ctx.reply("Usage: `/chat [-m model] <your question>`")
        return

    parts = message.split()
    model = "coder-smart"
    prompt = message
    if parts and parts[0] in ("-m", "--model") and len(parts) > 2:
        model = parts[1]
        prompt = " ".join(parts[2:])

    msg = await ctx.reply(f"⏳ Querying `{model}`...")
    res = await query_ai_model(prompt, model=model)
    if res["success"]:
        ans = res["answer"]
        if len(ans) > 1900:
            ans = ans[:1900] + "\n...(truncated)"
        await msg.edit(content=ans)
    else:
        await msg.edit(content=f"❌ AI Query error: {res.get('error', 'Unknown error')}")

@bot.command(name="gemini")
async def gemini_cmd(ctx: commands.Context, *, prompt: str = ""):
    if not await check_auth(ctx):
        return
    if not prompt:
        await ctx.reply("Usage: `/gemini <your question>`")
        return
    await chat_cmd(ctx, message=f"-m gemini-3.6-flash {prompt}")

@bot.command(name="gpt4")
async def gpt4_cmd(ctx: commands.Context, *, prompt: str = ""):
    if not await check_auth(ctx):
        return
    if not prompt:
        await ctx.reply("Usage: `/gpt4 <your question>`")
        return
    await chat_cmd(ctx, message=f"-m github-gpt-4o {prompt}")

@bot.command(name="models")
async def models_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    models, live = await list_ai_models()
    model_str = "\n".join([f"• `{m}`" for m in models])
    label = "Active AI Models" if live else "⚠️ Fallback AI Models (LiteLLM gateway unreachable, list may be stale)"
    await ctx.reply(f"🤖 **{label} ({len(models)}):**\n\n{model_str}\n\n*Routers:* `coder-smart`, `reasoning-heavy`")

@bot.command(name="modelhelp")
async def modelhelp_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    text = get_modelhelp_markdown().replace("*", "**")
    await ctx.reply(text)

@bot.command(name="projects")
async def projects_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    projects = list_workspace_projects()
    if not projects:
        await ctx.reply("📁 No workspace projects found.")
        return
    proj_str = "\n".join([f"• `📂 {p}`" for p in projects])
    await ctx.reply(f"📁 **Workspace Projects ({len(projects)}):**\n\n{proj_str}")

@bot.command(name="clone")
async def clone_cmd(ctx: commands.Context, git_url: str = "", folder_name: str = ""):
    if not await check_auth(ctx):
        return
    if not git_url:
        await ctx.reply("Usage: `/clone <git-url> [custom-folder-name]`")
        return

    msg = await ctx.reply(f"⏳ Cloning `{git_url}`...")
    res = await clone_repository(git_url, folder_name)
    if res["success"]:
        f_name = res["folder_name"]
        await msg.edit(content=(
            f"✅ **Repository Cloned & Registered as Active Project!**\n\n"
            f"📁 **Project:** `{f_name}`\n"
            f"💾 **Path:** `/data/workspace/{f_name}`\n"
            f"📓 **Obsidian Spec:** `/data/obsidian/Projects/{f_name}/`\n\n"
            f"Run tasks with `/task {f_name} \"instructions\"`"
        ))
    else:
        await msg.edit(content=f"❌ Git clone failed: {res.get('error')}")

@bot.command(name="newrepo")
async def newrepo_cmd(ctx: commands.Context, repo_name: str = "", *, description: str = ""):
    if not await check_auth(ctx):
        return
    if not repo_name:
        await ctx.reply("Usage: `/newrepo <repo-name> [description]`")
        return

    msg = await ctx.reply(f"⏳ Creating remote GitHub repo `{repo_name}`...")
    res = await create_new_repository(repo_name, description)
    if res["success"]:
        await msg.edit(content=(
            f"✅ **New GitHub Repository Created!**\n\n"
            f"📁 **Project:** `{res['repo_name']}`\n"
            f"🔗 **URL:** {res.get('html_url')}\n"
            f"💾 **Path:** `/data/workspace/{res['repo_name']}`"
        ))
    else:
        await msg.edit(content=f"❌ Failed to create repo: {res.get('error')}")

@bot.command(name="pull")
async def pull_cmd(ctx: commands.Context, project_name: str = ""):
    if not await check_auth(ctx):
        return
    proj, _ = resolve_ctx_project(ctx, [project_name] if project_name else [])
    if not proj:
        await ctx.reply("Usage: `/pull [project-name]`")
        return
    msg = await ctx.reply(f"⏳ Pulling latest changes for `{proj}`...")
    res = await git_pull_repo(proj)
    if res["success"]:
        await msg.edit(content=f"✅ **Git Pull ({proj}):**\n```{res['output'][:1800]}```")
    else:
        await msg.edit(content=f"❌ Git pull failed: {res.get('error')}")

@bot.command(name="push")
async def push_cmd(ctx: commands.Context, project_name: str = "", branch: str = "main"):
    if not await check_auth(ctx):
        return
    proj, remaining = resolve_ctx_project(ctx, [project_name] if project_name else [])
    if not proj:
        await ctx.reply("Usage: `/push [project-name] [branch]`")
        return
    target_branch = remaining[0] if remaining else branch
    msg = await ctx.reply(f"⏳ Pushing `{proj}` to `{target_branch}`...")
    res = await git_push_repo(proj, target_branch)
    if res["success"]:
        await msg.edit(content=f"✅ **Git Push ({proj} -> {target_branch}):**\n```{res['output'][:1800]}```")
    else:
        await msg.edit(content=f"❌ Git push failed: {res.get('error')}")

@bot.command(name="branch")
async def branch_cmd(ctx: commands.Context, project_name: str = "", branch_name: str = ""):
    if not await check_auth(ctx):
        return
    proj, remaining = resolve_ctx_project(ctx, [project_name] if project_name else [])
    if not proj:
        await ctx.reply("Usage: `/branch [project-name] [new-branch-name]`")
        return

    p_dir = sanitize_project_path(WORKSPACE, proj)
    if not p_dir or not (p_dir / ".git").exists():
        await ctx.reply(f"❌ `{proj}` is not a valid git repository.")
        return

    new_b = remaining[0] if remaining else branch_name
    if not new_b:
        res = await run_shell_exec("git branch -a", cwd=p_dir)
        await ctx.reply(f"🌿 **Branches for `{proj}`:**\n```{res['output'][:1800]}```")
    else:
        clean_b = sanitize_branch_name(new_b)
        if not clean_b:
            await ctx.reply("❌ Invalid branch name format.")
            return
        res = await run_shell_exec(f"git checkout -B {clean_b}", cwd=p_dir)
        if res["success"]:
            await ctx.reply(f"🌿 Switched to branch `{clean_b}` in project `{proj}`.")
        else:
            await ctx.reply(f"❌ Branch checkout failed: {res.get('output')}")

@bot.command(name="diff")
async def diff_cmd(ctx: commands.Context, project_name: str = ""):
    if not await check_auth(ctx):
        return
    proj, _ = resolve_ctx_project(ctx, [project_name] if project_name else [])
    if not proj:
        await ctx.reply("Usage: `/diff [project-name]`")
        return
    res = await git_diff_repo(proj)
    if res["success"]:
        diff_text = res["diff"] or "(No uncommitted diff)"
        if len(diff_text) > 1800:
            diff_text = diff_text[:1800] + "\n...(truncated)"
        await ctx.reply(f"🔍 **Git Diff (`{proj}`):**\n```diff\n{diff_text}\n```")
    else:
        await ctx.reply(f"❌ Error: {res.get('error')}")

@bot.command(name="task")
async def task_cmd(ctx: commands.Context, *, args_str: str = ""):
    if not await check_auth(ctx):
        return
    if not args_str:
        await ctx.reply("Usage: `/task [project-name] <coding instructions>`")
        return

    raw_parts = args_str.split()
    proj, remaining = resolve_ctx_project(ctx, raw_parts)
    if not proj or not remaining:
        await ctx.reply("Usage: `/task [project-name] <coding instructions>`")
        return

    instructions = " ".join(remaining)
    p_dir = sanitize_project_path(WORKSPACE, proj)
    if not p_dir or not p_dir.exists():
        await ctx.reply(f"❌ Project directory `{proj}` not found in `/data/workspace`.")
        return

    scope = channel_scope(ctx)
    if task_registry.get(*scope):
        await ctx.reply("⚠️ Another task is already running in this channel. Use `/cancel` to stop it first.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"task_{timestamp}"
    task_branch = f"agent/{session_id}"

    msg = await ctx.reply(f"🚀 **Launching Autonomous Agent Task** for `{proj}` on `{task_branch}`...")
    t = asyncio.create_task(run_task_background(scope, msg, proj, p_dir, instructions, session_id, task_branch))
    task_registry.start(*scope, label=f"task: {instructions}", asyncio_task=t)

async def run_task_background(scope, msg, proj, p_dir, instructions, session_id, task_branch):
    try:
        res = await run_autonomous_task(
            p_dir, instructions, session_id, task_branch,
            on_proc=lambda proc: task_registry.attach_proc(*scope, proc=proc),
        )
        if res["success"]:
            summary = res["summary"]
            if len(summary) > 1800:
                summary = summary[:1800] + "\n...(truncated)"
            await msg.edit(content=f"✅ **Task Completed (`{proj}`):**\n```{summary}```")
        else:
            await msg.edit(content=f"❌ Task execution error: {res.get('error')}")
    except asyncio.CancelledError:
        await msg.edit(content=f"🛑 **Task Cancelled** (`{proj}`, branch `{task_branch}`)")
        raise
    finally:
        task_registry.finish(*scope)

@bot.command(name="claude")
async def claude_cmd(ctx: commands.Context, *, prompt: str = ""):
    if not await check_auth(ctx):
        return
    if not prompt:
        await ctx.reply("Usage: `/claude <instructions>`")
        return

    scope = channel_scope(ctx)
    if task_registry.get(*scope):
        await ctx.reply("⚠️ Another task is already running in this channel. Use `/cancel` to stop it first.")
        return

    msg = await ctx.reply("🤖 **Dispatching Claude Code CLI...**")
    t = asyncio.create_task(run_claude_background(scope, msg, prompt))
    task_registry.start(*scope, label=f"claude: {prompt}", asyncio_task=t)

async def run_claude_background(scope, msg, prompt):
    try:
        res = await run_claude_cli(
            WORKSPACE, prompt,
            on_proc=lambda proc: task_registry.attach_proc(*scope, proc=proc),
        )
        if res["success"]:
            out = res["output"]
            if len(out) > 1900:
                out = out[:1900] + "\n...(truncated)"
            await msg.edit(content=f"✅ **Claude Code:**\n\n{out}")
        else:
            await msg.edit(content=f"❌ Claude error: {res.get('error')}")
    except asyncio.CancelledError:
        await msg.edit(content="🛑 **Claude Code Cancelled**")
        raise
    finally:
        task_registry.finish(*scope)

@bot.command(name="exec")
async def exec_cmd(ctx: commands.Context, *, shell_cmd: str = ""):
    if not await check_auth(ctx):
        return
    if not shell_cmd:
        await ctx.reply("Usage: `/exec <shell command>`")
        return

    scope = channel_scope(ctx)
    if task_registry.get(*scope):
        await ctx.reply("⚠️ Another task is already running in this channel. Use `/cancel` to stop it first.")
        return

    msg = await ctx.reply(f"⏳ Executing: `{shell_cmd}`...")
    t = asyncio.create_task(run_exec_background(scope, msg, shell_cmd))
    task_registry.start(*scope, label=f"exec: {shell_cmd}", asyncio_task=t)

async def run_exec_background(scope, msg, shell_cmd):
    try:
        res = await run_shell_exec(
            shell_cmd, cwd=WORKSPACE,
            on_proc=lambda proc: task_registry.attach_proc(*scope, proc=proc),
        )
        out = res["output"]
        if len(out) > 1800:
            out = out[:1800] + "\n...(truncated)"
        await msg.edit(content=f"🖥️ **Output:**\n```{out}```")
    except asyncio.CancelledError:
        await msg.edit(content=f"🛑 **Cancelled:** `{shell_cmd}`")
        raise
    finally:
        task_registry.finish(*scope)

@bot.command(name="cancel", aliases=["stop"])
async def cancel_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    scope = channel_scope(ctx)
    label = await task_registry.cancel(*scope)
    if label is None:
        await ctx.reply("ℹ️ Nothing is currently running here to cancel.")
        return
    await ctx.reply(f"🛑 Cancelling: `{label}`...")

@bot.command(name="status")
async def status_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    metrics = get_system_status()
    await ctx.reply(
        f"🖥️ **OMV Server Status**\n\n"
        f"⏱️ **Uptime:** `{metrics['uptime']}`\n"
        f"🧠 **RAM:** `{metrics['ram']}`\n"
        f"💾 **Disk Space:** `{metrics['disk']}`\n\n"
        f"🧵 **Active Tmux Sessions:**\n```{metrics['tmux']}```"
    )

@bot.command(name="note")
async def note_cmd(ctx: commands.Context, *, note_text: str = ""):
    if not await check_auth(ctx):
        return
    if not note_text:
        await ctx.reply("Usage: `/note <Title> | <Content>`")
        return
    if "|" in note_text:
        title, content = note_text.split("|", 1)
    else:
        title = f"Quick Note {datetime.now().strftime('%Y-%m-%d %H%M')}"
        content = note_text
    res = save_obsidian_note(title.strip(), content.strip())
    if res["success"]:
        await ctx.reply(f"✅ **Note Saved to Obsidian:** `{res['path']}`")
    else:
        await ctx.reply(f"❌ Failed to save note: {res.get('error')}")

@bot.command(name="vault")
async def vault_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    res = list_vault_notes()
    if res["success"]:
        recent_str = "\n".join([f"• `{f}`" for f in res["recent"]]) if res["recent"] else "No notes found."
        await ctx.reply(f"📓 **Obsidian Vault ({res['total_notes']} notes):**\n\n{recent_str}")
    else:
        await ctx.reply(f"❌ Error: {res.get('error')}")

@bot.command(name="addcmd")
async def addcmd_cmd(ctx: commands.Context, name: str = "", *, template: str = ""):
    if not await check_auth(ctx):
        return
    if not name or not template:
        await ctx.reply("Usage: `/addcmd <command-name> <command-template>`")
        return
    san_name = sanitize_cmd_name(name)
    if not san_name:
        await ctx.reply("❌ Invalid command name format.")
        return
    cmds = load_custom_commands()
    cmds[san_name] = template
    save_custom_commands(cmds)
    await ctx.reply(f"✅ **Custom Shortcut Registered:** `/{san_name}` ➔ `{template}`")

@bot.command(name="delcmd")
async def delcmd_cmd(ctx: commands.Context, name: str = ""):
    if not await check_auth(ctx):
        return
    san_name = sanitize_cmd_name(name)
    if not san_name:
        await ctx.reply("Usage: `/delcmd <command-name>`")
        return
    cmds = load_custom_commands()
    if san_name in cmds:
        del cmds[san_name]
        save_custom_commands(cmds)
        await ctx.reply(f"✅ Deleted shortcut `/{san_name}`.")
    else:
        await ctx.reply(f"⚠️ Shortcut `/{san_name}` not found.")

@bot.command(name="cmds")
async def customcmds_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    cmds = load_custom_commands()
    if not cmds:
        await ctx.reply("📋 No custom shortcuts configured yet. Create one with `/addcmd`.")
        return
    lines = [f"• `/{k}` ➔ `{v}`" for k, v in sorted(cmds.items())]
    await ctx.reply(f"⚡ **Custom Shortcuts ({len(cmds)}):**\n\n" + "\n".join(lines))

@bot.command(name="bind")
async def bind_cmd(ctx: commands.Context, project_name: str = ""):
    if not await check_auth(ctx):
        return
    if not project_name:
        await ctx.reply("Usage: `/bind <project-name>`")
        return
    p_dir = sanitize_project_path(WORKSPACE, project_name)
    if not p_dir or not p_dir.exists():
        await ctx.reply(f"❌ Project `{project_name}` not found in `/data/workspace`.")
        return
    channel_id, thread_id = channel_scope(ctx)
    set_bound_project(channel_id, thread_id, project_name)
    await ctx.reply(f"✅ Channel bound to project `{project_name}`. All tasks now target this repo.")

@bot.command(name="unbind")
async def unbind_cmd(ctx: commands.Context):
    if not await check_auth(ctx):
        return
    channel_id, thread_id = channel_scope(ctx)
    remove_bound_project(channel_id, thread_id)
    await ctx.reply("✅ Unbound project context from this channel.")

# ---------------------------------------------------------------------------
# File Upload to GitHub (parity with Telegram's handlers/upload.py)
# ---------------------------------------------------------------------------

async def handle_discord_upload(message: discord.Message):
    """Entry point: any message with an attachment is treated as a repo upload."""
    if not is_authorized(message):
        return

    attachment = message.attachments[0]
    if attachment.size > MAX_UPLOAD_BYTES:
        await message.reply(f"❌ File is {attachment.size / 1024 / 1024:.1f} MB -- max upload size is {MAX_UPLOAD_BYTES // 1024 // 1024} MB.")
        return

    project_override, path_hint = parse_upload_caption(message.content)
    channel_id, thread_id = channel_scope(message)
    project_name = project_override or get_bound_project(channel_id, thread_id)
    if not project_name:
        await message.reply("❌ No project bound to this channel.\n\nUse `/bind <project>` first, then resend the file.")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists():
        await message.reply(f"❌ Project `{project_name}` does not exist in `/data/workspace`.")
        return
    if not (project_dir / ".git").exists():
        await message.reply(f"❌ Project `{project_name}` is not a git repository.")
        return

    relative_path_str = path_hint or f"uploads/{attachment.filename}"
    target_path = sanitize_relative_path(project_dir, relative_path_str)
    if not target_path:
        await message.reply(f"❌ Invalid target path `{relative_path_str}` -- must stay inside the project and can't touch `.git/`.")
        return

    scope = channel_scope(message)
    if task_registry.get(*scope):
        await message.reply("⚠️ Another task is already running here. Use `/cancel` to stop it first.")
        return

    status_msg = await message.reply(
        f"📤 **Uploading to repository**\n\n"
        f"📁 Project: `{project_name}`\n"
        f"📄 Path: `{target_path.relative_to(project_dir)}`\n\n"
        f"⏳ Downloading from Discord..."
    )
    t = asyncio.create_task(run_discord_upload_background(scope, status_msg, attachment, project_dir, target_path))
    task_registry.start(*scope, label=f"upload: {target_path.name}", asyncio_task=t)

async def run_discord_upload_background(scope, status_msg, attachment, project_dir: Path, target_path: Path):
    try:
        file_bytes = await attachment.read()
        res = await run_repo_upload(
            project_dir, target_path, file_bytes,
            f"chore(upload): add {target_path.relative_to(project_dir)} via Discord upload",
            on_proc=lambda proc: task_registry.attach_proc(*scope, proc=proc),
        )
        if not res["success"]:
            await status_msg.edit(content=f"❌ {res['error']}")
            return

        reply = f"✅ **File Uploaded**\n\n📄 Path: `{res['relative_path']}`\n🌿 Branch: `{res['branch']}`\n"
        compare_url = build_compare_url(res["owner_repo"], res["base_branch"], res["branch"])
        if compare_url:
            reply += f"\n🔗 [Open compare / create PR]({compare_url})"
        await status_msg.edit(content=reply)
    except asyncio.CancelledError:
        await status_msg.edit(content=f"🛑 **Upload Cancelled**\n\n📄 Path: `{target_path.name}`")
        raise
    except Exception as e:
        logger.error(f"Error in Discord file upload: {e}", exc_info=True)
        await status_msg.edit(content=f"❌ Upload error: {e}")
    finally:
        task_registry.finish(*scope)

# Dynamic shortcut fallback
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.attachments:
        await handle_discord_upload(message)
        return
    if message.content.startswith("/"):
        parts = message.content.lstrip("/").split(maxsplit=1)
        cmd_name = parts[0].lower()
        passed_args = parts[1] if len(parts) > 1 else ""
        expanded = expand_custom_command(cmd_name, passed_args)
        if expanded and not bot.get_command(cmd_name):
            ctx = await bot.get_context(message)
            exp_parts = expanded.split()
            target_cmd = bot.get_command(exp_parts[0].lstrip("/"))
            if target_cmd:
                await target_cmd(ctx, *exp_parts[1:])
                return
    await bot.process_commands(message)

def main():
    if not DISCORD_TOKEN:
        print("ℹ️ DISCORD_BOT_TOKEN environment variable not set. Bot in standby mode.", file=sys.stderr)
        import time
        while True:
            time.sleep(3600)
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
