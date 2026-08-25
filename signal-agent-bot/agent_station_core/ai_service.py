"""
AI Gateway and Intelligence Querying Service.
Handles LiteLLM client interactions, smart model fallbacks, and model capability guides.
"""

import httpx
from openai import AsyncOpenAI
from .config import LITELLM_BASE, LITELLM_KEY, logger

# Global Async AI Client
ai_client = AsyncOpenAI(
    api_key=LITELLM_KEY,
    base_url=f"{LITELLM_BASE}/v1",
    timeout=120.0
)

async def query_ai_model(prompt: str, model: str = "coder-smart", system_prompt: str = "") -> dict:
    """Dispatches a prompt to LiteLLM with automatic fallback handling."""
    sys_msg = system_prompt or (
        "You are the OpenMediaVault AI Assistant running on a self-hosted server. "
        "Provide concise, practical, and highly accurate answers with code examples when appropriate."
    )
    try:
        response = await ai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content or "No response received."
        return {"success": True, "answer": answer, "model": model}
    except Exception as e:
        logger.error(f"AI query failed on model {model}: {e}")
        return {"success": False, "error": str(e), "model": model}

async def list_ai_models() -> list[str]:
    """Retrieves active models from the LiteLLM proxy."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{LITELLM_BASE}/models",
                headers={"Authorization": f"Bearer {LITELLM_KEY}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                return [m.get("id") for m in data.get("data", [])]
    except Exception as e:
        logger.warning(f"Could not fetch models from LiteLLM: {e}")
    return ["coder-smart", "gemini-3.6-flash", "github-gpt-4o", "reasoning-heavy", "claude"]

def get_modelhelp_markdown() -> str:
    """Returns comprehensive model documentation and capability guide."""
    return (
        "📖 *OMV Agent Station — AI Models Guide*\n\n"
        "⚡ *`gemini-3.6-flash`* (Google Gemini 2.0 Flash)\n"
        "• *Context:* 1,048,576 tokens | *Speed:* Ultra fast (< 1s)\n"
        "• *Best for:* Quick questions, documentation scans, regex, single-file edits.\n"
        "• *Usage:* `/gemini <prompt>`\n\n"
        "🚀 *`coder-smart`* (Multi-Tier Autonomous Router)\n"
        "• *Engines:* Gemini 2.0 Flash ➔ Claude 3.7 Sonnet ➔ DeepSeek R1\n"
        "• *Best for:* Agentic coding loops, deep refactoring, test generation.\n"
        "• *Usage:* `/chat <prompt>` or `/task <project> <prompt>`\n\n"
        "🧠 *`reasoning-heavy`* (Deep Chain-of-Thought)\n"
        "• *Engines:* DeepSeek-R1 ➔ Gemini 2.5 Pro ➔ OpenAI o3-mini\n"
        "• *Best for:* Math, system architecture, database optimization, algorithms.\n"
        "• *Usage:* `/chat -m reasoning-heavy <prompt>`\n\n"
        "🤖 *`github-gpt-4o`* (GitHub Marketplace)\n"
        "• *Context:* 128,000 tokens\n"
        "• *Best for:* High-quality GPT-4o intelligence included in GitHub accounts.\n"
        "• *Usage:* `/gpt4 <prompt>`\n\n"
        "🛠️ *`claude`* (Claude Code CLI)\n"
        "• *Best for:* Multi-file workspace edits & automated git workflows.\n"
        "• *Usage:* `/claude <prompt>`"
    )
