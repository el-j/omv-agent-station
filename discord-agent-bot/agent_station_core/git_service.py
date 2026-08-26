"""
Git Version Control and Repository Management Service.
Unified business logic for repo creation, PAT cloning, branch switching, diffing, pushing, and pulling.
"""

import asyncio
import subprocess  # nosec B404
from datetime import datetime
import httpx
from .config import (
    GIT_BIN,
    GIT_AUTHOR_NAME,
    GIT_AUTHOR_EMAIL,
    GITHUB_TOKEN,
    GITLAB_TOKEN,
    BITBUCKET_USER,
    BITBUCKET_TOKEN,
    WORKSPACE,
    logger,
)
from .security import sanitize_project_path, sanitize_repo_name, sanitize_branch_name, sanitize_git_url
from .vault_service import init_obsidian_project_spec

def init_git_credentials():
    """Configures global git identity and automated URL rewrites with Personal Access Tokens."""
    try:
        subprocess.run([GIT_BIN, "config", "--global", "user.name", GIT_AUTHOR_NAME], check=True)  # nosec B603,B607
        subprocess.run([GIT_BIN, "config", "--global", "user.email", GIT_AUTHOR_EMAIL], check=True)  # nosec B603,B607
        subprocess.run([GIT_BIN, "config", "--global", "init.defaultBranch", "main"], check=True)  # nosec B603,B607

        if GITHUB_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://x-access-token:{GITHUB_TOKEN}@github.com/.insteadOf",
                "https://github.com/"
            ], check=True)
            logger.info("Configured automated git auth for GitHub.")

        if GITLAB_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://oauth2:{GITLAB_TOKEN}@gitlab.com/.insteadOf",
                "https://gitlab.com/"
            ], check=True)
            logger.info("Configured automated git auth for GitLab.")

        if BITBUCKET_USER and BITBUCKET_TOKEN:
            subprocess.run([  # nosec B603,B607
                GIT_BIN, "config", "--global",
                f"url.https://{BITBUCKET_USER}:{BITBUCKET_TOKEN}@bitbucket.org/.insteadOf",
                "https://bitbucket.org/"
            ], check=True)
            logger.info("Configured automated git auth for Bitbucket.")
    except Exception as e:
        logger.warning(f"Could not configure global git credentials: {e}")

