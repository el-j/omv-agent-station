"""
Channel-to-Project Binding.
Discord has no forum-topic auto-creation like Telegram's -- users bind an
existing channel/thread to a project manually with /bind.
"""

from discord.ext import commands

from agent_station_core import WORKSPACE, sanitize_project_path, set_bound_project, remove_bound_project
from core.security import check_auth, channel_scope


async def bind_cmd(ctx: commands.Context, project_name: str = ""):
    """Binds the current channel/thread to a workspace project."""
    if not await check_auth(ctx):
        return
    if not project_name:
        await ctx.reply("Usage: `/bind <project-name>`")
        return
    p_dir = sanitize_project_path(WORKSPACE, project_name)
    if not p_dir or not p_dir.exists():
        await ctx.reply(f"❌ Project `{project_name}` not found in `/data/workspace`.")
        return
    channel_id, thread_id = channel_scope(ctx)
    set_bound_project(channel_id, thread_id, project_name)
    await ctx.reply(f"✅ Channel bound to project `{project_name}`. All tasks now target this repo.")


async def unbind_cmd(ctx: commands.Context):
    """Removes the project binding for the current channel/thread."""
    if not await check_auth(ctx):
        return
    channel_id, thread_id = channel_scope(ctx)
    remove_bound_project(channel_id, thread_id)
    await ctx.reply("✅ Unbound project context from this channel.")
