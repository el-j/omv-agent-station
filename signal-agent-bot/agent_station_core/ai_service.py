"""
AI Gateway and Intelligence Querying Service.
Handles LiteLLM client interactions, smart model fallbacks, and model capability guides.
"""

import os
from pathlib import Path

import httpx
import yaml
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

async def suggest_tags(text: str, max_tags: int = 5, model: str = "coder-fast") -> list[str]:
    """Asks the LLM gateway for a short list of keyword tags describing `text`.

    Mirrors list_ai_models' fallback discipline: never raises, and returns an
    empty list (not an error) on any failure so callers can unconditionally
    merge the result into an existing tag list."""
    if not text or not text.strip():
        return []
    try:
        response = await ai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Extract up to {max_tags} short keyword tags for the given text. "
                        "Reply with ONLY the tags as a comma-separated list, lowercase, "
                        "no numbering, no explanation, no hashtags."
                    ),
                },
                {"role": "user", "content": text[:4000]},
            ],
            temperature=0.2,
            max_tokens=64,
        )
        raw = response.choices[0].message.content or ""
        tags = [t.strip().lower().replace(" ", "-") for t in raw.split(",")]
        return [t for t in tags if t][:max_tags]
    except Exception as e:
        logger.warning(f"Tag suggestion failed on model {model}: {e}")
        return []

async def list_ai_models() -> tuple[list[str], bool]:
    """Retrieves active models from the LiteLLM proxy.

    Returns (models, live) -- live is False whenever the proxy call failed
    and the hardcoded fallback list is being returned instead, so callers
    can tell users the list may be stale rather than presenting it as a
    confirmed-reachable live gateway read."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{LITELLM_BASE}/models",
                headers={"Authorization": f"Bearer {LITELLM_KEY}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                return [m.get("id") for m in data.get("data", [])], True
    except Exception as e:
        logger.warning(f"Could not fetch models from LiteLLM: {e}")
    return ["coder-smart", "gemini-3.6-flash", "github-gpt-4o", "reasoning-heavy", "claude"], False

# Usage/description blurbs for the virtual routers -- this is the one piece of
# /modelhelp that genuinely can't be derived from litellm/config.yaml (it's
# product framing, not config). Everything else below (which models are in
# each router's pool, and its router-level fallback chain) is generated
# straight from the live YAML so it can't go stale the way the old
# hand-maintained markdown strings repeatedly did (see issue #13, #68).
_ROUTER_USAGE_HINTS = {
    "coder-fast": ("⚡", "Triage, repo mapping, and quick single-file changes.", "`/gemini <prompt>` or `/chat -m coder-fast <prompt>`"),
    "coder-smart": ("🚀", "Autonomous agentic coding loops, deep bug-fixing, refactoring.", "`/chat <prompt>` or `/task <project> <prompt>`"),
    "reasoning-heavy": ("🧠", "Architecture design, math, and deep chain-of-thought analysis.", "`/chat -m reasoning-heavy <prompt>`"),
}
_DEFAULT_ROUTER_HINT = ("🔀", "Multi-deployment virtual router.", "`/chat -m <router> <prompt>`")

_STATIC_FALLBACK_MODELHELP = (
    "📖 *OMV Agent Station — AI Models Guide*\n\n"
    "⚠️ Could not read `litellm/config.yaml` to generate the live model guide.\n\n"
    "The three smart routers are `coder-fast`, `coder-smart`, and `reasoning-heavy` -- "
    "use `/models` to see which upstream models are actually reachable right now, "
    "or `/chat -m <router> <prompt>` to query one directly.\n\n"
    "🛠️ *`claude`* (Claude Code CLI)\n"
    "• *Best for:* Multi-file workspace edits & automated git workflows.\n"
    "• *Usage:* `/claude <prompt>`"
)

def _find_litellm_config_path() -> Path | None:
    """Locates litellm/config.yaml. Checks LITELLM_CONFIG_YAML_PATH first (set
    by docker-compose.yml, which mounts the real file into every bot
    container), then walks up from this module's directory looking for a
    `litellm/config.yaml` sibling -- this works both for the root
    agent_station_core/ package (used by tests) and the per-bot copies
    (telegram-agent-bot/agent_station_core/, etc.) without any hardcoded
    path-depth assumption."""
    env_path = os.environ.get("LITELLM_CONFIG_YAML_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    here = Path(__file__).resolve().parent
    for ancestor in [here, *here.parents]:
        candidate = ancestor / "litellm" / "config.yaml"
        if candidate.is_file():
            return candidate
    return None

def _load_litellm_config() -> dict | None:
    path = _find_litellm_config_path()
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not read litellm config for modelhelp generation: {e}")
        return None

def get_modelhelp_markdown() -> str:
    """Generates the /modelhelp guide directly from litellm/config.yaml's
    model_list and router_settings.fallbacks, instead of hand-maintained
    strings that go stale every time the config changes (issue #13, #68)."""
    config = _load_litellm_config()
    if not config or not config.get("model_list"):
        return _STATIC_FALLBACK_MODELHELP

    groups: dict[str, list[str]] = {}
    for deployment in config["model_list"]:
        name = deployment.get("model_name")
        upstream = (deployment.get("litellm_params") or {}).get("model", "?")
        if not name:
            continue
        groups.setdefault(name, []).append(upstream)

    fallbacks: dict[str, list[str]] = {}
    for fb_entry in (config.get("router_settings") or {}).get("fallbacks", []) or []:
        if isinstance(fb_entry, dict):
            for k, v in fb_entry.items():
                fallbacks[k] = v

    router_names = [name for name, deployments in groups.items() if len(deployments) > 1]
    direct_names = [name for name, deployments in groups.items() if len(deployments) == 1]

    lines = [
        "📖 *OMV Agent Station — AI Models Guide*",
        "_(generated live from litellm/config.yaml)_",
        "",
        "*Smart Virtual Routers:*",
    ]

    for name in router_names:
        icon, desc, usage = _ROUTER_USAGE_HINTS.get(name, _DEFAULT_ROUTER_HINT)
        chain = " ➔ ".join(f"`{m}`" for m in groups[name])
        lines.append(f"\n{icon} *`{name}`*")
        lines.append(f"• {desc}")
        lines.append(f"• Pool order: {chain}")
        if name in fallbacks:
            fb_chain = " ➔ ".join(f"`{m}`" for m in fallbacks[name])
            lines.append(f"• If the whole pool fails: {fb_chain}")
        lines.append(f"• Usage: {usage}")

    if direct_names:
        lines.append("")
        lines.append(f"*Direct Model Access ({len(direct_names)}):*")
        lines.append(", ".join(f"`{n}`" for n in sorted(direct_names)))
        lines.append("\nQuery any of the above directly with `/chat -m <name> <prompt>`.")

    lines.append("")
    lines.append("🛠️ *`claude`* (Claude Code CLI, not a LiteLLM route)")
    lines.append("• *Best for:* Multi-file workspace edits & automated git workflows.")
    lines.append("• *Usage:* `/claude <prompt>`")

    return "\n".join(lines)
