"""
User-Defined Dynamic Custom Commands & Template Expansions.
Allows creating and hot-reloading dynamic shortcuts stored on disk and mirrored to Obsidian.
"""

from discord.ext import commands

from agent_station_core import (
    BUILTIN_COMMANDS,
    sanitize_cmd_name,
    load_custom_commands,
    save_custom_commands,
)
from core.security import check_auth


async def addcmd_cmd(ctx: commands.Context, name: str = "", *, template: str = ""):
    """Registers a new custom shortcut, rejecting names that shadow a real built-in command."""
    if not await check_auth(ctx):
        return
    if not name or not template:
        await ctx.reply("Usage: `/addcmd <command-name> <command-template>`")
        return
    san_name = sanitize_cmd_name(name)
    if not san_name:
        await ctx.reply("❌ Invalid command name format.")
        return
    if san_name in BUILTIN_COMMANDS:
        await ctx.reply(f"❌ `{san_name}` is a reserved built-in command and cannot be overridden.")
        return
    cmds = load_custom_commands()
    cmds[san_name] = template
    save_custom_commands(cmds)
    await ctx.reply(f"✅ **Custom Shortcut Registered:** `/{san_name}` ➔ `{template}`")


async def delcmd_cmd(ctx: commands.Context, name: str = ""):
    """Deletes a previously registered custom shortcut."""
    if not await check_auth(ctx):
        return
    san_name = sanitize_cmd_name(name)
    if not san_name:
        await ctx.reply("Usage: `/delcmd <command-name>`")
        return
    cmds = load_custom_commands()
    if san_name in cmds:
        del cmds[san_name]
        save_custom_commands(cmds)
        await ctx.reply(f"✅ Deleted shortcut `/{san_name}`.")
    else:
        await ctx.reply(f"⚠️ Shortcut `/{san_name}` not found.")


async def customcmds_cmd(ctx: commands.Context):
    """Lists every registered custom shortcut and its expansion template."""
    if not await check_auth(ctx):
        return
    cmds = load_custom_commands()
    if not cmds:
        await ctx.reply("📋 No custom shortcuts configured yet. Create one with `/addcmd`.")
        return
    lines = [f"• `/{k}` ➔ `{v}`" for k, v in sorted(cmds.items())]
    await ctx.reply(f"⚡ **Custom Shortcuts ({len(cmds)}):**\n\n" + "\n".join(lines))