async def clone_repository(raw_git_url: str, custom_folder: str = "") -> dict:
    """Clones a remote repository, configures git author, and initializes Obsidian specs."""
    git_url = sanitize_git_url(raw_git_url)
    if not git_url:
        return {"success": False, "error": "Invalid git URL format."}

    folder_name = custom_folder.strip() if custom_folder else git_url.rstrip("/").split("/")[-1].replace(".git", "")
    target_dir = sanitize_project_path(WORKSPACE, folder_name)
    if not target_dir:
        return {"success": False, "error": "Invalid folder name path resolution."}

    if target_dir.exists():
        return {"success": False, "error": f"Destination folder `{folder_name}` already exists in `/data/workspace`."}

    clone_target_url = git_url
    if GITHUB_TOKEN and "github.com" in git_url and not git_url.startswith("git@"):
        clean_http = git_url.replace("https://", "").replace("http://", "")
        clone_target_url = f"https://x-access-token:{GITHUB_TOKEN}@{clean_http}"

    try:
        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "clone", "--", clone_target_url, str(target_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await asyncio.create_subprocess_exec(GIT_BIN, "config", "user.name", GIT_AUTHOR_NAME, cwd=str(target_dir))
            await asyncio.create_subprocess_exec(GIT_BIN, "config", "user.email", GIT_AUTHOR_EMAIL, cwd=str(target_dir))

            # Initialize Obsidian Spec
            init_obsidian_project_spec(folder_name, git_url)

            return {
                "success": True,
                "folder_name": folder_name,
                "git_url": git_url,
                "target_dir": target_dir
            }
        else:
            return {"success": False, "error": stderr.decode("utf-8", errors="replace")}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def create_new_repository(repo_name_raw: str, description: str = "") -> dict:
    """Creates a remote repository on GitHub and initializes local git workspace."""
    repo_name = sanitize_repo_name(repo_name_raw)
    if not repo_name:
        return {"success": False, "error": "Invalid repository name format."}

    target_dir = sanitize_project_path(WORKSPACE, repo_name)
    if not target_dir or target_dir.exists():
        return {"success": False, "error": f"Directory `{repo_name}` already exists or path invalid."}

    if not GITHUB_TOKEN:
        return {"success": False, "error": "GITHUB_TOKEN is not configured in Agent Station settings."}

    desc = description.strip() if description else f"Project {repo_name} created with OMV Agent Station"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.github.com/user/repos",
                headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "OMV-Agent-Station"
                },
                json={"name": repo_name, "description": desc, "private": True, "auto_init": False}
            )
            if resp.status_code not in (200, 201):
                return {"success": False, "error": f"GitHub API error ({resp.status_code}): {resp.text[:400]}"}

            repo_data = resp.json()
            html_url = repo_data.get("html_url")
            clone_url = repo_data.get("clone_url")
            owner = repo_data.get("owner", {}).get("login", "")

        target_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.create_subprocess_exec(GIT_BIN, "init", "-b", "main", cwd=str(target_dir))
        (target_dir / "README.md").write_text(f"# {repo_name}\n\n{desc}\n\n*Created on {datetime.now().strftime('%Y-%m-%d')}*\n", encoding="utf-8")
        (target_dir / ".gitignore").write_text("__pycache__/\n*.pyc\n.env\nnode_modules/\n.DS_Store\nvenv/\n", encoding="utf-8")
        await asyncio.create_subprocess_exec(GIT_BIN, "add", ".", cwd=str(target_dir))
        await asyncio.create_subprocess_exec(GIT_BIN, "commit", "-m", "feat: initial commit from OMV Agent Station", cwd=str(target_dir))

        remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git" if GITHUB_TOKEN else clone_url
        await asyncio.create_subprocess_exec(GIT_BIN, "remote", "add", "origin", remote_url, cwd=str(target_dir))
        push_proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "-u", "origin", "main", cwd=str(target_dir))
        await push_proc.communicate()

        init_obsidian_project_spec(repo_name, html_url or clone_url)

        return {
            "success": True,
            "repo_name": repo_name,
            "html_url": html_url,
            "target_dir": target_dir
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def git_pull_repo(project_name: str) -> dict:
    """Pulls latest changes for a project with rebase."""
    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        return {"success": False, "error": f"`{project_name}` is not a valid git repository."}

    proc = await asyncio.create_subprocess_exec(GIT_BIN, "pull", "--rebase", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
    stdout, stderr = await proc.communicate()
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    return {"success": proc.returncode == 0, "output": out or err or "Already up to date."}

async def git_push_repo(project_name: str, branch: str = "main") -> dict:
    """Pushes committed branch to remote repository."""
    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        return {"success": False, "error": f"`{project_name}` is not a valid git repository."}

    clean_branch = sanitize_branch_name(branch) or "main"
    proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "origin", clean_branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
    stdout, stderr = await proc.communicate()
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    return {"success": proc.returncode == 0, "output": out or err or "Everything up-to-date"}

async def git_diff_repo(project_name: str) -> dict:
    """Retrieves uncommitted diff in project."""
    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        return {"success": False, "error": f"`{project_name}` is not a valid git repository."}

    proc = await asyncio.create_subprocess_exec(GIT_BIN, "diff", "HEAD", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
    stdout, _ = await proc.communicate()
    diff_text = stdout.decode("utf-8", errors="replace").strip()
    return {"success": True, "diff": diff_text}

def list_workspace_projects() -> list[str]:
    """Returns sorted list of valid workspace project directories."""
    if not WORKSPACE.exists():
        return []
    return sorted([p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")])
