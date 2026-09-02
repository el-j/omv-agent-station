"""
Core System Commands: welcome/help text, status telemetry, sandboxed shell
execution, and autonomous coding agent dispatch (Claude Code / task runner).
"""

import asyncio
from datetime import datetime

from discord.ext import commands

from agent_station_core import (
    WORKSPACE,
    task_registry,
    sanitize_project_path,
    run_autonomous_task,
    run_claude_cli,
    run_shell_exec,
    get_system_status,
)
from core.security import check_auth, channel_scope, resolve_ctx_project


async def start_cmd(ctx: commands.Context):
    """Replies with the welcome banner and a quick command overview."""
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


async def help_cmd(ctx: commands.Context):
    """Replies with the full command reference / handbook."""
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


async def status_cmd(ctx: commands.Context):
    """Replies with server uptime/RAM/disk and active tmux session info."""
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


async def task_cmd(ctx: commands.Context, *, args_str: str = ""):
    """Dispatches the autonomous coding agent on a fresh agent/<timestamp> branch."""
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
    """Runs the autonomous agent in the background so /cancel can stop it mid-flight."""
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


async def claude_cmd(ctx: commands.Context, *, prompt: str = ""):
    """Dispatches the Claude Code CLI against the whole shared workspace."""
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
    """Runs Claude Code CLI in the background so /cancel can stop it mid-flight."""
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


async def exec_cmd(ctx: commands.Context, *, shell_cmd: str = ""):
    """Runs an arbitrary shell command inside the shared workspace sandbox."""
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
    """Runs the shell command in the background so /cancel can stop it mid-flight."""
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


async def cancel_cmd(ctx: commands.Context):
    """Cancels whatever background task (task/claude/exec) is running in this channel."""
    if not await check_auth(ctx):
        return
    scope = channel_scope(ctx)
    label = await task_registry.cancel(*scope)
    if label is None:
        await ctx.reply("ℹ️ Nothing is currently running here to cancel.")
        return
    await ctx.reply(f"🛑 Cancelling: `{label}`...")
