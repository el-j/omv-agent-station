"""
Security, Input Sanitization, and Authorization Guards.
Protects against path traversal attacks, command injection, and unauthorized message execution.
"""

import re
from pathlib import Path
from telegram import Update
from .config import ALLOWED_USER_ID, logger

def authorized(update: Update) -> bool:
    """Ensure only the configured user can communicate with the bot."""
    if not ALLOWED_USER_ID:
        return True
    if not update.effective_user:
        return False
    user_id = str(update.effective_user.id)
    return user_id == str(ALLOWED_USER_ID)

async def check_auth(update: Update) -> bool:
    """Verifies user authorization and replies with an error if unauthorized."""
    if not authorized(update):
        if update.effective_user:
            logger.warning(f"Unauthorized access attempt from user_id: {update.effective_user.id} (@{update.effective_user.username})")
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ Unauthorized access.\n\n"
                "Please configure your personal numeric Telegram User ID in OMV Services -> Agent Station -> Chat & Messenger."
            )
        return False
    return True

def sanitize_project_path(workspace: Path, project_name: str) -> Path | None:
    """Validates that project_name resolves strictly within the workspace root to prevent traversal."""
    if not project_name or ".." in project_name or project_name.startswith(("/", "\\", "-")):
        return None
    try:
        clean_name = project_name.strip().strip("./")
        if not clean_name or clean_name.startswith("-"):
            return None
        target = (workspace / clean_name).resolve()
        workspace_resolved = workspace.resolve()
        if workspace_resolved in target.parents or target == workspace_resolved:
            return target
        return None
    except Exception:
        return None

def sanitize_repo_name(name: str) -> str | None:
    """Validates repository name for alphanumeric and safe separator chars."""
    if not name:
        return None
    name = name.strip()
    if name.startswith(("-", ".")) or ".." in name or "/" in name or "\\" in name:
        return None
    if re.match(r"^[a-zA-Z0-9_.-]+$", name):
        return name
    return None

def sanitize_branch_name(branch: str) -> str | None:
    """Validates git branch names to prevent argument injection."""
    if not branch:
        return None
    branch = branch.strip()
    if branch.startswith("-") or ".." in branch or "\\" in branch or "@{" in branch:
        return None
    if re.match(r"^[a-zA-Z0-9_./-]+$", branch):
        return branch
    return None

def sanitize_cmd_name(name: str) -> str | None:
    """Validates custom command names (alphanumeric and underscores only)."""
    if not name:
        return None
    name = name.strip().lstrip("/").lower()
    if re.match(r"^[a-z0-9_]{1,32}$", name):
        return name
    return None

def sanitize_relative_path(base: Path, rel_path: str) -> Path | None:
    """Validates a caption-provided relative file path resolves strictly within
    base, blocking traversal and any write access into the repo's own .git
    directory (a path there is a code-execution vector via git hooks)."""
    if not rel_path:
        return None
    rel_path = rel_path.strip()
    if not rel_path or rel_path.startswith(("/", "\\")):
        return None
    parts = Path(rel_path).parts
    if not parts or ".." in parts or ".git" in parts:
        return None
    try:
        base_resolved = base.resolve()
        target = (base_resolved / rel_path).resolve()
        if target == base_resolved or base_resolved not in target.parents:
            return None
        return target
    except Exception:
        return None

def sanitize_git_url(url: str) -> str | None:
    """Validates git URL to prevent command argument injection (e.g. leading dashes)."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("-"):
        return None
    pattern = r"^(https?|git|ssh)://[^\s/$.?#].[^\s]*$|^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(\.git)?$"
    if re.match(pattern, url):
        return url
    return None
