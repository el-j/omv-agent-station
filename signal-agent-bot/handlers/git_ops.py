"""
Git Version Control and Workspace Management Handlers.
Implements repo listing/creation, automated PAT cloning, pulling, pushing,
branch switching, and diff viewing.
"""

from agent_station_core import (
    WORKSPACE,
    sanitize_project_path,
    sanitize_branch_name,
    clone_repository,
    create_new_repository,
    git_pull_repo,
    git_push_repo,
    git_diff_repo,
    list_workspace_projects,
    run_shell_exec,
    resolve_project_context_raw,
)
from core.messaging import send_signal_message


async def projects(sender: str, args: list[str]):
    """Lists every project currently cloned into the shared workspace."""
    project_list = list_workspace_projects()
    if not project_list:
        await send_signal_message(sender, "📁 No workspace projects found.")
        return
    proj_str = "\n".join([f"• {p}" for p in project_list])
    await send_signal_message(sender, f"📁 Workspace Projects ({len(project_list)}):\n\n{proj_str}")


async def clone(sender: str, args: list[str]):
    """Clones a git repository (with PAT injection where applicable) into the workspace."""
    if not args:
        await send_signal_message(sender, "Usage: /clone <git-url> [custom-folder-name]")
        return
    git_url = args[0]
    f_name = args[1] if len(args) > 1 else ""
    await send_signal_message(sender, f"⏳ Cloning {git_url}...")
    res = await clone_repository(git_url, f_name)
    if res["success"]:
        folder = res["folder_name"]
        msg = (
            f"✅ Repository Cloned & Registered as Active Project!\n\n"
            f"📁 Project: {folder}\n"
            f"💾 Path: /data/workspace/{folder}\n"
            f"📓 Obsidian Spec: /data/obsidian/Projects/{folder}/\n\n"
            f"Run tasks with: /task {folder} \"your instructions\""
        )
        await send_signal_message(sender, msg)
    else:
        await send_signal_message(sender, f"❌ Git clone failed: {res.get('error')}")


async def newrepo(sender: str, args: list[str]):
    """Creates a brand-new remote GitHub repository via the configured PAT."""
    if not args:
        await send_signal_message(sender, "Usage: /newrepo <repo-name> [description]")
        return
    repo_name = args[0]
    desc = " ".join(args[1:]) if len(args) > 1 else ""
    await send_signal_message(sender, f"⏳ Creating GitHub repository {repo_name}...")
    res = await create_new_repository(repo_name, desc)
    if res["success"]:
        msg = (
            f"✅ New GitHub Repository Created!\n\n"
            f"📁 Project: {res['repo_name']}\n"
            f"🔗 URL: {res.get('html_url')}\n"
            f"💾 Path: /data/workspace/{res['repo_name']}"
        )
        await send_signal_message(sender, msg)
    else:
        await send_signal_message(sender, f"❌ Failed to create repo: {res.get('error')}")


async def pull(sender: str, args: list[str]):
    """Runs git pull in the resolved project's workspace directory."""
    proj, _ = resolve_project_context_raw(sender, None, args, WORKSPACE)
    if not proj:
        await send_signal_message(sender, "Usage: /pull [project-name]")
        return
    await send_signal_message(sender, f"⏳ Pulling latest changes for {proj}...")
    res = await git_pull_repo(proj)
    if res["success"]:
        await send_signal_message(sender, f"✅ Git Pull ({proj}):\n{res['output']}")
    else:
        await send_signal_message(sender, f"❌ Git pull failed: {res.get('error')}")


async def push(sender: str, args: list[str]):
    """Runs git push for the resolved project to the given (or default) branch."""
    proj, remaining = resolve_project_context_raw(sender, None, args, WORKSPACE)
    if not proj:
        await send_signal_message(sender, "Usage: /push [project-name] [branch]")
        return
    branch = remaining[0] if remaining else "main"
    await send_signal_message(sender, f"⏳ Pushing {proj} to {branch}...")
    res = await git_push_repo(proj, branch)
    if res["success"]:
        await send_signal_message(sender, f"✅ Git Push ({proj} -> {branch}):\n{res['output']}")
    else:
        await send_signal_message(sender, f"❌ Git push failed: {res.get('error')}")


async def branch(sender: str, args: list[str]):
    """Lists branches, or safely creates/switches to one (never force-resets an
    existing branch -- see GitHub issue #48: a prior `git checkout -B` here could
    silently discard commits on a branch that already existed)."""
    proj, remaining = resolve_project_context_raw(sender, None, args, WORKSPACE)
    if not proj:
        await send_signal_message(sender, "Usage: /branch [project-name] [new-branch]")
        return
    p_dir = sanitize_project_path(WORKSPACE, proj)
    if not p_dir or not (p_dir / ".git").exists():
        await send_signal_message(sender, f"❌ `{proj}` is not a valid git repository.")
        return
    if not remaining:
        res = await run_shell_exec("git branch -a", cwd=p_dir)
        await send_signal_message(sender, f"🌿 Branches for {proj}:\n{res['output']}")
    else:
        clean_b = sanitize_branch_name(remaining[0])
        if not clean_b:
            await send_signal_message(sender, "❌ Invalid branch name format.")
            return
        res = await run_shell_exec(f"git checkout -b {clean_b}", cwd=p_dir)
        if res["success"]:
            await send_signal_message(sender, f"✅ Checked out new branch {clean_b} in project {proj}.")
        else:
            res2 = await run_shell_exec(f"git checkout {clean_b}", cwd=p_dir)
            if res2["success"]:
                await send_signal_message(sender, f"✅ Switched to existing branch {clean_b} in project {proj}.")
            else:
                await send_signal_message(sender, f"❌ Branch checkout failed: {res2.get('output')}")


async def diff(sender: str, args: list[str]):
    """Shows the uncommitted git diff for the resolved project."""
    proj, _ = resolve_project_context_raw(sender, None, args, WORKSPACE)
    if not proj:
        await send_signal_message(sender, "Usage: /diff [project-name]")
        return
    res = await git_diff_repo(proj)
    if res["success"]:
        diff_text = res["diff"] or "(No uncommitted diff)"
        await send_signal_message(sender, f"🔍 Git Diff ({proj}):\n{diff_text}")
    else:
        await send_signal_message(sender, f"❌ Error: {res.get('error')}")
