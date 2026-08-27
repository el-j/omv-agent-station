"""
File Upload to GitHub Handler.
Lets a user send a Document or Photo directly to the bot and have it committed
to the bound project's repository on a dedicated review branch, never the
current/default branch directly.
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from core.config import WORKSPACE, GIT_BIN, logger
from core.security import check_auth, sanitize_project_path, sanitize_relative_path
from core import task_registry
from .topics import get_bound_project

# Telegram's Bot API refuses to hand back files larger than this via getFile.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def parse_upload_caption(caption: str | None) -> tuple[str | None, str | None]:
    """Parses a caption of the form '<project>: <path>' or bare '<path>'.
    Returns (project_override, path); either may be None."""
    if not caption:
        return None, None
    caption = caption.strip()
    if not caption:
        return None, None
    if ":" in caption:
        maybe_project, _, maybe_path = caption.partition(":")
        maybe_project = maybe_project.strip()
        maybe_path = maybe_path.strip()
        if maybe_project and "/" not in maybe_project and maybe_path:
            return maybe_project, maybe_path
    return None, caption


def parse_github_owner_repo(remote_url: str) -> tuple[str, str] | None:
    """Extracts (owner, repo) from a github.com https or ssh remote URL."""
    match = re.match(
        r"^(?:https://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$",
        remote_url.strip(),
    )
    if not match:
        return None
    return match.group(1), match.group(2)


async def upload_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: any Document or Photo message is treated as a repo upload."""
    if not await check_auth(update):
        return

    msg = update.effective_message
    document = msg.document
    photo = msg.photo[-1] if msg.photo else None
    if not document and not photo:
        return

    chat_id = update.effective_chat.id if update.effective_chat else 0
    thread_id = msg.message_thread_id

    project_override, path_hint = parse_upload_caption(msg.caption)
    project_name = project_override or get_bound_project(chat_id, thread_id)
    if not project_name:
        await msg.reply_text(
            "❌ No project bound to this chat/topic.\n\n"
            "Use `/bind <project>` first, then resend the file.",
            parse_mode="Markdown",
        )
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists():
        await msg.reply_text(f"❌ Project `{project_name}` does not exist in `/data/workspace`.", parse_mode="Markdown")
        return
    if not (project_dir / ".git").exists():
        await msg.reply_text(f"❌ Project `{project_name}` is not a git repository.", parse_mode="Markdown")
        return

    file_id = document.file_id if document else photo.file_id
    file_size = (document.file_size if document else photo.file_size) or 0
    if file_size > MAX_UPLOAD_BYTES:
        await msg.reply_text(
            f"❌ File is {file_size / 1024 / 1024:.1f} MB -- Telegram bots can only download files up to 20 MB.",
            parse_mode="Markdown",
        )
        return

    if document:
        default_name = document.file_name or f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    else:
        default_name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    relative_path_str = path_hint or f"uploads/{default_name}"

    target_path = sanitize_relative_path(project_dir, relative_path_str)
    if not target_path:
        await msg.reply_text(
            f"❌ Invalid target path `{relative_path_str}` -- must stay inside the project and can't touch `.git/`.",
            parse_mode="Markdown",
        )
        return

    chat_scope_id, thread_scope_id = chat_id, thread_id
    if task_registry.get(chat_scope_id, thread_scope_id):
        await msg.reply_text(
            "⚠️ Another task is already running here. Use `/cancel` to stop it first.",
            parse_mode="Markdown",
        )
        return

    status_msg = await msg.reply_text(
        f"📤 *Uploading to repository*\n\n"
        f"📁 Project: `{project_name}`\n"
        f"📄 Path: `{target_path.relative_to(project_dir)}`\n\n"
        f"⏳ Downloading from Telegram...",
        parse_mode="Markdown",
    )

    t = asyncio.create_task(
        run_upload_task(chat_scope_id, thread_scope_id, status_msg, context, file_id, project_dir, target_path)
    )
    task_registry.start(chat_scope_id, thread_scope_id, label=f"upload: {target_path.name}", asyncio_task=t)


async def run_upload_task(
    chat_id: int,
    thread_id: int | None,
    status_msg,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    project_dir: Path,
    target_path: Path,
):
    """Downloads the file, writes it into the repo, and pushes it on a new
    upload/<timestamp> branch -- never the project's current branch."""
    try:
        tg_file = await context.bot.get_file(file_id)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        await tg_file.download_to_drive(custom_path=str(target_path))

        relative_path = target_path.relative_to(project_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        upload_branch = f"upload/{timestamp}"

        base_branch_proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "rev-parse", "--abbrev-ref", "HEAD",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        task_registry.attach_proc(chat_id, thread_id, base_branch_proc)
        base_out, _ = await base_branch_proc.communicate()
        base_branch = base_out.decode("utf-8", errors="replace").strip() or "main"

        checkout_proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "checkout", "-B", upload_branch, cwd=str(project_dir)
        )
        task_registry.attach_proc(chat_id, thread_id, checkout_proc)
        await checkout_proc.communicate()

        add_proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "add", str(relative_path), cwd=str(project_dir)
        )
        task_registry.attach_proc(chat_id, thread_id, add_proc)
        await add_proc.communicate()

        commit_proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "commit", "-m", f"chore(upload): add {relative_path} via Telegram upload",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        task_registry.attach_proc(chat_id, thread_id, commit_proc)
        commit_out, commit_err = await commit_proc.communicate()

        if commit_proc.returncode != 0:
            detail = (commit_out + commit_err).decode("utf-8", errors="replace").strip()
            await status_msg.edit_text(f"❌ Nothing to commit or commit failed:\n```\n{detail[:1500]}\n```", parse_mode="Markdown")
            return

        push_proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "push", "-u", "origin", upload_branch,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        task_registry.attach_proc(chat_id, thread_id, push_proc)
        push_out, push_err = await push_proc.communicate()

        if push_proc.returncode != 0:
            detail = (push_out + push_err).decode("utf-8", errors="replace").strip()
            await status_msg.edit_text(f"❌ Push failed:\n```\n{detail[:1500]}\n```", parse_mode="Markdown")
            return

        remote_proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "remote", "get-url", "origin",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        remote_out, _ = await remote_proc.communicate()
        owner_repo = parse_github_owner_repo(remote_out.decode("utf-8", errors="replace"))

        reply = (
            f"✅ *File Uploaded*\n\n"
            f"📄 Path: `{relative_path}`\n"
            f"🌿 Branch: `{upload_branch}`\n"
        )
        if owner_repo:
            owner, repo = owner_repo
            compare_url = f"https://github.com/{owner}/{repo}/compare/{base_branch}...{upload_branch}?expand=1"
            reply += f"\n🔗 [Open compare / create PR]({compare_url})"
        await status_msg.edit_text(reply, parse_mode="Markdown", disable_web_page_preview=True)
    except asyncio.CancelledError:
        await status_msg.edit_text(f"🛑 *Upload Cancelled*\n\n📄 Path: `{target_path.name}`", parse_mode="Markdown")
        raise
    except Exception as e:
        logger.error(f"Error in file upload: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Upload error: {e}")
    finally:
        task_registry.finish(chat_id, thread_id)
