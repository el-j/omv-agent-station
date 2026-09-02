"""
Direct AI Query Commands: smart-router chat plus per-model shortcuts, and the
live model catalog / capability reference.
"""

from discord.ext import commands

from agent_station_core import query_ai_model, list_ai_models, get_modelhelp_markdown
from core.security import check_auth


async def chat_cmd(ctx: commands.Context, *, message: str = ""):
    """Queries the smart router (or an explicit -m model) and replies with the answer."""
    if not await check_auth(ctx):
        return
    if not message:
        await ctx.reply("Usage: `/chat [-m model] <your question>`")
        return

    parts = message.split()
    model = "coder-smart"
    prompt = message
    if parts and parts[0] in ("-m", "--model") and len(parts) > 2:
        model = parts[1]
        prompt = " ".join(parts[2:])

    msg = await ctx.reply(f"⏳ Querying `{model}`...")
    res = await query_ai_model(prompt, model=model)
    if res["success"]:
        ans = res["answer"]
        if len(ans) > 1900:
            ans = ans[:1900] + "\n...(truncated)"
        await msg.edit(content=ans)
    else:
        await msg.edit(content=f"❌ AI Query error: {res.get('error', 'Unknown error')}")


async def gemini_cmd(ctx: commands.Context, *, prompt: str = ""):
    """Shortcut for /chat -m gemini-3.6-flash."""
    if not await check_auth(ctx):
        return
    if not prompt:
        await ctx.reply("Usage: `/gemini <your question>`")
        return
    await chat_cmd(ctx, message=f"-m gemini-3.6-flash {prompt}")


async def gpt4_cmd(ctx: commands.Context, *, prompt: str = ""):
    """Shortcut for /chat -m github-gpt-4o."""
    if not await check_auth(ctx):
        return
    if not prompt:
        await ctx.reply("Usage: `/gpt4 <your question>`")
        return
    await chat_cmd(ctx, message=f"-m github-gpt-4o {prompt}")


async def models_cmd(ctx: commands.Context):
    """Lists the active (or fallback) AI model catalog from the LiteLLM gateway."""
    if not await check_auth(ctx):
        return
    models, live = await list_ai_models()
    model_str = "\n".join([f"• `{m}`" for m in models])
    label = "Active AI Models" if live else "⚠️ Fallback AI Models (LiteLLM gateway unreachable, list may be stale)"
    await ctx.reply(f"🤖 **{label} ({len(models)}):**\n\n{model_str}\n\n*Routers:* `coder-smart`, `reasoning-heavy`")


async def modelhelp_cmd(ctx: commands.Context):
    """Replies with the detailed model-tier/fallback-chain capability reference."""
    if not await check_auth(ctx):
        return
    text = get_modelhelp_markdown().replace("*", "**")
    await ctx.reply(text)
