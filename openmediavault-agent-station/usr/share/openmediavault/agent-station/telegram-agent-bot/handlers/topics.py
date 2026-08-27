"""
Telegram Forum Topics and Channel Context Binding Handlers.
Manages thread-to-project mappings and context inference for multi-project groups.
"""

import json
from telegram import Update, ForceReply
from telegram.ext import ContextTypes
from core.config import WORKSPACE, TOPICS_FILE, logger
from core.security import check_auth, sanitize_project_path

def load_topic_bindings() -> dict:
    """Loads thread-to-project bindings from disk."""
    if TOPICS_FILE.exists():
        try:
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {TOPICS_FILE}: {e}")
    return {}

def save_topic_bindings(bindings: dict):
    """Saves thread-to-project bindings to disk."""
    try:
        with open(TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(bindings, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write {TOPICS_FILE}: {e}")

def get_bound_project(chat_id: int, thread_id: int | None) -> str | None:
    """Returns the project folder name bound to a given (chat_id, thread_id) pair."""
    if not thread_id:
        return None
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    return bindings.get(key)

def set_bound_project(chat_id: int, thread_id: int, project_name: str):
    """Binds a project folder name to a given (chat_id, thread_id) pair."""
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    bindings[key] = project_name
    save_topic_bindings(bindings)

def remove_bound_project(chat_id: int, thread_id: int):
    """Removes the project binding for a given (chat_id, thread_id) pair."""
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    if key in bindings:
        del bindings[key]
        save_topic_bindings(bindings)

def resolve_project_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[str | None, list[str]]:
    """
    Intelligently resolves the target project and remaining args based on:
    1. Explicit project argument in command (if matches a workspace folder).
    2. Forum topic / sub-channel binding.
    """
    thread_id = update.effective_message.message_thread_id if update.effective_message else None
    chat_id = update.effective_chat.id if update.effective_chat else 0
    bound_project = get_bound_project(chat_id, thread_id)

    args = list(context.args) if context.args else []

    if not args:
        return (bound_project, [])

    first_arg = args[0]
    candidate_dir = WORKSPACE / first_arg
    if candidate_dir.exists() and candidate_dir.is_dir() and not first_arg.startswith("."):
        return (first_arg, args[1:])

    if bound_project:
        return (bound_project, args)

    return (first_arg, args[1:])

async def bind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Binds the current Telegram topic/sub-channel to a workspace project."""
    if not await check_auth(update):
        return

    chat = update.effective_chat
    thread_id = update.effective_message.message_thread_id if update.effective_message else None

    if not thread_id:
        await update.effective_message.reply_text(
            "ℹ️ *How to bind Telegram Forum Topics to Projects:*\n\n"
            "1. Enable **Topics** in your Telegram Group Settings.\n"
            "2. Open a dedicated Project Topic (e.g. `#my-app`).\n"
            "3. Send `/bind <project-folder-name>` inside that topic.",
            parse_mode="Markdown"
        )
        return

    if not context.args:
        current_bound = get_bound_project(chat.id, thread_id)
        status = f"Currently bound to: `{current_bound}`" if current_bound else "Not bound to any project."
        projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")] if WORKSPACE.exists() else []
        proj_str = ", ".join([f"`{p}`" for p in projects]) or "None"
        await update.effective_message.reply_text(
            f"🧵 *Topic Binding Status*\n\n"
            f"• {status}\n"
            f"• Available projects: {proj_str}\n\n"
            f"To bind: `/bind <project-name>`\nTo unbind: `/unbind`",
            parse_mode="Markdown"
        )
        return

    project_name = context.args[0].strip()
    project_dir = sanitize_project_path(WORKSPACE, project_name)

    if not project_dir or not project_dir.exists():
        await update.effective_message.reply_text(f"❌ Project directory `{project_name}` not found in `/data/workspace`.")
        return

    set_bound_project(chat.id, thread_id, project_name)
    await update.effective_message.reply_text(
        f"✅ *Topic Successfully Bound!*\n\n"
        f"This sub-channel is now linked to project: `{project_name}`.\n\n"
        f"Commands in this topic now automatically target `{project_name}`:\n"
        f"• `/task \"your instructions\"`\n"
        f"• `/diff`\n"
        f"• `/pull`\n"
        f"• `/push`\n"
        f"• `/branch <name>`",
        parse_mode="Markdown"
    )

async def unbind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unbinds the current Telegram topic/sub-channel."""
    if not await check_auth(update):
        return

    chat = update.effective_chat
    thread_id = update.effective_message.message_thread_id if update.effective_message else None

    if not thread_id:
        await update.effective_message.reply_text("ℹ️ Run `/unbind` inside a Telegram Forum Topic.")
        return

    remove_bound_project(chat.id, thread_id)
    await update.effective_message.reply_text("✅ Topic unlinked from project context.")

async def createtopic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Creates a dedicated Telegram Forum Topic for a project and binds it."""
    if not await check_auth(update):
        return
    chat = update.effective_chat
    if not chat or chat.type not in ("supergroup", "group"):
        await update.effective_message.reply_text("ℹ️ This command must be run inside a Telegram Group / Supergroup with **Topics** enabled.", parse_mode="Markdown")
        return

    if not context.args:
        projects = [p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.name.startswith(".")] if WORKSPACE.exists() else []
        proj_str = ", ".join([f"`{p}`" for p in projects]) if projects else "none"
        await update.effective_message.reply_text(
            f"Usage: `/createtopic <project-folder-name>`\n\nAvailable projects: {proj_str}",
            parse_mode="Markdown",
            reply_markup=ForceReply(selective=True, input_field_placeholder="Type project name for new topic...")
        )
        return

    folder_name = context.args[0].strip()
    target_dir = sanitize_project_path(WORKSPACE, folder_name)
    if not target_dir or not target_dir.exists():
        await update.effective_message.reply_text(f"❌ Project directory `{folder_name}` not found in `/data/workspace`.", parse_mode="Markdown")
        return

    try:
        forum_topic = await context.bot.create_forum_topic(
            chat_id=chat.id,
            name=f"📂 {folder_name}"
        )
        if forum_topic and forum_topic.message_thread_id:
            set_bound_project(chat.id, forum_topic.message_thread_id, folder_name)
            await update.effective_message.reply_text(
                f"✅ *Created Forum Topic:* `📂 {folder_name}`!\n\n"
                f"This topic channel is now automatically bound to `{folder_name}`.\n\n"
                f"All commands (`/task`, `/diff`, `/push`, `/pull`, `/branch`) inside that topic will directly target this project!",
                parse_mode="Markdown"
            )
    except Exception as e:
        err_s = str(e).lower()
        if "not a forum" in err_s:
            await update.effective_message.reply_text(
                "⚠️ *Topics are not enabled for this group yet.*\n\n"
                "👉 *How to enable Topics in Telegram:*\n"
                "1. Click/tap Group Name at the top (`Agent-station-projects`)\n"
                "2. Click the **Edit** (✏️) icon ➔ **Group Settings**\n"
                "3. Turn ON the **Topics** toggle switch\n"
                "4. Re-run `/createtopic " + folder_name + "`!",
                parse_mode="Markdown"
            )
        elif "rights" in err_s or "admin" in err_s:
            await update.effective_message.reply_text(
                "⚠️ *Bot lacks permission to create topics.*\n\n"
                "👉 Please promote `@agent_station_bot` to **Administrator** and enable the **Manage Topics** permission.",
                parse_mode="Markdown"
            )
        else:
            await update.effective_message.reply_text(f"❌ Could not create topic: {e}")
