"""
User-Defined Dynamic Custom Commands & Template Expansions.
Allows creating and hot-reloading dynamic shortcuts stored on disk and mirrored to Obsidian.
"""

from agent_station_core import (
    BUILTIN_COMMANDS,
    sanitize_cmd_name,
    load_custom_commands,
    save_custom_commands,
    expand_custom_command,
)
from core.messaging import send_signal_message


def expand_shortcut(text: str) -> str:
    """Expands a leading /shortcut into its registered template, if any."""
    parts = text.lstrip("/").split(maxsplit=1)
    cmd_name = parts[0].lower()
    passed_args = parts[1] if len(parts) > 1 else ""
    expanded = expand_custom_command(cmd_name, passed_args)
    if expanded:
        return expanded if expanded.startswith("/") else f"/{expanded}"
    return text


async def addcmd(sender: str, args: list[str]):
    """Registers a new custom shortcut, rejecting names that shadow a real built-in command."""
    if len(args) < 2:
        await send_signal_message(sender, "Usage: /addcmd <command-name> <command-template>")
        return
    name = args[0]
    template = " ".join(args[1:])
    san_name = sanitize_cmd_name(name)
    if not san_name:
        await send_signal_message(sender, "❌ Invalid command name format.")
        return
    if san_name in BUILTIN_COMMANDS:
        await send_signal_message(sender, f"❌ {san_name} is a reserved built-in command and cannot be overridden.")
        return
    cmds = load_custom_commands()
    cmds[san_name] = template
    save_custom_commands(cmds)
    await send_signal_message(sender, f"✅ Custom Shortcut Registered: /{san_name} ➔ {template}")


async def delcmd(sender: str, args: list[str]):
    """Deletes a previously registered custom shortcut."""
    if not args:
        await send_signal_message(sender, "Usage: /delcmd <command-name>")
        return
    san_name = sanitize_cmd_name(args[0])
    if not san_name:
        await send_signal_message(sender, "Usage: /delcmd <command-name>")
        return
    cmds = load_custom_commands()
    if san_name in cmds:
        del cmds[san_name]
        save_custom_commands(cmds)
        await send_signal_message(sender, f"✅ Deleted shortcut /{san_name}.")
    else:
        await send_signal_message(sender, f"⚠️ Shortcut /{san_name} not found.")


async def customcmds(sender: str, args: list[str]):
    """Lists every registered custom shortcut and its expansion template."""
    cmds = load_custom_commands()
    if not cmds:
        await send_signal_message(sender, "📋 No custom shortcuts configured yet. Create one with /addcmd.")
        return
    lines = [f"• /{k} ➔ {v}" for k, v in sorted(cmds.items())]
    await send_signal_message(sender, f"⚡ Custom Shortcuts ({len(cmds)}):\n\n" + "\n".join(lines))
