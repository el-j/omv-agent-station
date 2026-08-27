"""
Configuration and Environment Settings for Telegram Agent Bot.
Handles environment parsing, file paths, and global logger initialization.
"""

import os
import logging
from pathlib import Path

# Configure global logger
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("telegram_agent_bot")

# Core Messenger & LiteLLM Config
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.environ.get("TELEGRAM_ALLOWED_USER_ID")
LITELLM_BASE = os.environ.get("LITELLM_API_BASE", "http://litellm:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-omv-secret-master-key")
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/workspace"))
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT", "/workspace/ObsidianVault"))

# Git Binary & Identity Credentials
GIT_BIN = os.environ.get("GIT_BIN", "git")
GIT_AUTHOR_NAME = os.environ.get("GIT_AUTHOR_NAME", "Agent Station Bot")
GIT_AUTHOR_EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "bot@agentstation.local")
GITHUB_USER = os.environ.get("GITHUB_USER", "")
GITHUB_TOKEN = os.environ.get("GITHUB_GIT_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
GITLAB_USER = os.environ.get("GITLAB_USER", "oauth2")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
BITBUCKET_USER = os.environ.get("BITBUCKET_USERNAME", "")
BITBUCKET_TOKEN = os.environ.get("BITBUCKET_APP_PASSWORD", "")

# System Utility Binaries
TMUX_BIN = os.environ.get("TMUX_BIN", "tmux")
UPTIME_BIN = os.environ.get("UPTIME_BIN", "uptime")
DF_BIN = os.environ.get("DF_BIN", "df")
AIDER_BIN = os.environ.get("AIDER_BIN", "aider")

# Metadata Storage Files
TOPICS_FILE = WORKSPACE / ".agent_topics.json"
CUSTOM_CMDS_FILE = WORKSPACE / ".custom_commands.json"
OBSIDIAN_CMDS_FILE = OBSIDIAN_VAULT / "Config" / "commands.json"

# Set of Built-in Commands Reserved by System
BUILTIN_COMMANDS = {
    "start", "help", "status", "models", "modelhelp", "aihelp", "projects", "newrepo", "create",
    "bind", "unbind", "clone", "pull", "push", "branch", "diff", "vault",
    "note", "chat", "gemini", "gpt4", "task", "claude", "exec", "addcmd", "alias", "delcmd",
    "removecmd", "customcmds", "cmds", "aliases", "createtopic", "topic"
}
