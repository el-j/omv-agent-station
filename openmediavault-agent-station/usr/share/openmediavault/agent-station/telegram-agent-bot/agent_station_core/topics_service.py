"""
Thread, Channel, and Topic Context Binding Service.
Maps sub-channel / thread IDs to project workspaces for Telegram, Discord, and Signal.
"""

import json
from pathlib import Path
from .config import TOPICS_FILE, WORKSPACE, logger

def load_topic_bindings() -> dict:
    """Loads thread-to-project bindings from disk."""
    if TOPICS_FILE.exists():
        try:
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {TOPICS_FILE}: {e}")
    return {}

def save_topic_bindings(bindings: dict):
    """Saves thread-to-project bindings to disk."""
    try:
        TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(bindings, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write {TOPICS_FILE}: {e}")

def get_bound_project(chat_id: int | str, thread_id: int | str | None) -> str | None:
    """Returns the project folder name bound to a given (chat_id, thread_id) pair."""
    if not thread_id:
        return None
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    return bindings.get(key)

def set_bound_project(chat_id: int | str, thread_id: int | str, project_name: str):
    """Binds a project folder name to a given (chat_id, thread_id) pair."""
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    bindings[key] = project_name
    save_topic_bindings(bindings)

def remove_bound_project(chat_id: int | str, thread_id: int | str):
    """Removes the project binding for a given (chat_id, thread_id) pair."""
    bindings = load_topic_bindings()
    key = f"{chat_id}:{thread_id}"
    if key in bindings:
        del bindings[key]
        save_topic_bindings(bindings)

def resolve_project_context_raw(chat_id: int | str, thread_id: int | str | None, args: list[str], workspace: Path = WORKSPACE) -> tuple[str | None, list[str]]:
    """Resolves project name and remaining args based on explicit arg or bound thread context."""
    bound_project = get_bound_project(chat_id, thread_id)
    if not args:
        return (bound_project, [])

    first_arg = args[0]
    candidate_dir = workspace / first_arg
    if candidate_dir.exists() and candidate_dir.is_dir() and not first_arg.startswith("."):
        return (first_arg, args[1:])

    if bound_project:
        return (bound_project, args)

    return (first_arg, args[1:])
