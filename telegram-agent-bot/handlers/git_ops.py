"""
Git Version Control and Workspace Management Handlers.
Implements repo creation, automated PAT cloning, branch switching, pulling, pushing, and diff viewing.
"""

import asyncio
from datetime import datetime
import httpx
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from core.config import (
    WORKSPACE,
    GIT_BIN,
    GIT_AUTHOR_NAME,
    GIT_AUTHOR_EMAIL,
    GITHUB_TOKEN,
    logger,
)
from core.security import (
    check_auth,
    sanitize_project_path,
    sanitize_repo_name,
    sanitize_branch_name,
    sanitize_git_url,
)
from .topics import resolve_project_context, set_bound_project
from .vault import init_obsidian_project_spec

async def projects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all active projects in the workspace with interactive action buttons."""
    if not await check_auth(update):
        return
    if not WORKSPACE.exists():
        await update.effective_message.reply_text("📁 Workspace folder is empty or not mounted.")
        return

    projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if not projects:
        await update.effective_message.reply_text("📁 No projects found in `/data/workspace`.")
        return

    proj_list = "\n".join([f"• `📂 {p}`" for p in sorted(projects)])
    keyboard = []
    for p in sorted(projects)[:6]:
        keyboard.append([InlineKeyboardButton(f"🚀 Code: {p}", switch_inline_query_current_chat=f"/task {p} ")])
    keyboard.append([InlineKeyboardButton("❓ Help Handbook", callback_data="help_menu:main")])

    await update.effective_message.reply_text(
        f"📁 *Available Workspace Projects ({len(projects)}):*\n\n{proj_list}\n\nTap below to start coding on any project:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def newrepo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Creates a new repository on GitHub, initializes local files, commits, and pushes to origin."""
    if not await check_auth(update):
        return

    if not context.args:
        await update.effective_message.reply_text(
            "✨ *Create New GitHub Repository*\n\n"
            "Please type repository name and optional description below:\n"
            "• Syntax: `<repo-name> [description]`\n"
            "• Example: `my-awesome-app \"Autonomous full-stack service\"`",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="repo-name \"optional description\""
            )
        )
        return

    repo_name_raw = context.args[0].strip()
    repo_name = sanitize_repo_name(repo_name_raw)

    if not repo_name:
        await update.effective_message.reply_text(
            "❌ Invalid repository name. Use alphanumeric characters, hyphens, underscores, or dots (e.g. `my-new-app`).",
            parse_mode="Markdown"
        )
        return

    description = " ".join(context.args[1:]).strip() if len(context.args) > 1 else f"Project {repo_name} created with OMV Agent Station"

    target_dir = sanitize_project_path(WORKSPACE, repo_name)
    if not target_dir:
        await update.effective_message.reply_text("❌ Invalid repository name path resolution.", parse_mode="Markdown")
        return

    if target_dir.exists():
        await update.effective_message.reply_text(
            f"⚠️ Destination directory `{repo_name}` already exists in `/data/workspace`.",
            parse_mode="Markdown"
        )
        return

    if not GITHUB_TOKEN:
        await update.effective_message.reply_text(
            "❌ `GITHUB_TOKEN` is not configured.\n\n"
            "Please add your GitHub Personal Access Token (with `repo` scope) in OMV Services -> Agent Station -> AI Providers.",
            parse_mode="Markdown"
        )
        return

    msg = await update.effective_message.reply_text(f"⏳ Creating GitHub repository `{repo_name}`...", parse_mode="Markdown")

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
                json={
                    "name": repo_name,
                    "description": description,
                    "private": True,
                    "auto_init": False
                }
            )

            if resp.status_code not in (200, 201):
                err_body = resp.text
                await msg.edit_text(f"❌ GitHub API error ({resp.status_code}):\n```\n{err_body[:500]}\n```", parse_mode="Markdown")
                return

            repo_data = resp.json()
            clone_url = repo_data.get("clone_url")
            html_url = repo_data.get("html_url")
            owner = repo_data.get("owner", {}).get("login", "")

        target_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.create_subprocess_exec(GIT_BIN, "init", "-b", "main", cwd=str(target_dir))

        readme_content = f"# {repo_name}\n\n{description}\n\n*Created with OMV Agent Station on {datetime.now().strftime('%Y-%m-%d')}*\n"
        (target_dir / "README.md").write_text(readme_content, encoding="utf-8")

        gitignore_content = "__pycache__/\n*.pyc\n.env\nnode_modules/\n.DS_Store\nvenv/\n.venv/\n"
        (target_dir / ".gitignore").write_text(gitignore_content, encoding="utf-8")

        await asyncio.create_subprocess_exec(GIT_BIN, "add", ".", cwd=str(target_dir))
        await asyncio.create_subprocess_exec(GIT_BIN, "commit", "-m", "feat: initial commit from OMV Agent Station", cwd=str(target_dir))

        remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git" if GITHUB_TOKEN else clone_url
        await asyncio.create_subprocess_exec(GIT_BIN, "remote", "add", "origin", remote_url, cwd=str(target_dir))
        push_proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "-u", "origin", "main", cwd=str(target_dir))
        await push_proc.communicate()

        # Initialize Obsidian Spec
        init_obsidian_project_spec(repo_name, html_url or clone_url)

        topic_info = ""
        chat = update.effective_chat
        if chat and chat.type in ("supergroup", "group"):
            try:
                forum_topic = await context.bot.create_forum_topic(
                    chat_id=chat.id,
                    name=f"📂 {repo_name}"
                )
                if forum_topic and forum_topic.message_thread_id:
                    set_bound_project(chat.id, forum_topic.message_thread_id, repo_name)
                    topic_info = f"\n🧵 *Created Forum Topic:* `📂 {repo_name}` (automatically bound!)"
            except Exception as te:
                err_s = str(te).lower()
                logger.info(f"Could not create forum topic: {te}")
                if "not enough rights" in err_s or "rights" in err_s or "admin" in err_s:
                    topic_info = (
                        f"\n\n⚠️ *Could not auto-create sub-channel topic:*\n"
                        f"Telegram requires bot to be an **Administrator** with **Manage Topics** permission.\n"
                        f"👉 Promote bot to Admin in group settings, then type `/createtopic {repo_name}`!"
                    )
                elif "not a forum" in err_s:
                    topic_info = (
                        f"\n\n⚠️ *Could not auto-create sub-channel topic:*\n"
                        f"Topics are not enabled yet in this group.\n"
                        f"👉 Turn ON **Topics** in Group Settings, then type `/createtopic {repo_name}`!"
                    )
                else:
                    topic_info = f"\n\nℹ️ Run `/createtopic {repo_name}` to create its dedicated sub-channel topic."

        await msg.edit_text(
            f"✅ *New GitHub Repository Created & Cloned!*\n\n"
            f"📁 *Project:* `{repo_name}`\n"
            f"🔗 *URL:* {html_url}\n"
            f"💾 *Path:* `/data/workspace/{repo_name}`\n"
            f"📓 *Obsidian Spec:* `/data/obsidian/Projects/{repo_name}/`{topic_info}\n\n"
            f"Run your first agent task:\n`/task {repo_name} \"your coding prompt\"`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error creating new repository: {e}")
        await msg.edit_text(f"❌ Failed to create new repository: {e}")

