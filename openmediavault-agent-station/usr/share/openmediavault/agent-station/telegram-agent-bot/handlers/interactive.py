"""
Interactive ForceReply Prompt and Natural Language Conversational Message Router.
Handles typing responses to bot input prompts and direct conversational AI in 1-on-1 chats.
"""

import shlex
from telegram import Update
from telegram.ext import ContextTypes
from core.security import check_auth
from .ai_chat import chat_cmd
from .system import task_cmd, claude_cmd, exec_cmd
from .git_ops import newrepo_cmd, clone_cmd
from .vault import note_cmd

async def interactive_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles direct plain text, interactive ForceReply prompts, and auto-clone link pastes."""
    if not await check_auth(update):
        return
    msg = update.effective_message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    reply_to = msg.reply_to_message

    # Case 1: User is replying to a ForceReply prompt from the bot
    if reply_to and reply_to.from_user and reply_to.from_user.is_bot:
        parent_text = reply_to.text or ""

        if "Gemini" in parent_text:
            context.args = ["-m", "gemini-3.6-flash"] + text.split()
            await chat_cmd(update, context)
            return
        elif "GPT-4o" in parent_text or "gpt4" in parent_text.lower():
            context.args = ["-m", "github-gpt-4o"] + text.split()
            await chat_cmd(update, context)
            return
        elif "AI Chat" in parent_text or "Smart Router" in parent_text:
            context.args = text.split()
            await chat_cmd(update, context)
            return
        elif "Coding Agent" in parent_text or "Autonomous" in parent_text:
            context.args = shlex.split(text) if ("\"" in text or "'" in text) else text.split()
            await task_cmd(update, context)
            return
        elif "Claude Code" in parent_text:
            context.args = text.split()
            await claude_cmd(update, context)
            return
        elif "Obsidian" in parent_text or "Note" in parent_text:
            context.args = text.split()
            await note_cmd(update, context)
            return
        elif "Shell Command" in parent_text or "Workspace Shell" in parent_text:
            context.args = text.split()
            await exec_cmd(update, context)
            return
        elif "GitHub Repository" in parent_text or "repo" in parent_text.lower():
            context.args = shlex.split(text) if ("\"" in text or "'" in text) else text.split()
            await newrepo_cmd(update, context)
            return
        elif "Clone Git Repository" in parent_text or "clone" in parent_text.lower() or "git" in parent_text.lower():
            context.args = text.split()
            await clone_cmd(update, context)
            return

    # Case 2: Direct GitHub / Git URL paste in private chat automatically triggers project clone
    if text.startswith("https://github.com/") or text.startswith("http://github.com/") or text.startswith("git@github.com:"):
        context.args = text.split()
        await clone_cmd(update, context)
        return

    # Case 3: In private 1-on-1 chat, if the user sends any text question without a slash command,
    # naturally answer it with AI Chat (Google Gemini Flash / coder-smart)!
    chat = update.effective_chat
    if chat and chat.type == "private":
        context.args = text.split()
        await chat_cmd(update, context)
