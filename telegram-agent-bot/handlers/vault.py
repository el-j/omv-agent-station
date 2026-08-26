"""
Obsidian Second-Brain and Syncthing Note Vault Handlers.
Captures notes and provisions project-spec markdown files with bi-directional sync.
"""

from datetime import datetime
from telegram import Update, ForceReply
from telegram.ext import ContextTypes
from core.config import OBSIDIAN_VAULT, logger
from core.security import check_auth

async def vault_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists recent Obsidian notes and specs."""
    if not await check_auth(update):
        return
    if not OBSIDIAN_VAULT.exists():
        await update.effective_message.reply_text("📓 Obsidian vault not mounted.")
        return

    md_files = list(OBSIDIAN_VAULT.glob("**/*.md"))
    recent = sorted(md_files, key=lambda f: f.stat().st_mtime, reverse=True)[:6]

    recent_str = "\n".join([f"• `{f.relative_to(OBSIDIAN_VAULT)}`" for f in recent]) if recent else "No notes found."
    await update.effective_message.reply_text(
        f"📓 *Obsidian Second Brain Vault:*\n\n"
        f"📊 Total notes: `{len(md_files)}`\n"
        f"🔄 Sync: Syncthing (Port 8384)\n\n"
        f"🕒 *Recently Modified Notes:*\n{recent_str}",
        parse_mode="Markdown"
    )

async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Appends or creates a markdown note inside the Obsidian vault."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "Usage: `/note <Title> | <Content>`\n\nExample:\n`/note API Architecture | Use FastAPI and Redis`",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="Title | Your note content..."
            )
        )
        return

    raw = " ".join(context.args)
    if "|" in raw:
        title_part, content_part = raw.split("|", 1)
        title = title_part.strip()
        content = content_part.strip()
    else:
        title = f"Quick Note {datetime.now().strftime('%Y-%m-%d %H%M')}"
        content = raw.strip()

    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or "Quick Note"
    note_dir = OBSIDIAN_VAULT / "Inbox"
    try:
        note_dir.mkdir(parents=True, exist_ok=True)
        note_file = note_dir / f"{safe_title}.md"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note_body = (
            f"---\n"
            f"date: {now_str}\n"
            f"author: Telegram Bot\n"
            f"tags: [telegram, quick-capture]\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"{content}\n"
        )
        note_file.write_text(note_body, encoding="utf-8")

        await update.effective_message.reply_text(
            f"✅ *Note Saved to Obsidian Vault!*\n\n"
            f"📄 `{note_file.relative_to(OBSIDIAN_VAULT)}`\n"
            f"🔄 Synchronized via Syncthing to your devices.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to write note: {e}")
        await update.effective_message.reply_text(f"❌ Failed to write note: {e}")

def init_obsidian_project_spec(folder_name: str, git_url: str):
    """Provisions a standardized project specification markdown document inside Obsidian."""
    try:
        obsidian_proj = OBSIDIAN_VAULT / "Projects" / folder_name
        obsidian_proj.mkdir(parents=True, exist_ok=True)
        spec_file = obsidian_proj / "project-spec.md"
        if not spec_file.exists():
            spec_content = (
                f"# Project: {folder_name}\n\n"
                f"- **Git Remote:** `{git_url}`\n"
                f"- **Cloned On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"- **Workspace Path:** `/data/workspace/{folder_name}`\n\n"
                f"## 📋 Active Tasks & Notes\n"
                f"- [ ] Initial codebase review & test suite execution\n\n"
                f"## 🤖 Agent Execution History\n"
            )
            spec_file.write_text(spec_content, encoding="utf-8")
    except Exception as oe:
        logger.warning(f"Could not initialize Obsidian project note: {oe}")
