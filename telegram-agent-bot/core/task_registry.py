"""
Per-chat/topic Active Task Registry.
Tracks the single in-flight background command (exec/task/claude) for a given
(chat_id, thread_id) scope so it can be reported on and cancelled via /cancel,
and so a new command is rejected instead of silently racing/blocking a prior one.
"""

from dataclasses import dataclass
from typing import Optional

import asyncio


@dataclass
class RunningTask:
    label: str
    asyncio_task: asyncio.Task
    proc: Optional[asyncio.subprocess.Process] = None


_active: dict[tuple[int, Optional[int]], RunningTask] = {}


def _key(chat_id: int, thread_id: Optional[int]) -> tuple[int, Optional[int]]:
    return (chat_id, thread_id)


def start(chat_id: int, thread_id: Optional[int], label: str, asyncio_task: asyncio.Task) -> None:
    """Registers a newly launched background command as the active task for this scope."""
    _active[_key(chat_id, thread_id)] = RunningTask(label=label, asyncio_task=asyncio_task)


def attach_proc(chat_id: int, thread_id: Optional[int], proc: asyncio.subprocess.Process) -> None:
    """Attaches the live subprocess handle once spawned, so /cancel can kill it directly."""
    entry = _active.get(_key(chat_id, thread_id))
    if entry is not None:
        entry.proc = proc


def get(chat_id: int, thread_id: Optional[int]) -> Optional[RunningTask]:
    return _active.get(_key(chat_id, thread_id))


def finish(chat_id: int, thread_id: Optional[int]) -> None:
    """Clears the active task entry once a command finishes, fails, or is cancelled."""
    _active.pop(_key(chat_id, thread_id), None)


async def cancel(chat_id: int, thread_id: Optional[int]) -> Optional[str]:
    """Kills the active subprocess (if any) and cancels its wrapping task. Returns the task's
    label if something was cancelled, or None if nothing was running in this scope."""
    entry = _active.pop(_key(chat_id, thread_id), None)
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
