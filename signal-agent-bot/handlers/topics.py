"""
Chat-to-Project Binding.
Signal has no forum-topic auto-creation like Telegram's -- users bind their
1-on-1 chat to a project manually with /bind.
"""

from agent_station_core import WORKSPACE, sanitize_project_path, set_bound_project, remove_bound_project, get_bound_project
from core.messaging import send_signal_message


async def bind(sender: str, args: list[str]):
    """Binds the sender's chat to a workspace project (or shows current binding status)."""
    if not args:
        current_bound = get_bound_project(sender, None)
        status = f"Currently bound to: {current_bound}" if current_bound else "Not bound to any project."
        await send_signal_message(sender, f"🧵 Binding Status\n\n• {status}\n\nTo bind: /bind <project-name>\nTo unbind: /unbind")
        return
    project_name = args[0]
    p_dir = sanitize_project_path(WORKSPACE, project_name)
    if not p_dir or not p_dir.exists():
        await send_signal_message(sender, f"❌ Project {project_name} not found in /data/workspace.")
        return
    set_bound_project(sender, None, project_name)
    await send_signal_message(sender, f"✅ Bound! All commands and file uploads now target project {project_name}.")


async def unbind(sender: str, args: list[str]):
    """Removes the project binding for the sender's chat."""
    remove_bound_project(sender, None)
    await send_signal_message(sender, "✅ Unbound project context.")
