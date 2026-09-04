"""
Core System Commands: welcome/help text, status telemetry, sandboxed shell
execution, and autonomous coding agent dispatch (Claude Code / task runner).
"""

import asyncio
from datetime import datetime

from agent_station_core import (
    WORKSPACE,
    task_registry,
    sanitize_project_path,
    run_autonomous_task,
    run_claude_cli,
    run_shell_exec,
    get_system_status,
    resolve_project_context_raw,
)
from core.messaging import send_signal_message


async def start(sender: str, args: list[str]):
    """Sends the welcome banner and a quick command overview."""
    welcome = (
        "🤖 OMV AI Agent Station — Signal Relay Online\n\n"
        "24/7 AI Development Server Connected.\n\n"
        "⚡ Core Commands:\n"
        "• /task [project] <prompt> — Run autonomous coding agent on branch\n"
        "• /chat <message> — Ask questions via smart router\n"
        "• /gemini <prompt> | /gpt4 <prompt> — Quick model shortcuts\n"
        "• /claude <prompt> — Run Claude Code CLI in workspace\n"
        "• /cancel — Stop the task/claude/exec command currently running\n"
        "• /projects — List workspace repositories\n"
        "• /newrepo <name> [desc] — Create new GitHub repository\n"
        "• /clone <url> [name] — Clone git repository\n"
        "• /addcmd <name> <template> — Create dynamic custom shortcuts\n"
        "• /bind <project> | /unbind — Bind this chat to a project\n"
        "• /status — Server CPU/RAM & tmux sessions\n"
        "• /help — Full handbook\n\n"
        "📤 Send any file/image directly to commit it into your bound project's repo."
    )
    await send_signal_message(sender, welcome)


async def help_cmd(sender: str, args: list[str]):
    """Sends the full command reference / handbook."""
    help_text = (
        "📖 Agent Station Handbook & Command Reference\n\n"
        "1. AI Models & Chat:\n"
        "• /chat [-m model] <question>\n"
        "• /gemini <prompt> | /gpt4 <prompt>\n"
        "• /models | /modelhelp\n\n"
        "2. Coding Agent & Execution:\n"
        "• /task [project] <instructions>\n"
        "• /claude <prompt> | /exec <cmd>\n"
        "• /cancel — Stop the task/claude/exec command currently running\n\n"
        "3. Git & Workspaces:\n"
        "• /projects | /newrepo | /clone | /pull | /push | /branch | /diff\n\n"
        "4. Notes & Vault:\n"
        "• /note <Title> | <Content> | /vault\n\n"
        "5. Custom Shortcuts:\n"
        "• /addcmd <name> <template> | /delcmd <name> | /cmds\n\n"
        "6. File Upload:\n"
        "• Send any file/image to commit it to the bound project's repo\n"
        "• Caption 'path/to/file.txt' sets the destination path (defaults to uploads/<filename>)\n"
        "• Caption 'project: path/to/file.txt' targets a project without binding\n"
        "• /bind <project> | /unbind — bind this chat to a project"
    )
    await send_signal_message(sender, help_text)


async def status(sender: str, args: list[str]):
    """Sends server uptime/RAM/disk and active tmux session info."""
    metrics = get_system_status()
    await send_signal_message(
        sender,
        f"🖥️ OMV Server Status\n\n"
        f"⏱️ Uptime: {metrics['uptime']}\n"
        f"🧠 RAM: {metrics['ram']}\n"
        f"💾 Disk Space: {metrics['disk']}\n\n"
        f"🧵 Active Tmux Sessions:\n{metrics['tmux']}"
    )


