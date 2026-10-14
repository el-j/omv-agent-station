#!/usr/bin/env python3
"""
Signal Agent Relay Bot for OpenMediaVault & HP ProLiant Gen8.
Provides end-to-end encrypted remote command execution, autonomous coding agent dispatch (Aider/Claude Code),
Git repository synchronization, Obsidian second-brain integration, and LiteLLM gateway telemetry over Signal.
Powered by agent_station_core.
"""

import sys
import json
import asyncio
from pathlib import Path
import websockets

# Auto-resolve agent_station_core in sys.path
_bot_dir = Path(__file__).parent.resolve()
_root_dir = _bot_dir.parent.resolve()
for path_cand in [str(_bot_dir), str(_root_dir)]:
    if path_cand not in sys.path:
        sys.path.insert(0, path_cand)

from agent_station_core import logger, init_git_credentials

from core.security import is_authorized  # noqa: F401 -- re-exported for tests/tooling
from core.messaging import SIGNAL_API_URL, SIGNAL_PHONE_NUMBER, send_signal_message  # noqa: F401
from handlers import system, ai_chat, git_ops, custom_cmds, vault, topics, interactive
from handlers.upload import handle_signal_upload, MAX_UPLOAD_BYTES  # noqa: F401 -- re-exported for tests

# Command name (and alias) -> handler(sender, args) dispatch table.
_COMMAND_TABLE = {
    "start": system.start,
    "menu": system.start,
    "help": system.help_cmd,
    "status": system.status,
    "task": system.task,
    "claude": system.claude,
    "exec": system.exec_cmd,
    "cancel": system.cancel,
    "stop": system.cancel,
    "chat": ai_chat.chat,
    "gemini": ai_chat.gemini,
    "gpt4": ai_chat.gpt4,
    "models": ai_chat.models,
    "modelhelp": ai_chat.modelhelp,
    "aihelp": ai_chat.modelhelp,
    "projects": git_ops.projects,
    "clone": git_ops.clone,
    "newrepo": git_ops.newrepo,
    "create": git_ops.newrepo,
    "pull": git_ops.pull,
    "push": git_ops.push,
    "branch": git_ops.branch,
    "diff": git_ops.diff,
    "addcmd": custom_cmds.addcmd,
    "delcmd": custom_cmds.delcmd,
    "customcmds": custom_cmds.customcmds,
    "cmds": custom_cmds.customcmds,
    "aliases": custom_cmds.customcmds,
    "note": vault.note,
    "vault": vault.vault,
    "bind": topics.bind,
    "unbind": topics.unbind,
}


async def handle_signal_command(sender: str, text: str):
    """Parses and dispatches all Agent Station commands over Signal."""
    if not is_authorized(sender):
        logger.warning(f"Unauthorized Signal access attempt from sender: {sender}")
        await send_signal_message(sender, "⛔ Unauthorized access. Configure your Signal Phone Number in OMV Agent Station settings.")
        return

    text = text.strip()
    if not text:
        return

    text = interactive.rewrite_bare_github_url(text)

    if text.startswith("/"):
        text = custom_cmds.expand_shortcut(text)

    if not text.startswith("/"):
        await interactive.route_freeform_chat(sender, text)
        return

    parts = text.lstrip("/").split()
    cmd = parts[0].lower()
    args = parts[1:]

    handler = _COMMAND_TABLE.get(cmd)
    if handler:
        await handler(sender, args)


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
    """Starts the Signal bot, or idles in standby if no phone number is configured."""
    init_git_credentials()
    if not SIGNAL_PHONE_NUMBER:
        print("ℹ️ SIGNAL_PHONE_NUMBER environment variable not set. Bot in standby mode.", file=sys.stderr)
        import time
        while True:
            time.sleep(3600)
    asyncio.run(signal_event_listener())


if __name__ == "__main__":
    main()
