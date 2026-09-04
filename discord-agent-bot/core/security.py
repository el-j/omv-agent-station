"""
Discord Authorization & Channel/Project Context Resolution.
Shared by discord_bot.py and every handlers/*.py module -- kept independent of
discord_bot.py itself so handler modules never need to import back from the
entrypoint (which would create a circular import).
"""

import os
import discord
from discord.ext import commands
from agent_station_core import logger, resolve_project_context_raw, WORKSPACE

ALLOWED_USER_ID = os.environ.get("DISCORD_ALLOWED_USER_ID")


def is_authorized(ctx: commands.Context) -> bool:
    """Verifies that the message sender matches DISCORD_ALLOWED_USER_ID."""
    if not ALLOWED_USER_ID:
        return True
    if not ctx.author:
        return False
    return str(ctx.author.id) == str(ALLOWED_USER_ID)


async def check_auth(ctx: commands.Context) -> bool:
    """Replies with an error if the user is unauthorized."""
    if not is_authorized(ctx):
        logger.warning(f"Unauthorized Discord access attempt from user ID: {ctx.author.id} ({ctx.author.name})")
        await ctx.reply("⛔ **Unauthorized access.** Configure your numeric Discord User ID in OMV Agent Station settings.")
        return False
    return True


def channel_scope(ctx: commands.Context) -> tuple[str, str | None]:
    """Resolves the stable (channel_id, thread_id) binding key for a context.

    A Discord Thread has its own stable id distinct from every message posted
    in it -- using ctx.message.id here (as this used to) makes every message
    look like a different thread, so a binding set by /bind can never be
    found again by a later message.
    """
    if isinstance(ctx.channel, discord.Thread):
        parent_id = ctx.channel.parent_id or ctx.channel.id
        return str(parent_id), str(ctx.channel.id)
    return str(ctx.channel.id), None


def resolve_ctx_project(ctx: commands.Context, args: list[str]) -> tuple[str | None, list[str]]:
    """Resolves project context based on thread ID or channel ID."""
    channel_id, thread_id = channel_scope(ctx)
    return resolve_project_context_raw(channel_id, thread_id, args, WORKSPACE)
