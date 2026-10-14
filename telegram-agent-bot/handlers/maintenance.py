"""
Chat-driven Housekeeping: /selftest, /selfheal, /update.

Deliberately check-and-report only -- none of these commands start, stop, or
rebuild anything. The bot process answering the command runs inside the very
container an update would restart, and this bot is meant to be the sole remote
access to the box while its operator is away, so an auto-apply that goes wrong
has no one around to fix it. Applying a fix means SSH access (the exact command
is always included in the report).
"""

import os
import subprocess  # nosec B404

import httpx

from telegram import Update
from telegram.ext import ContextTypes

from core.config import LITELLM_BASE, GIT_BIN, STACK_REPO, GITHUB_REPO_SLUG, logger
from core.security import check_auth
from core import task_registry
from .system import gather_status, chat_scope

_SSH_HINT = "cd /srv/dev-data/omv-agent-station && git pull && docker compose build && docker compose up -d"


def _read_deployed_commit() -> dict:
    """Reads the deployed commit/branch from the read-only /stack mount.
    Pure reads (rev-parse) -- never fetches, never writes, safe on a :ro mount."""
    if not (STACK_REPO / ".git").exists():
        return {"ok": False, "error": f"{STACK_REPO} is not a git checkout (is the STACK_DIR mount configured?)"}
    try:
        sha = subprocess.check_output(  # nosec B603,B607
            [GIT_BIN, "-C", str(STACK_REPO), "rev-parse", "HEAD"], text=True
        ).strip()
        branch = subprocess.check_output(  # nosec B603,B607
            [GIT_BIN, "-C", str(STACK_REPO), "rev-parse", "--abbrev-ref", "HEAD"], text=True
        ).strip()
        return {"ok": True, "sha": sha, "branch": branch}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _check_git_freshness() -> dict:
    """Compares the deployed commit against the live GitHub branch tip via the
    public compare API (no local fetch, no auth needed for a public repo).
    Never raises -- any failure just means the freshness check is unavailable,
    which callers report as a soft warning rather than treating as fatal."""
    local = _read_deployed_commit()
    if not local["ok"]:
        return {"ok": False, "error": local["error"]}

    url = f"https://api.github.com/repos/{GITHUB_REPO_SLUG}/compare/{local['sha']}...{local['branch']}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"Accept": "application/vnd.github+json"})
            if resp.status_code != 200:
                return {"ok": False, "error": f"GitHub API returned {resp.status_code}"}
            data = resp.json()
    except Exception as e:
        logger.warning(f"Freshness check failed: {e}")
        return {"ok": False, "error": str(e)}

    behind_by = data.get("ahead_by", 0)  # commits the branch has that local doesn't
    commits = [c["commit"]["message"].splitlines()[0] for c in data.get("commits", [])]
    return {
        "ok": True,
        "branch": local["branch"],
        "sha": local["sha"],
        "behind_by": behind_by,
        "commits": commits[-10:],
    }


async def _check_litellm() -> bool:
    """True if the LiteLLM gateway answers its own liveliness probe."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{LITELLM_BASE}/health/liveliness")
            return resp.status_code == 200
    except Exception:
        return False


def _configured_providers() -> list[str]:
    """Presence-only checks (never the values) of which AI providers have keys set."""
    flags = {
        "Gemini": "GEMINI_API_KEY",
        "Anthropic": "ANTHROPIC_API_KEY",
        "GitHub Models": "GITHUB_TOKEN",
        "GitLab": "GITLAB_TOKEN",
    }
    return [name for name, env_var in flags.items() if os.environ.get(env_var)]


async def selftest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full read-only health snapshot: system metrics, gateway reachability,
    deployed version freshness, active task, and configured providers."""
    if not await check_auth(update):
        return

    s = gather_status()
    litellm_ok = await _check_litellm()
    freshness = await _check_git_freshness()
    chat_id, thread_id = chat_scope(update)
    active = task_registry.get(chat_id, thread_id)
    providers = _configured_providers()

    if freshness["ok"]:
        if freshness["behind_by"] == 0:
            version_line = f"`{freshness['branch']}@{freshness['sha'][:7]}` (up to date)"
        else:
            version_line = f"`{freshness['branch']}@{freshness['sha'][:7]}` — {freshness['behind_by']} commit(s) behind origin"
    else:
        version_line = f"⚠️ could not check ({freshness['error']})"

    report = (
        f"🩺 *OMV Agent Station — Self-Test*\n\n"
        f"⏱️ *Uptime:* `{s['uptime']}`\n"
        f"🧠 *RAM:* `{s['ram']}`\n"
        f"💾 *Disk:* `{s['disk']}`\n"
        f"🔌 *LiteLLM Gateway:* {'✅ reachable' if litellm_ok else '❌ unreachable'}\n"
        f"🏷️ *Deployed Version:* {version_line}\n"
        f"🏃 *Active Task Here:* `{active.label if active else 'none'}`\n"
        f"🔑 *Configured Providers:* {', '.join(providers) if providers else 'none'}\n"
    )
    await update.effective_message.reply_text(report, parse_mode="Markdown")


async def selfheal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs the same checks as /selftest but reports only what's actually
    wrong, each paired with the exact SSH command to fix it. Never executes
    anything itself -- see the module docstring for why."""
    if not await check_auth(update):
        return

    s = gather_status()
    litellm_ok = await _check_litellm()
    freshness = await _check_git_freshness()

    problems: list[str] = []

    if not litellm_ok:
        problems.append(
            "❌ *LiteLLM gateway unreachable.*\n"
            "   Fix: `ssh root@<host> \"cd /srv/dev-data/omv-agent-station && "
            "docker compose restart litellm\"`"
        )

    if s["disk_pct"] is not None and s["disk_pct"] >= 90:
        problems.append(
            f"❌ *Disk {s['disk_pct']}% full.*\n"
            "   Fix: `ssh root@<host> \"docker system prune -f\"`"
        )

    if freshness["ok"] and freshness["behind_by"] > 0:
        problems.append(
            f"⚠️ *{freshness['behind_by']} commit(s) behind `origin/{freshness['branch']}`.*\n"
            f"   Fix: `ssh root@<host> \"{_SSH_HINT}\"`"
        )
    elif not freshness["ok"]:
        problems.append(f"⚠️ *Could not check for updates* ({freshness['error']}).")

    if not problems:
        await update.effective_message.reply_text("✅ Nothing to heal — everything checked out looks healthy.")
        return

    report = "🩹 *Self-Heal Report*\n\n" + "\n\n".join(problems)
    await update.effective_message.reply_text(report, parse_mode="Markdown")


async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reports how far the deployed build is behind origin. Does not pull or
    rebuild anything -- see the module docstring for why."""
    if not await check_auth(update):
        return

    freshness = await _check_git_freshness()
    if not freshness["ok"]:
        await update.effective_message.reply_text(f"⚠️ Could not check for updates: {freshness['error']}")
        return

    if freshness["behind_by"] == 0:
        await update.effective_message.reply_text(
            f"✅ Already up to date on `{freshness['branch']}@{freshness['sha'][:7]}`."
        )
        return

    commit_list = "\n".join(f"• {c}" for c in freshness["commits"]) or "(commit messages unavailable)"
    report = (
        f"🔄 *Update Available*\n\n"
        f"Currently on `{freshness['branch']}@{freshness['sha'][:7]}`, "
        f"*{freshness['behind_by']}* commit(s) behind:\n\n{commit_list}\n\n"
        f"To apply: `ssh root@<host> \"{_SSH_HINT}\"`"
    )
    await update.effective_message.reply_text(report, parse_mode="Markdown")
