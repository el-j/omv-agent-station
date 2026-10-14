"""
Bare-URL Auto-Clone Detection and Conversational AI Message Router.
Signal's analog of Telegram's handlers/interactive.py (minus ForceReply
prompts, which have no Signal equivalent).
"""

from agent_station_core import query_ai_model
from core.messaging import send_signal_message


def rewrite_bare_github_url(text: str) -> str:
    """Rewrites a bare pasted GitHub URL into a /clone command, so pasting a
    link in a private chat automatically triggers a project clone."""
    if text.startswith("https://github.com/") or text.startswith("http://github.com/") or text.startswith("git@github.com:"):
        return f"/clone {text}"
    return text


async def route_freeform_chat(sender: str, text: str):
    """Answers any non-slash-command text directly via the smart-router AI chat."""
    res = await query_ai_model(text, model="coder-smart")
    ans = res["answer"] if res["success"] else f"❌ AI error: {res.get('error')}"
    await send_signal_message(sender, ans)
