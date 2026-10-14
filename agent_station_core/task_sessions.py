"""
Per-Chat/Topic Autonomous Task Session Continuity.

Tracks the last agent branch + aider session used by /task in a given
(chat_id, thread_id) scope, so a second /task call in the same bound topic
resumes the same branch and aider chat history instead of starting over --
mirrors topics_service.py's binding-file pattern exactly.
"""

import json
from .config import TASK_SESSIONS_FILE, logger

def load_task_sessions() -> dict:
    """Loads chat/topic-to-session records from disk."""
    if TASK_SESSIONS_FILE.exists():
        try:
            with open(TASK_SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {TASK_SESSIONS_FILE}: {e}")
    return {}

def save_task_sessions(sessions: dict):
    """Saves chat/topic-to-session records to disk."""
    try:
        TASK_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TASK_SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write {TASK_SESSIONS_FILE}: {e}")

def get_task_session(chat_id: int | str, thread_id: int | str | None) -> dict | None:
    """Returns {"project": str, "session_id": str, "branch": str} for this
    scope, or None if no /task has run here yet (or it was cleared)."""
    sessions = load_task_sessions()
    key = f"{chat_id}:{thread_id}"
    return sessions.get(key)

def set_task_session(chat_id: int | str, thread_id: int | str | None, project: str, session_id: str, branch: str):
    """Records the branch/session a /task call in this scope just used, so
    the next /task here resumes it instead of starting fresh."""
    sessions = load_task_sessions()
    key = f"{chat_id}:{thread_id}"
    sessions[key] = {"project": project, "session_id": session_id, "branch": branch}
    save_task_sessions(sessions)

def clear_task_session(chat_id: int | str, thread_id: int | str | None):
    """Drops the stored session for this scope (used by /task --new)."""
    sessions = load_task_sessions()
    key = f"{chat_id}:{thread_id}"
    if key in sessions:
        del sessions[key]
        save_task_sessions(sessions)