async def clone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clones a git repository with automated PAT credentials and Obsidian spec initialization."""
    if not await check_auth(update):
        return
    if not context.args:
        await update.effective_message.reply_text(
            "📥 *Clone Git Repository*\n\n"
            "Please type or paste the git repository URL below:\n"
            "• Syntax: `https://github.com/owner/repo [folder-name]`\n"
            "• Example: `https://github.com/fastapi/fastapi my-api`",
            parse_mode="Markdown",
            reply_markup=ForceReply(
                selective=True,
                input_field_placeholder="https://github.com/owner/repo..."
            )
        )
        return

    raw_git_url = context.args[0].strip()
    git_url = sanitize_git_url(raw_git_url)
    if not git_url:
        await update.effective_message.reply_text("❌ Invalid git URL format.", parse_mode="Markdown")
        return

    if len(context.args) > 1:
        folder_name = context.args[1].strip()
    else:
        folder_name = git_url.rstrip("/").split("/")[-1].replace(".git", "")

    target_dir = sanitize_project_path(WORKSPACE, folder_name)
    if not target_dir:
        await update.effective_message.reply_text("❌ Invalid folder name.", parse_mode="Markdown")
        return

    if target_dir.exists():
        await update.effective_message.reply_text(f"⚠️ Destination folder `{folder_name}` already exists in `/data/workspace`.", parse_mode="Markdown")
        return

    msg = await update.effective_message.reply_text(f"⏳ Cloning `{git_url}` into `/data/workspace/{folder_name}`...", parse_mode="Markdown")
    try:
        clone_target_url = git_url
        if GITHUB_TOKEN and "github.com" in git_url and not git_url.startswith("git@"):
            clean_http = git_url.replace("https://", "").replace("http://", "")
            clone_target_url = f"https://x-access-token:{GITHUB_TOKEN}@{clean_http}"

        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            GIT_BIN, "clone", "--", clone_target_url, str(target_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await asyncio.create_subprocess_exec(GIT_BIN, "config", "user.name", GIT_AUTHOR_NAME, cwd=str(target_dir))
            await asyncio.create_subprocess_exec(GIT_BIN, "config", "user.email", GIT_AUTHOR_EMAIL, cwd=str(target_dir))

            # Initialize Obsidian Project Specs
            init_obsidian_project_spec(folder_name, git_url)

            topic_info = ""
            chat = update.effective_chat
            if chat and chat.type in ("supergroup", "group"):
                try:
                    forum_topic = await context.bot.create_forum_topic(
                        chat_id=chat.id,
                        name=f"📂 {folder_name}"
                    )
                    if forum_topic and forum_topic.message_thread_id:
                        set_bound_project(chat.id, forum_topic.message_thread_id, folder_name)
                        topic_info = f"\n🧵 *Created Forum Topic:* `📂 {folder_name}` (automatically bound!)"
                except Exception as te:
                    err_s = str(te).lower()
                    logger.info(f"Could not create forum topic: {te}")
                    if "not enough rights" in err_s or "rights" in err_s or "admin" in err_s:
                        topic_info = (
                            f"\n\n⚠️ *Could not auto-create sub-channel topic:*\n"
                            f"Telegram requires bot to be an **Administrator** with **Manage Topics** permission.\n"
                            f"👉 Promote bot to Admin in group settings, then type `/createtopic {folder_name}`!"
                        )
                    elif "not a forum" in err_s:
                        topic_info = (
                            f"\n\n⚠️ *Could not auto-create sub-channel topic:*\n"
                            f"Topics are not enabled yet in this group.\n"
                            f"👉 Turn ON **Topics** in Group Settings, then type `/createtopic {folder_name}`!"
                        )
                    else:
                        topic_info = f"\n\nℹ️ Run `/createtopic {folder_name}` to create its dedicated sub-channel topic."

            keyboard = [
                [
                    InlineKeyboardButton("🚀 Start Coding Task", switch_inline_query_current_chat=f"/task {folder_name} "),
                    InlineKeyboardButton("🌿 Branches", switch_inline_query_current_chat=f"/branch {folder_name} "),
                ],
                [
                    InlineKeyboardButton("📁 List All Projects", callback_data="btn_projects"),
                ]
            ]

            await msg.edit_text(
                f"✅ *Repository Cloned & Registered as Active Project!*\n\n"
                f"📁 *Project:* `{folder_name}`\n"
                f"🔗 *Remote:* `{git_url}`\n"
                f"💾 *Path:* `/data/workspace/{folder_name}`\n"
                f"📓 *Obsidian Spec:* `/data/obsidian/Projects/{folder_name}/`{topic_info}\n\n"
                f"You can now run tasks on this project with:\n`/task {folder_name} \"your coding prompt\"`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            err = stderr.decode("utf-8", errors="replace")
            await msg.edit_text(f"❌ Git clone failed:\n```\n{err}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error during git clone: {e}")

async def pull_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes git pull on the resolved project repository."""
    if not await check_auth(update):
        return

    project_name, _ = resolve_project_context(update, context)
    if not project_name:
        await update.effective_message.reply_text("Usage: `/pull [project-folder-name]`\n\n*(Tip: In a bound Telegram Topic, project name is automatically inferred!)*", parse_mode="Markdown")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.effective_message.reply_text(f"❌ `{project_name}` is not a valid git repository.")
        return

    msg = await update.effective_message.reply_text(f"⏳ Pulling latest changes for `{project_name}`...", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "pull", "--rebase", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        if proc.returncode == 0:
            await msg.edit_text(f"✅ *Git Pull Successful ({project_name}):*\n```\n{out or 'Already up to date.'}\n```", parse_mode="Markdown")
        else:
            await msg.edit_text(f"❌ *Git Pull Failed:*\n```\n{err or out}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error during git pull: {e}")

async def push_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes git push on the resolved project repository."""
    if not await check_auth(update):
        return

    project_name, remaining_args = resolve_project_context(update, context)
    if not project_name:
        await update.effective_message.reply_text("Usage: `/push [project-folder-name] [branch]`", parse_mode="Markdown")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.effective_message.reply_text(f"❌ `{project_name}` is not a valid git repository.")
        return

    branch = "main"
    if remaining_args:
        raw_b = remaining_args[0].strip()
        san_b = sanitize_branch_name(raw_b)
        if not san_b:
            await update.effective_message.reply_text("❌ Invalid branch name.")
            return
        branch = san_b

    msg = await update.effective_message.reply_text(f"⏳ Pushing `{project_name}` to origin `{branch}`...", parse_mode="Markdown")
    try:
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "origin", branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        if proc.returncode == 0:
            await msg.edit_text(f"✅ *Git Push Successful ({project_name} -> {branch}):*\n```\n{out or err or 'Everything up-to-date'}\n```", parse_mode="Markdown")
        else:
            await msg.edit_text(f"❌ *Git Push Failed:*\n```\n{err or out}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error during git push: {e}")

async def branch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists branches or creates and checks out a new branch."""
    if not await check_auth(update):
        return

    project_name, remaining_args = resolve_project_context(update, context)
    if not project_name:
        await update.effective_message.reply_text("Usage: `/branch [project-name] [new-branch-name]`", parse_mode="Markdown")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.effective_message.reply_text(f"❌ `{project_name}` is not a valid git repository.")
        return

    if not remaining_args:
        proc = await asyncio.create_subprocess_exec(GIT_BIN, "branch", "-a", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, _ = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        await update.effective_message.reply_text(f"🌿 *Branches for `{project_name}`:*\n```\n{out}\n```", parse_mode="Markdown")
    else:
        new_branch = sanitize_branch_name(remaining_args[0].strip())
        if not new_branch:
            await update.effective_message.reply_text("❌ Invalid branch name format.")
            return

        proc = await asyncio.create_subprocess_exec(GIT_BIN, "checkout", "-b", new_branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            await update.effective_message.reply_text(f"✅ Checked out new branch `{new_branch}` in `{project_name}`.", parse_mode="Markdown")
        else:
            proc2 = await asyncio.create_subprocess_exec(GIT_BIN, "checkout", new_branch, cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
            stdout2, stderr2 = await proc2.communicate()
            if proc2.returncode == 0:
                await update.effective_message.reply_text(f"✅ Switched to existing branch `{new_branch}` in `{project_name}`.", parse_mode="Markdown")
            else:
                err = stderr2.decode("utf-8", errors="replace")
                await update.effective_message.reply_text(f"❌ Branch checkout failed:\n```\n{err}\n```", parse_mode="Markdown")

async def diff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays uncommitted git diff in the project."""
    if not await check_auth(update):
        return

    project_name, _ = resolve_project_context(update, context)
    if not project_name:
        await update.effective_message.reply_text("Usage: `/diff [project-name]`", parse_mode="Markdown")
        return

    project_dir = sanitize_project_path(WORKSPACE, project_name)
    if not project_dir or not project_dir.exists() or not (project_dir / ".git").exists():
        await update.effective_message.reply_text(f"❌ `{project_name}` is not a valid git repository.")
        return

    proc = await asyncio.create_subprocess_exec(GIT_BIN, "diff", "HEAD", cwd=str(project_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)  # nosec B603,B607
    stdout, stderr = await proc.communicate()
    diff_text = stdout.decode("utf-8", errors="replace").strip()

    if not diff_text:
        await update.effective_message.reply_text(f"✅ Working tree clean in `{project_name}`. No uncommitted diff.", parse_mode="Markdown")
        return

    if len(diff_text) > 3500:
        diff_text = diff_text[:3500] + "\n...(diff truncated due to length)"

    await update.effective_message.reply_text(f"🔍 *Git Diff (`{project_name}`):*\n```diff\n{diff_text}\n```", parse_mode="Markdown")
