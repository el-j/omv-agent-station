"""
File Upload to GitHub Service.
Shared by the Discord and Signal bots: takes bytes already downloaded from the
messenger platform and commits them into a bound project's repo on a new
review branch, never the project's current/default branch directly.

telegram-agent-bot/handlers/upload.py implements the same caption-parsing and
git-flow logic independently -- it predates this shared package and has its
own tested copy, so it isn't migrated here to avoid touching already-verified
code for a purely cosmetic dedupe.
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .config import GIT_BIN, logger

# Deliberate shared cap across all three bots, not a platform-imposed limit.
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


async def run_repo_upload(
    project_dir: Path,
    target_path: Path,
    file_bytes: bytes,
    commit_message: str,
    on_proc: Optional[Callable] = None,
) -> dict:
    """Writes file_bytes to target_path, then checkout -B/add/commit/push on a
    new upload/<timestamp> branch. Returns a result dict with success, branch,
    base_branch, relative_path, owner_repo (tuple or None), and error."""
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(file_bytes)

        relative_path = target_path.relative_to(project_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        upload_branch = f"upload/{timestamp}"

        async def run_git(*args, capture=False):
            proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
                GIT_BIN, *args,
                cwd=str(project_dir),
                stdout=asyncio.subprocess.PIPE if capture else None,
                stderr=asyncio.subprocess.PIPE if capture else None,
            )
            if on_proc:
                on_proc(proc)
            out, err = await proc.communicate()
            return proc, (out or b""), (err or b"")

        base_proc, base_out, _ = await run_git("rev-parse", "--abbrev-ref", "HEAD", capture=True)
        base_branch = base_out.decode("utf-8", errors="replace").strip() or "main"

        await run_git("checkout", "-B", upload_branch)
        await run_git("add", str(relative_path))

        commit_proc, commit_out, commit_err = await run_git(
            "commit", "-m", commit_message, capture=True
        )
        if commit_proc.returncode != 0:
            detail = (commit_out + commit_err).decode("utf-8", errors="replace").strip()
            return {"success": False, "error": f"Nothing to commit or commit failed:\n{detail[:1500]}"}

        push_proc, push_out, push_err = await run_git(
            "push", "-u", "origin", upload_branch, capture=True
        )
        if push_proc.returncode != 0:
            detail = (push_out + push_err).decode("utf-8", errors="replace").strip()
            return {"success": False, "error": f"Push failed:\n{detail[:1500]}"}

        _, remote_out, _ = await run_git("remote", "get-url", "origin", capture=True)
        owner_repo = parse_github_owner_repo(remote_out.decode("utf-8", errors="replace"))

        return {
            "success": True,
            "branch": upload_branch,
            "base_branch": base_branch,
            "relative_path": str(relative_path),
            "owner_repo": owner_repo,
        }
    except Exception as e:
        logger.error(f"Error in repo upload: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def build_compare_url(owner_repo: tuple[str, str] | None, base_branch: str, upload_branch: str) -> str | None:
    """Builds a GitHub compare/PR-creation link, or None if the remote isn't GitHub."""
    if not owner_repo:
        return None
    owner, repo = owner_repo
    return f"https://github.com/{owner}/{repo}/compare/{base_branch}...{upload_branch}?expand=1"
