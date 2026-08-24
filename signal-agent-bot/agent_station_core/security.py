"""
Security, Input Sanitization, and Path Traversal Guards.
Single-source-of-truth validation functions protecting all messenger interfaces.
"""

import re
from pathlib import Path

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
