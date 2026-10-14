"""
File Upload to GitHub (parity with Telegram's handlers/upload.py).
Any incoming Signal attachment is treated as a commit-to-repo request against
the sender's bound project, landing on its own review branch.
"""

import asyncio
from datetime import datetime

import httpx

from agent_station_core import (
    WORKSPACE,
    task_registry,
    logger,
    sanitize_project_path,
    sanitize_relative_path,
    get_bound_project,
    MAX_UPLOAD_BYTES,
    parse_upload_caption,
    run_repo_upload,
    build_compare_url,
)
from core.security import is_authorized
from core.messaging import SIGNAL_API_URL, send_signal_message


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


async def run_signal_upload_background(sender: str, attachment_id: str, project_dir, target_path):
    """Downloads the attachment and commits it on a new review branch in the background."""
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
