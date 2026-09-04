"""
Centralized Configuration and Environment Settings for Agent Station.
Shared across Telegram, Discord, and Signal relays.
"""

import os
import shutil
import logging
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("agent_station")

# Core AI Gateway Config
LITELLM_BASE = os.environ.get("LITELLM_API_BASE", "http://litellm:4000")
LITELLM_KEY = os.environ.get("LITELLM_API_KEY") or os.environ.get("LITELLM_MASTER_KEY", "sk-omv-secret-master-key")

# System & Workspace Directories
WORKSPACE = Path(os.environ.get("WORKSPACE_PATH") or os.environ.get("WORKSPACE_DIR", "/data/workspace"))
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH") or os.environ.get("OBSIDIAN_VAULT", "/data/obsidian"))

# Git Binary & Identity Credentials
GIT_BIN = shutil.which("git") or os.environ.get("GIT_BIN", "/usr/bin/git")
GIT_AUTHOR_NAME = os.environ.get("GIT_AUTHOR_NAME", "OMV AI Agent")
GIT_AUTHOR_EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "agent@omv-box.local")
GITHUB_USER = os.environ.get("GITHUB_USER", "")
GITHUB_TOKEN = os.environ.get("GITHUB_GIT_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
GITLAB_USER = os.environ.get("GITLAB_USER", "oauth2")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
BITBUCKET_USER = os.environ.get("BITBUCKET_USERNAME", "")
BITBUCKET_TOKEN = os.environ.get("BITBUCKET_APP_PASSWORD", "") or os.environ.get("BITBUCKET_PASS", "")

# System Utility Binaries
TMUX_BIN = shutil.which("tmux") or os.environ.get("TMUX_BIN", "/usr/bin/tmux")
UPTIME_BIN = shutil.which("uptime") or os.environ.get("UPTIME_BIN", "/usr/bin/uptime")
DF_BIN = shutil.which("df") or os.environ.get("DF_BIN", "/bin/df")
AIDER_BIN = shutil.which("aider") or os.environ.get("AIDER_BIN", "aider")
CLAUDE_BIN = shutil.which("claude") or "/usr/local/bin/claude"

# Storage Metadata Files
TOPICS_FILE = WORKSPACE / ".agent_topics.json"
CUSTOM_CMDS_FILE = WORKSPACE / ".custom_commands.json"
OBSIDIAN_CMDS_FILE = OBSIDIAN_VAULT / "Config" / "commands.json"

# Reserved System Commands
BUILTIN_COMMANDS = {
    "start", "help", "status", "models", "modelhelp", "aihelp", "projects", "newrepo", "create",
    "bind", "unbind", "clone", "pull", "push", "branch", "diff", "vault",
    "note", "chat", "gemini", "gpt4", "task", "claude", "exec", "cancel", "stop", "addcmd", "alias", "delcmd",
    "removecmd", "customcmds", "cmds", "aliases", "createtopic", "topic"
}
