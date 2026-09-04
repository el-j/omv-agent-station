"""
Obsidian Second-Brain Note-Taking Handlers.
"""

from datetime import datetime

from discord.ext import commands

from agent_station_core import save_obsidian_note, list_vault_notes
from core.security import check_auth


async def note_cmd(ctx: commands.Context, *, note_text: str = ""):
    """Saves a quick note into the Obsidian vault (Title | Content, or Content alone)."""
    if not await check_auth(ctx):
        return
    if not note_text:
        await ctx.reply("Usage: `/note <Title> | <Content>`")
        return
    if "|" in note_text:
        title, content = note_text.split("|", 1)
    else:
        title = f"Quick Note {datetime.now().strftime('%Y-%m-%d %H%M')}"
        content = note_text
    res = save_obsidian_note(title.strip(), content.strip())
    if res["success"]:
        await ctx.reply(f"✅ **Note Saved to Obsidian:** `{res['path']}`")
    else:
        await ctx.reply(f"❌ Failed to save note: {res.get('error')}")


async def vault_cmd(ctx: commands.Context):
    """Lists the most recently modified notes in the Obsidian vault."""
    if not await check_auth(ctx):
        return
    res = list_vault_notes()
    if res["success"]:
        recent_str = "\n".join([f"• `{f}`" for f in res["recent"]]) if res["recent"] else "No notes found."
        await ctx.reply(f"📓 **Obsidian Vault ({res['total_notes']} notes):**\n\n{recent_str}")
    else:
        await ctx.reply(f"❌ Error: {res.get('error')}")
