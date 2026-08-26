"""
Autonomous Coding Agent, Shell Execution, and Telemetry Service.
Dispatches Aider, Claude Code CLI, and shell commands in isolated subprocesses.
"""

import asyncio
import subprocess  # nosec B404
from pathlib import Path
from .config import (
    AIDER_BIN,
    CLAUDE_BIN,
    GIT_BIN,
    TMUX_BIN,
    UPTIME_BIN,
    DF_BIN,
    LITELLM_BASE,
    LITELLM_KEY,
    WORKSPACE,
    logger,
)

async def run_autonomous_task(project_dir: Path, instructions: str, session_id: str, task_branch: str) -> dict:
    """Executes the autonomous agent (Aider with LiteLLM proxy), auto-commits, and pushes branch."""
    try:
        is_git = (project_dir / ".git").exists()
        if is_git:
            await asyncio.create_subprocess_exec(GIT_BIN, "checkout", "-B", task_branch, cwd=str(project_dir))  # nosec B603,B607

        cmd = [
            AIDER_BIN,
            "--openai-api-base", f"{LITELLM_BASE}/v1",
            "--openai-api-key", LITELLM_KEY,
            "--model", "openai/coder-smart",
            "--message", instructions,
            "--auto-commits",
            "--no-git-commit-verify"
        ]

        agent_auth_file = Path("/root/.anthropic/token")
        if agent_auth_file.exists():
            cmd.extend(["--anthropic-api-key", agent_auth_file.read_text().strip()])

        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            *cmd,
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if is_git:
            push_proc = await asyncio.create_subprocess_exec(GIT_BIN, "push", "-u", "origin", task_branch, cwd=str(project_dir))  # nosec B603,B607
            await push_proc.communicate()

        summary = out if len(out) > 0 else err
        return {"success": proc.returncode == 0, "summary": summary, "task_branch": task_branch}
    except Exception as e:
        logger.error(f"Error in autonomous agent execution: {e}", exc_info=True)
        return {"success": False, "error": str(e), "task_branch": task_branch}

async def run_claude_cli(work_dir: Path, prompt: str) -> dict:
    """Executes Claude Code CLI in headless print mode."""
    try:
        proc = await asyncio.create_subprocess_exec(  # nosec B603,B607
            CLAUDE_BIN, "-p", prompt, "--print",
            cwd=str(work_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        return {"success": proc.returncode == 0, "output": out, "error": err}
    except FileNotFoundError:
        return {"success": False, "error": "Claude Code CLI not installed or not in PATH."}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def run_shell_exec(cmd: str, cwd: Path = WORKSPACE) -> dict:
    """Executes an arbitrary shell command within the workspace."""
    try:
        proc = await asyncio.create_subprocess_shell(  # nosec B602
            cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        result = (out + "\n" + err).strip() or "(No output)"
        return {"success": proc.returncode == 0, "output": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_system_status() -> dict:
    """Collects system uptime, disk usage, and active tmux sessions."""
    try:
        tmux_out = subprocess.check_output([TMUX_BIN, "list-sessions"], stderr=subprocess.STDOUT, text=True).strip()  # nosec B603,B607
    except Exception:
        tmux_out = "No active tmux sessions."

    try:
        uptime_out = subprocess.check_output([UPTIME_BIN], text=True).strip()  # nosec B603,B607
        df_out = subprocess.check_output([DF_BIN, "-h", str(WORKSPACE)], text=True).strip().splitlines()[-1]  # nosec B603,B607
    except Exception:
        uptime_out = "N/A"
        df_out = "N/A"

    return {
        "uptime": uptime_out,
        "disk": df_out,
        "tmux": tmux_out
    }
