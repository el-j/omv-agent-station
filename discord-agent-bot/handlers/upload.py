"""
File Upload to GitHub (parity with Telegram's handlers/upload.py).
Any message with an attachment is treated as a commit-to-repo request against
the channel's bound project, landing on its own review branch.
"""

import asyncio

import discord

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
from core.security import is_authorized, channel_scope


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


async def run_discord_upload_background(scope, status_msg, attachment, project_dir, target_path):
    """Downloads the attachment and commits it on a new review branch in the background."""
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