async def task(sender: str, args: list[str]):
    """Dispatches the autonomous coding agent on a fresh agent/<timestamp> branch."""
    if not args:
        await send_signal_message(sender, "Usage: /task [project-name] <coding instructions>")
        return
    proj, remaining = resolve_project_context_raw(sender, None, args, WORKSPACE)
    if not proj or not remaining:
        await send_signal_message(sender, "Usage: /task [project-name] <coding instructions>")
        return
    instructions = " ".join(remaining)
    p_dir = sanitize_project_path(WORKSPACE, proj)
    if not p_dir or not p_dir.exists():
        await send_signal_message(sender, f"❌ Project directory `{proj}` not found in /data/workspace.")
        return

    if task_registry.get(sender):
        await send_signal_message(sender, "⚠️ Another task is already running for you. Send /cancel to stop it first.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"task_{timestamp}"
    task_branch = f"agent/{session_id}"

    await send_signal_message(sender, f"🚀 Launching Autonomous Agent Task for {proj} on {task_branch}...")
    t = asyncio.create_task(run_task_background(sender, proj, p_dir, instructions, session_id, task_branch))
    task_registry.start(sender, label=f"task: {instructions}", asyncio_task=t)


async def run_task_background(sender, proj, p_dir, instructions, session_id, task_branch):
    """Runs the autonomous agent in the background so /cancel can stop it and
    a second /task from the same sender can't race it on the same git dir."""
    try:
        res = await run_autonomous_task(
            p_dir, instructions, session_id, task_branch,
            on_proc=lambda proc: task_registry.attach_proc(sender, proc=proc),
        )
        if res["success"]:
            await send_signal_message(sender, f"✅ Task Completed ({proj}):\n\n{res['summary']}")
        else:
            await send_signal_message(sender, f"❌ Task execution error: {res.get('error')}")
    except asyncio.CancelledError:
        await send_signal_message(sender, f"🛑 Task Cancelled ({proj}, branch {task_branch})")
        raise
    finally:
        task_registry.finish(sender)


async def claude(sender: str, args: list[str]):
    """Dispatches the Claude Code CLI against the whole shared workspace."""
    if not args:
        await send_signal_message(sender, "Usage: /claude <instructions>")
        return

    if task_registry.get(sender):
        await send_signal_message(sender, "⚠️ Another task is already running for you. Send /cancel to stop it first.")
        return

    prompt = " ".join(args)
    await send_signal_message(sender, "🤖 Dispatching Claude Code CLI...")
    t = asyncio.create_task(run_claude_background(sender, prompt))
    task_registry.start(sender, label=f"claude: {prompt}", asyncio_task=t)


async def run_claude_background(sender, prompt):
    """Runs Claude Code CLI in the background so /cancel can stop it mid-flight."""
    try:
        res = await run_claude_cli(
            WORKSPACE, prompt,
            on_proc=lambda proc: task_registry.attach_proc(sender, proc=proc),
        )
        if res["success"]:
            await send_signal_message(sender, f"✅ Claude Code:\n\n{res['output']}")
        else:
            await send_signal_message(sender, f"❌ Claude error: {res.get('error')}")
    except asyncio.CancelledError:
        await send_signal_message(sender, "🛑 Claude Code Cancelled")
        raise
    finally:
        task_registry.finish(sender)


async def exec_cmd(sender: str, args: list[str]):
    """Runs an arbitrary shell command inside the shared workspace sandbox."""
    if not args:
        await send_signal_message(sender, "Usage: /exec <shell command>")
        return

    if task_registry.get(sender):
        await send_signal_message(sender, "⚠️ Another task is already running for you. Send /cancel to stop it first.")
        return

    shell_cmd = " ".join(args)
    await send_signal_message(sender, f"⏳ Executing: {shell_cmd}...")
    t = asyncio.create_task(run_exec_background(sender, shell_cmd))
    task_registry.start(sender, label=f"exec: {shell_cmd}", asyncio_task=t)


async def run_exec_background(sender, shell_cmd):
    """Runs the shell command in the background so /cancel can stop it mid-flight."""
    try:
        res = await run_shell_exec(
            shell_cmd, cwd=WORKSPACE,
            on_proc=lambda proc: task_registry.attach_proc(sender, proc=proc),
        )
        await send_signal_message(sender, f"🖥️ Output:\n{res['output']}")
    except asyncio.CancelledError:
        await send_signal_message(sender, f"🛑 Cancelled: {shell_cmd}")
        raise
    finally:
        task_registry.finish(sender)


async def cancel(sender: str, args: list[str]):
    """Cancels whatever background task (task/claude/exec) is running for this sender."""
    label = await task_registry.cancel(sender)
    if label is None:
        await send_signal_message(sender, "ℹ️ Nothing is currently running for you to cancel.")
    else:
        await send_signal_message(sender, f"🛑 Cancelling: {label}...")
