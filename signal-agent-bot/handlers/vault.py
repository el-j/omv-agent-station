"""
Obsidian Second-Brain Note-Taking Handlers.
"""

from datetime import datetime

from agent_station_core import save_obsidian_note, list_vault_notes, suggest_tags
from core.messaging import send_signal_message


async def note(sender: str, args: list[str]):
    """Saves a quick note into the Obsidian vault (Title | Content, or Content alone)."""
    if not args:
        await send_signal_message(sender, "Usage: /note <Title> | <Content>")
        return
    raw = " ".join(args)
    if "|" in raw:
        title, content = raw.split("|", 1)
    else:
        title = f"Quick Note {datetime.now().strftime('%Y-%m-%d %H%M')}"
        content = raw
    tags = await suggest_tags(content.strip())
    res = save_obsidian_note(title.strip(), content.strip(), extra_tags=tags)
    if res["success"]:
        await send_signal_message(sender, f"✅ Note Saved to Obsidian: {res['path']}")
    else:
        await send_signal_message(sender, f"❌ Failed to save note: {res.get('error')}")


async def vault(sender: str, args: list[str]):
    """Lists the most recently modified notes in the Obsidian vault."""
    res = list_vault_notes()
    if res["success"]:
        recent_str = "\n".join([f"• {f}" for f in res["recent"]]) if res["recent"] else "No notes found."
        await send_signal_message(sender, f"📓 Obsidian Vault ({res['total_notes']} notes):\n\n{recent_str}")
    else:
        await send_signal_message(sender, f"❌ Error: {res.get('error')}")
