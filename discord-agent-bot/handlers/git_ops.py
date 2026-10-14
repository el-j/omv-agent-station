"""
Git Version Control and Workspace Management Handlers.
Implements repo listing/creation, automated PAT cloning, pulling, pushing,
branch switching, and diff viewing.
"""

from discord.ext import commands

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
)
from core.security import check_auth, resolve_ctx_project


async def projects_cmd(ctx: commands.Context):
    """Lists every project currently cloned into the shared workspace."""
    if not await check_auth(ctx):
        return
    projects = list_workspace_projects()
    if not projects:
        await ctx.reply("📁 No workspace projects found.")
        return
    proj_str = "\n".join([f"• `📂 {p}`" for p in projects])
    await ctx.reply(f"📁 **Workspace Projects ({len(projects)}):**\n\n{proj_str}")


async def clone_cmd(ctx: commands.Context, git_url: str = "", folder_name: str = ""):
    """Clones a git repository (with PAT injection where applicable) into the workspace."""
    if not await check_auth(ctx):
        return
    if not git_url:
        await ctx.reply("Usage: `/clone <git-url> [custom-folder-name]`")
        return

    msg = await ctx.reply(f"⏳ Cloning `{git_url}`...")
    res = await clone_repository(git_url, folder_name)
    if res["success"]:
        f_name = res["folder_name"]
        await msg.edit(content=(
            f"✅ **Repository Cloned & Registered as Active Project!**\n\n"
            f"📁 **Project:** `{f_name}`\n"
            f"💾 **Path:** `/data/workspace/{f_name}`\n"
            f"📓 **Obsidian Spec:** `/data/obsidian/Projects/{f_name}/`\n\n"
            f"Run tasks with `/task {f_name} \"instructions\"`"
        ))
    else:
        await msg.edit(content=f"❌ Git clone failed: {res.get('error')}")


async def newrepo_cmd(ctx: commands.Context, repo_name: str = "", *, description: str = ""):
    """Creates a brand-new remote GitHub repository via the configured PAT."""
    if not await check_auth(ctx):
        return
    if not repo_name:
        await ctx.reply("Usage: `/newrepo <repo-name> [description]`")
        return

    msg = await ctx.reply(f"⏳ Creating remote GitHub repo `{repo_name}`...")
    res = await create_new_repository(repo_name, description)
    if res["success"]:
        await msg.edit(content=(
            f"✅ **New GitHub Repository Created!**\n\n"
            f"📁 **Project:** `{res['repo_name']}`\n"
            f"🔗 **URL:** {res.get('html_url')}\n"
            f"💾 **Path:** `/data/workspace/{res['repo_name']}`"
        ))
    else:
        await msg.edit(content=f"❌ Failed to create repo: {res.get('error')}")


async def pull_cmd(ctx: commands.Context, project_name: str = ""):
    """Runs git pull in the resolved project's workspace directory."""
    if not await check_auth(ctx):
        return
    proj, _ = resolve_ctx_project(ctx, [project_name] if project_name else [])
    if not proj:
        await ctx.reply("Usage: `/pull [project-name]`")
        return
    msg = await ctx.reply(f"⏳ Pulling latest changes for `{proj}`...")
    res = await git_pull_repo(proj)
    if res["success"]:
        await msg.edit(content=f"✅ **Git Pull ({proj}):**\n```{res['output'][:1800]}```")
    else:
        await msg.edit(content=f"❌ Git pull failed: {res.get('error')}")


async def push_cmd(ctx: commands.Context, project_name: str = "", branch: str = "main"):
    """Runs git push for the resolved project to the given (or default) branch."""
    if not await check_auth(ctx):
        return
    proj, remaining = resolve_ctx_project(ctx, [project_name] if project_name else [])
    if not proj:
        await ctx.reply("Usage: `/push [project-name] [branch]`")
        return
    target_branch = remaining[0] if remaining else branch
    msg = await ctx.reply(f"⏳ Pushing `{proj}` to `{target_branch}`...")
    res = await git_push_repo(proj, target_branch)
    if res["success"]:
        await msg.edit(content=f"✅ **Git Push ({proj} -> {target_branch}):**\n```{res['output'][:1800]}```")
    else:
        await msg.edit(content=f"❌ Git push failed: {res.get('error')}")


async def branch_cmd(ctx: commands.Context, project_name: str = "", branch_name: str = ""):
    """Lists branches, or safely creates/switches to one (never force-resets an
    existing branch -- see GitHub issue #48: a prior `git checkout -B` here could
    silently discard commits on a branch that already existed)."""
    if not await check_auth(ctx):
        return
    proj, remaining = resolve_ctx_project(ctx, [project_name] if project_name else [])
    if not proj:
        await ctx.reply("Usage: `/branch [project-name] [new-branch-name]`")
        return

    p_dir = sanitize_project_path(WORKSPACE, proj)
    if not p_dir or not (p_dir / ".git").exists():
        await ctx.reply(f"❌ `{proj}` is not a valid git repository.")
        return

    new_b = remaining[0] if remaining else branch_name
    if not new_b:
        res = await run_shell_exec("git branch -a", cwd=p_dir)
        await ctx.reply(f"🌿 **Branches for `{proj}`:**\n```{res['output'][:1800]}```")
    else:
        clean_b = sanitize_branch_name(new_b)
        if not clean_b:
            await ctx.reply("❌ Invalid branch name format.")
            return
        res = await run_shell_exec(f"git checkout -b {clean_b}", cwd=p_dir)
        if res["success"]:
            await ctx.reply(f"✅ Checked out new branch `{clean_b}` in project `{proj}`.")
        else:
            res2 = await run_shell_exec(f"git checkout {clean_b}", cwd=p_dir)
            if res2["success"]:
                await ctx.reply(f"✅ Switched to existing branch `{clean_b}` in project `{proj}`.")
            else:
                await ctx.reply(f"❌ Branch checkout failed: {res2.get('output')}")


async def diff_cmd(ctx: commands.Context, project_name: str = ""):
    """Shows the uncommitted git diff for the resolved project."""
    if not await check_auth(ctx):
        return
    proj, _ = resolve_ctx_project(ctx, [project_name] if project_name else [])
    if not proj:
        await ctx.reply("Usage: `/diff [project-name]`")
        return
    res = await git_diff_repo(proj)
    if res["success"]:
        diff_text = res["diff"] or "(No uncommitted diff)"
        if len(diff_text) > 1800:
            diff_text = diff_text[:1800] + "\n...(truncated)"
        await ctx.reply(f"🔍 **Git Diff (`{proj}`):**\n```diff\n{diff_text}\n```")
    else:
        await ctx.reply(f"❌ Error: {res.get('error')}")
