"""
Direct AI Query Commands: smart-router chat plus per-model shortcuts, and the
live model catalog / capability reference.
"""

from agent_station_core import query_ai_model, list_ai_models, get_modelhelp_markdown
from core.messaging import send_signal_message


async def chat(sender: str, args: list[str]):
    """Queries the smart router (or an explicit -m model) and sends back the answer."""
    if not args:
        await send_signal_message(sender, "Usage: /chat [-m model] <your question>")
        return
    model = "coder-smart"
    prompt = " ".join(args)
    if len(args) > 2 and args[0] in ("-m", "--model"):
        model = args[1]
        prompt = " ".join(args[2:])
    await send_signal_message(sender, f"⏳ Querying {model}...")
    res = await query_ai_model(prompt, model=model)
    ans = res["answer"] if res["success"] else f"❌ AI Query error: {res.get('error')}"
    await send_signal_message(sender, ans)


async def gemini(sender: str, args: list[str]):
    """Shortcut for querying gemini-3.6-flash directly."""
    if not args:
        await send_signal_message(sender, "Usage: /gemini <prompt>")
        return
    res = await query_ai_model(" ".join(args), model="gemini-3.6-flash")
    ans = res["answer"] if res["success"] else f"❌ Error: {res.get('error')}"
    await send_signal_message(sender, ans)


async def gpt4(sender: str, args: list[str]):
    """Shortcut for querying github-gpt-4o directly."""
    if not args:
        await send_signal_message(sender, "Usage: /gpt4 <prompt>")
        return
    res = await query_ai_model(" ".join(args), model="github-gpt-4o")
    ans = res["answer"] if res["success"] else f"❌ Error: {res.get('error')}"
    await send_signal_message(sender, ans)


async def models(sender: str, args: list[str]):
    """Lists the active (or fallback) AI model catalog from the LiteLLM gateway."""
    model_list, live = await list_ai_models()
    model_str = "\n".join([f"• {m}" for m in model_list])
    label = "Active AI Models" if live else "⚠️ Fallback AI Models (LiteLLM gateway unreachable, list may be stale)"
    await send_signal_message(sender, f"🤖 {label} ({len(model_list)}):\n\n{model_str}\n\nRouters: coder-smart, reasoning-heavy")


async def modelhelp(sender: str, args: list[str]):
    """Sends the detailed model-tier/fallback-chain capability reference."""
    await send_signal_message(sender, get_modelhelp_markdown())
