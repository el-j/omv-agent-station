"""
Per-channel/scope Active Task Registry.
Tracks the single in-flight background command (exec/task/claude) for a given
scope key (e.g. (channel_id, thread_id)) so it can be reported on and
cancelled via /cancel, and so a new command is rejected instead of silently
racing a prior one against the same git working directory.

Used directly by discord-agent-bot and signal-agent-bot. telegram-agent-bot
currently has its own equivalent at telegram-agent-bot/core/task_registry.py
predating this shared version; consolidating that is tracked separately.
"""

from dataclasses import dataclass
from typing import Optional

import asyncio


@dataclass
class RunningTask:
    label: str
    asyncio_task: asyncio.Task
    proc: Optional[asyncio.subprocess.Process] = None


_active: dict[tuple, RunningTask] = {}


def _key(*scope) -> tuple:
    return tuple(scope)


def start(*scope, label: str, asyncio_task: asyncio.Task) -> None:
    """Registers a newly launched background command as the active task for this scope."""
    _active[_key(*scope)] = RunningTask(label=label, asyncio_task=asyncio_task)


def attach_proc(*scope, proc: asyncio.subprocess.Process) -> None:
    """Attaches the live subprocess handle once spawned, so /cancel can kill it directly."""
    entry = _active.get(_key(*scope))
    if entry is not None:
        entry.proc = proc


def get(*scope) -> Optional[RunningTask]:
    return _active.get(_key(*scope))


def finish(*scope) -> None:
    """Clears the active task entry once a command finishes, fails, or is cancelled."""
    _active.pop(_key(*scope), None)


async def cancel(*scope) -> Optional[str]:
    """Kills the active subprocess (if any) and cancels its wrapping task. Returns the task's
    label if something was cancelled, or None if nothing was running in this scope."""
    entry = _active.pop(_key(*scope), None)
    if entry is None:
        return None

    if entry.proc is not None and entry.proc.returncode is None:
        try:
            entry.proc.kill()
        except ProcessLookupError:
            pass

    if not entry.asyncio_task.done():
        entry.asyncio_task.cancel()

    return entry.label
