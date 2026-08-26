#!/usr/bin/env python3
"""
Signal Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8.
Provides end-to-end encrypted remote command execution, autonomous coding agent dispatch (Aider/Claude Code),
Git repository synchronization, Obsidian second-brain integration, and LiteLLM gateway telemetry over Signal.
Powered by agent_station_core.
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
import httpx
import websockets

# Auto-resolve agent_station_core in sys.path
_bot_dir = Path(__file__).parent.resolve()
_root_dir = _bot_dir.parent.resolve()
for path_cand in [str(_bot_dir), str(_root_dir)]:
    if path_cand not in sys.path:
        sys.path.insert(0, path_cand)

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

# Signal Environment Configuration
SIGNAL_API_URL = os.environ.get("SIGNAL_CLI_URL", "http://signal-cli:8080")
SIGNAL_PHONE_NUMBER = os.environ.get("SIGNAL_PHONE_NUMBER", "")
SIGNAL_ALLOWED_NUMBER = os.environ.get("SIGNAL_ALLOWED_PHONE_NUMBER", "")

def is_authorized(sender: str) -> bool:
    """Verifies that incoming Signal phone number matches SIGNAL_ALLOWED_NUMBER."""
    if not SIGNAL_ALLOWED_NUMBER:
        return True
    if not sender:
        return False
    return sender.strip().replace(" ", "").replace("-", "") == SIGNAL_ALLOWED_NUMBER.strip().replace(" ", "").replace("-", "")

async def send_signal_message(recipient: str, message: str):
    """Sends an end-to-end encrypted message via signal-cli REST API."""
    url = f"{SIGNAL_API_URL.rstrip('/')}/v2/send"
    payload = {
        "number": SIGNAL_PHONE_NUMBER,
        "recipients": [recipient],
        "message": message
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code not in (200, 201):
                logger.warning(f"Failed to send Signal message: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Error sending Signal message to {recipient}: {e}")

async def handle_signal_command(sender: str, text: str):
    """Parses and handles all 25 Agent Station commands over Signal."""
    if not is_authorized(sender):
        logger.warning(f"Unauthorized Signal access attempt from sender: {sender}")
        await send_signal_message(sender, "⛔ Unauthorized access. Configure your Signal Phone Number in OMV Agent Station settings.")
        return

    text = text.strip()
    if not text:
        return

    # Check for direct GitHub clone link
    if text.startswith("https://github.com/") or text.startswith("http://github.com/") or text.startswith("git@github.com:"):
        text = f"/clone {text}"

    # Expand custom shortcut commands
    if text.startswith("/"):
        parts = text.lstrip("/").split(maxsplit=1)
        cmd_name = parts[0].lower()
        passed_args = parts[1] if len(parts) > 1 else ""
        expanded = expand_custom_command(cmd_name, passed_args)
        if expanded:
            text = expanded if expanded.startswith("/") else f"/{expanded}"

    # If message doesn't start with slash in 1-on-1 chat, route to conversational AI
    if not text.startswith("/"):
        res = await query_ai_model(text, model="coder-smart")
        ans = res["answer"] if res["success"] else f"❌ AI error: {res.get('error')}"
        await send_signal_message(sender, ans)
        return

    parts = text.lstrip("/").split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ("start", "menu"):
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

    elif cmd == "help":
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

    elif cmd == "chat":
        if not args:
            await send_signal_message(sender, "Usage: /chat [-m model] <your question>")
            return
        model = "coder-smart"
        prompt = " ".join(args)
        if len(args) > 2 and args[0] in ("-m", "--model"):
            model = args[1]
            prompt = " ".join(args[2:])
        await send_signal_message(sender, f"⏳ Querying {model}...")
        res = await query_ai_model(prompt, model=model)
        ans = res["answer"] if res["success"] else f"❌ AI Query error: {res.get('error')}"
        await send_signal_message(sender, ans)

    elif cmd == "gemini":
        if not args:
            await send_signal_message(sender, "Usage: /gemini <prompt>")
            return
        res = await query_ai_model(" ".join(args), model="gemini-3.6-flash")
        ans = res["answer"] if res["success"] else f"❌ Error: {res.get('error')}"
        await send_signal_message(sender, ans)

    elif cmd == "gpt4":
        if not args:
            await send_signal_message(sender, "Usage: /gpt4 <prompt>")
            return
        res = await query_ai_model(" ".join(args), model="github-gpt-4o")
        ans = res["answer"] if res["success"] else f"❌ Error: {res.get('error')}"
        await send_signal_message(sender, ans)

    elif cmd == "models":
        models = await list_ai_models()
        model_str = "\n".join([f"• {m}" for m in models])
        await send_signal_message(sender, f"🤖 Active AI Models ({len(models)}):\n\n{model_str}\n\nRouters: coder-smart, reasoning-heavy")

    elif cmd in ("modelhelp", "aihelp"):
        await send_signal_message(sender, get_modelhelp_markdown())

    elif cmd == "projects":
        projects = list_workspace_projects()
        if not projects:
            await send_signal_message(sender, "📁 No workspace projects found.")
            return
        proj_str = "\n".join([f"• {p}" for p in projects])
        await send_signal_message(sender, f"📁 Workspace Projects ({len(projects)}):\n\n{proj_str}")

    elif cmd == "clone":
        if not args:
            await send_signal_message(sender, "Usage: /clone <git-url> [custom-folder-name]")
            return
        git_url = args[0]
        f_name = args[1] if len(args) > 1 else ""
        await send_signal_message(sender, f"⏳ Cloning {git_url}...")
        res = await clone_repository(git_url, f_name)
        if res["success"]:
            folder = res["folder_name"]
            msg = (
                f"✅ Repository Cloned & Registered as Active Project!\n\n"
                f"📁 Project: {folder}\n"
                f"💾 Path: /data/workspace/{folder}\n"
                f"📓 Obsidian Spec: /data/obsidian/Projects/{folder}/\n\n"
                f"Run tasks with: /task {folder} \"your instructions\""
            )
            await send_signal_message(sender, msg)
        else:
            await send_signal_message(sender, f"❌ Git clone failed: {res.get('error')}")

    elif cmd in ("newrepo", "create"):
        if not args:
            await send_signal_message(sender, "Usage: /newrepo <repo-name> [description]")
            return
        repo_name = args[0]
        desc = " ".join(args[1:]) if len(args) > 1 else ""
        await send_signal_message(sender, f"⏳ Creating GitHub repository {repo_name}...")
        res = await create_new_repository(repo_name, desc)
        if res["success"]:
            msg = (
                f"✅ New GitHub Repository Created!\n\n"
                f"📁 Project: {res['repo_name']}\n"
                f"🔗 URL: {res.get('html_url')}\n"
                f"💾 Path: /data/workspace/{res['repo_name']}"
            )
            await send_signal_message(sender, msg)
        else:
            await send_signal_message(sender, f"❌ Failed to create repo: {res.get('error')}")

    elif cmd == "pull":
        proj, _ = resolve_project_context_raw(sender, None, args, WORKSPACE)
        if not proj:
            await send_signal_message(sender, "Usage: /pull [project-name]")
            return
        await send_signal_message(sender, f"⏳ Pulling latest changes for {proj}...")
        res = await git_pull_repo(proj)
        if res["success"]:
            await send_signal_message(sender, f"✅ Git Pull ({proj}):\n{res['output']}")
        else:
            await send_signal_message(sender, f"❌ Git pull failed: {res.get('error')}")

    elif cmd == "push":
        proj, remaining = resolve_project_context_raw(sender, None, args, WORKSPACE)
        if not proj:
            await send_signal_message(sender, "Usage: /push [project-name] [branch]")
            return
        branch = remaining[0] if remaining else "main"
        await send_signal_message(sender, f"⏳ Pushing {proj} to {branch}...")
        res = await git_push_repo(proj, branch)
        if res["success"]:
            await send_signal_message(sender, f"✅ Git Push ({proj} -> {branch}):\n{res['output']}")
        else:
            await send_signal_message(sender, f"❌ Git push failed: {res.get('error')}")

    elif cmd == "branch":
        proj, remaining = resolve_project_context_raw(sender, None, args, WORKSPACE)
        if not proj:
            await send_signal_message(sender, "Usage: /branch [project-name] [new-branch]")
            return
        p_dir = sanitize_project_path(WORKSPACE, proj)
        if not p_dir or not (p_dir / ".git").exists():
            await send_signal_message(sender, f"❌ `{proj}` is not a valid git repository.")
            return
        if not remaining:
            res = await run_shell_exec("git branch -a", cwd=p_dir)
            await send_signal_message(sender, f"🌿 Branches for {proj}:\n{res['output']}")
        else:
            clean_b = sanitize_branch_name(remaining[0])
            if not clean_b:
                await send_signal_message(sender, "❌ Invalid branch name format.")
                return
            res = await run_shell_exec(f"git checkout -B {clean_b}", cwd=p_dir)
            if res["success"]:
                await send_signal_message(sender, f"🌿 Switched to branch {clean_b} in project {proj}.")
            else:
                await send_signal_message(sender, f"❌ Branch checkout failed: {res.get('output')}")

    elif cmd == "diff":
        proj, _ = resolve_project_context_raw(sender, None, args, WORKSPACE)
        if not proj:
            await send_signal_message(sender, "Usage: /diff [project-name]")
            return
        res = await git_diff_repo(proj)
        if res["success"]:
            diff_text = res["diff"] or "(No uncommitted diff)"
            await send_signal_message(sender, f"🔍 Git Diff ({proj}):\n{diff_text}")
        else:
            await send_signal_message(sender, f"❌ Error: {res.get('error')}")

    elif cmd == "task":
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

    elif cmd == "claude":
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

    elif cmd == "exec":
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

    elif cmd in ("cancel", "stop"):
        label = await task_registry.cancel(sender)
        if label is None:
            await send_signal_message(sender, "ℹ️ Nothing is currently running for you to cancel.")
        else:
            await send_signal_message(sender, f"🛑 Cancelling: {label}...")

    elif cmd == "bind":
        if not args:
            current_bound = get_bound_project(sender, None)
            status = f"Currently bound to: {current_bound}" if current_bound else "Not bound to any project."
            await send_signal_message(sender, f"🧵 Binding Status\n\n• {status}\n\nTo bind: /bind <project-name>\nTo unbind: /unbind")
            return
        project_name = args[0]
        p_dir = sanitize_project_path(WORKSPACE, project_name)
        if not p_dir or not p_dir.exists():
            await send_signal_message(sender, f"❌ Project {project_name} not found in /data/workspace.")
            return
        set_bound_project(sender, None, project_name)
        await send_signal_message(sender, f"✅ Bound! All commands and file uploads now target project {project_name}.")

    elif cmd == "unbind":
        remove_bound_project(sender, None)
        await send_signal_message(sender, "✅ Unbound project context.")

    elif cmd == "status":
        metrics = get_system_status()
        await send_signal_message(
            sender,
            f"🖥️ OMV Server Status\n\n"
            f"⏱️ Uptime: {metrics['uptime']}\n"
            f"💾 Disk Space: {metrics['disk']}\n\n"
            f"🧵 Active Tmux Sessions:\n{metrics['tmux']}"
        )

    elif cmd == "note":
        if not args:
            await send_signal_message(sender, "Usage: /note <Title> | <Content>")
            return
        raw = " ".join(args)
        if "|" in raw:
            title, content = raw.split("|", 1)
        else:
            title = f"Quick Note {datetime.now().strftime('%Y-%m-%d %H%M')}"
            content = raw
        res = save_obsidian_note(title.strip(), content.strip())
        if res["success"]:
            await send_signal_message(sender, f"✅ Note Saved to Obsidian: {res['path']}")
        else:
            await send_signal_message(sender, f"❌ Failed to save note: {res.get('error')}")

    elif cmd == "vault":
        res = list_vault_notes()
        if res["success"]:
            recent_str = "\n".join([f"• {f}" for f in res["recent"]]) if res["recent"] else "No notes found."
            await send_signal_message(sender, f"📓 Obsidian Vault ({res['total_notes']} notes):\n\n{recent_str}")
        else:
            await send_signal_message(sender, f"❌ Error: {res.get('error')}")

    elif cmd == "addcmd":
        if len(args) < 2:
            await send_signal_message(sender, "Usage: /addcmd <command-name> <command-template>")
            return
        name = args[0]
        template = " ".join(args[1:])
        san_name = sanitize_cmd_name(name)
        if not san_name:
            await send_signal_message(sender, "❌ Invalid command name format.")
            return
        cmds = load_custom_commands()
        cmds[san_name] = template
        save_custom_commands(cmds)
        await send_signal_message(sender, f"✅ Custom Shortcut Registered: /{san_name} ➔ {template}")

    elif cmd == "delcmd":
        if not args:
            await send_signal_message(sender, "Usage: /delcmd <command-name>")
            return
        san_name = sanitize_cmd_name(args[0])
        if not san_name:
            await send_signal_message(sender, "Usage: /delcmd <command-name>")
            return
        cmds = load_custom_commands()
        if san_name in cmds:
            del cmds[san_name]
            save_custom_commands(cmds)
            await send_signal_message(sender, f"✅ Deleted shortcut /{san_name}.")
        else:
            await send_signal_message(sender, f"⚠️ Shortcut /{san_name} not found.")

    elif cmd in ("customcmds", "cmds", "aliases"):
        cmds = load_custom_commands()
        if not cmds:
            await send_signal_message(sender, "📋 No custom shortcuts configured yet. Create one with /addcmd.")
            return
        lines = [f"• /{k} ➔ {v}" for k, v in sorted(cmds.items())]
        await send_signal_message(sender, f"⚡ Custom Shortcuts ({len(cmds)}):\n\n" + "\n".join(lines))

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

async def run_claude_background(sender, prompt):
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

async def run_exec_background(sender, shell_cmd):
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

async def download_signal_attachment(attachment_id: str) -> bytes:
    """Downloads a received attachment's raw bytes from signal-cli's REST API."""
    url = f"{SIGNAL_API_URL.rstrip('/')}/v1/attachments/{attachment_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content

async def handle_signal_upload(sender: str, attachment: dict, caption: str | None):
    """Entry point: any incoming message with an attachment is treated as a repo upload."""
    if not is_authorized(sender):
        logger.warning(f"Unauthorized Signal upload attempt from sender: {sender}")
        await send_signal_message(sender, "⛔ Unauthorized access. Configure your Signal Phone Number in OMV Agent Station settings.")
        return

    attachment_id = attachment.get("id")
    if not attachment_id:
        return
    size = attachment.get("size") or 0
    filename = attachment.get("filename") or f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if size and size > MAX_UPLOAD_BYTES:
        await send_signal_message(sender, f"❌ File is {size / 1024 / 1024:.1f} MB -- max upload size is {MAX_UPLOAD_BYTES // 1024 // 1024} MB.")
        return

    project_override, path_hint = parse_upload_caption(caption)
    project_name = project_override or get_bound_project(sender, None)
    if not project_name:
        await send_signal_message(sender, "❌ No project bound. Use /bind <project> first, then resend the file.")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists():
        await send_signal_message(sender, f"❌ Project {project_name} does not exist in /data/workspace.")
        return
    if not (project_dir / ".git").exists():
        await send_signal_message(sender, f"❌ Project {project_name} is not a git repository.")
        return

    relative_path_str = path_hint or f"uploads/{filename}"
    target_path = sanitize_relative_path(project_dir, relative_path_str)
    if not target_path:
        await send_signal_message(sender, f"❌ Invalid target path {relative_path_str} -- must stay inside the project and can't touch .git/.")
        return

    if task_registry.get(sender):
        await send_signal_message(sender, "⚠️ Another task is already running for you. Send /cancel to stop it first.")
        return

    await send_signal_message(
        sender,
        f"📤 Uploading to repository\n\n"
        f"Project: {project_name}\n"
        f"Path: {target_path.relative_to(project_dir)}\n\n"
        f"⏳ Downloading from Signal..."
    )
    t = asyncio.create_task(run_signal_upload_background(sender, attachment_id, project_dir, target_path))
    task_registry.start(sender, label=f"upload: {target_path.name}", asyncio_task=t)

async def run_signal_upload_background(sender: str, attachment_id: str, project_dir: Path, target_path: Path):
    try:
        file_bytes = await download_signal_attachment(attachment_id)
        res = await run_repo_upload(
            project_dir, target_path, file_bytes,
            f"chore(upload): add {target_path.relative_to(project_dir)} via Signal upload",
            on_proc=lambda proc: task_registry.attach_proc(sender, proc=proc),
        )
        if not res["success"]:
            await send_signal_message(sender, f"❌ {res['error']}")
            return
        reply = f"✅ File Uploaded\n\nPath: {res['relative_path']}\nBranch: {res['branch']}\n"
        compare_url = build_compare_url(res["owner_repo"], res["base_branch"], res["branch"])
        if compare_url:
            reply += f"\n🔗 {compare_url}"
        await send_signal_message(sender, reply)
    except asyncio.CancelledError:
        await send_signal_message(sender, f"🛑 Upload Cancelled\n\nPath: {target_path.name}")
        raise
    except Exception as e:
        logger.error(f"Error in Signal file upload: {e}", exc_info=True)
        await send_signal_message(sender, f"❌ Upload error: {e}")
    finally:
        task_registry.finish(sender)

async def signal_event_listener():
    """Connects to signal-cli JSON-RPC WebSocket stream to listen for incoming messages."""
    ws_url = SIGNAL_API_URL.replace("http://", "ws://").replace("https://", "wss://").rstrip("/") + "/v1/receive/" + SIGNAL_PHONE_NUMBER
    logger.info(f"Connecting to Signal WebSocket stream: {ws_url}")
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                logger.info("Connected to Signal WebSocket stream.")
                async for raw_msg in ws:
                    try:
                        data = json.loads(raw_msg)
                        envelope = data.get("envelope", {})
                        sender = envelope.get("source") or envelope.get("sourceNumber")
                        data_msg = envelope.get("dataMessage", {})
                        text = data_msg.get("message")
                        attachments = data_msg.get("attachments") or []
                        if sender and attachments:
                            asyncio.create_task(handle_signal_upload(sender, attachments[0], text))
                        elif sender and text:
                            asyncio.create_task(handle_signal_command(sender, text))
                    except Exception as parse_err:
                        logger.warning(f"Error parsing Signal message payload: {parse_err}")
        except Exception as e:
            logger.warning(f"Signal WebSocket disconnected: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

def main():
    init_git_credentials()
    if not SIGNAL_PHONE_NUMBER:
        print("ℹ️ SIGNAL_PHONE_NUMBER environment variable not set. Bot in standby mode.", file=sys.stderr)
        import time
        while True:
            time.sleep(3600)
    asyncio.run(signal_event_listener())

if __name__ == "__main__":
    main()
