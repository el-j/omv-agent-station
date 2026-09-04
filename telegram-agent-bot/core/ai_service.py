"""
Model capability guide generation for /modelhelp.
"""

import os
from pathlib import Path

import yaml
from .config import logger

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
    `litellm/config.yaml` sibling."""
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
