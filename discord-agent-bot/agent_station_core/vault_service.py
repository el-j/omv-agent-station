"""
Obsidian Second-Brain and Markdown Spec Service.
Captures notes into inbox and manages project specifications.
"""

from datetime import datetime
from .config import OBSIDIAN_VAULT, logger

def save_obsidian_note(title: str, content: str, extra_tags: list[str] | None = None) -> dict:
    """Saves a structured markdown note with frontmatter to the Obsidian vault Inbox.

    extra_tags (e.g. from ai_service.suggest_tags) are merged in after the
    fixed base tags and deduplicated; omitting them reproduces the exact
    frontmatter this function has always written."""
    try:
        note_dir = OBSIDIAN_VAULT / "Inbox"
        note_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or "Quick Note"
        note_file = note_dir / f"{safe_title}.md"

        all_tags = list(dict.fromkeys(["quick-capture", "second-brain", *(extra_tags or [])]))
        tags_str = ", ".join(all_tags)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note_body = (
            f"---\n"
            f"date: {now_str}\n"
            f"author: Agent Station\n"
            f"tags: [{tags_str}]\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"{content}\n"
        )
        note_file.write_text(note_body, encoding="utf-8")
        return {"success": True, "path": str(note_file.relative_to(OBSIDIAN_VAULT))}
    except Exception as e:
        logger.error(f"Failed to save obsidian note: {e}")
        return {"success": False, "error": str(e)}

def list_vault_notes(limit: int = 6) -> dict:
    """Lists recent notes in the Obsidian vault."""
    if not OBSIDIAN_VAULT.exists():
        return {"success": False, "error": "Obsidian vault not mounted."}

    md_files = list(OBSIDIAN_VAULT.glob("**/*.md"))
    recent = sorted(md_files, key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    return {
        "success": True,
        "total_notes": len(md_files),
        "recent": [str(f.relative_to(OBSIDIAN_VAULT)) for f in recent]
    }

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
