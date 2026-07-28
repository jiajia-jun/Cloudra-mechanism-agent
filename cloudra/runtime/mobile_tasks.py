"""Strongly referenced background tasks for the single-process mobile runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

_BACKGROUND_TASKS: set[asyncio.Task] = set()


def create_mobile_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Schedule ``coro`` and retain it until completion.

    Android child agents are asyncio tasks rather than subprocesses.  Keeping a
    strong reference prevents a fire-and-forget task from being garbage
    collected while it is still running.
    """

    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_discard_finished_task)
    return task


def _discard_finished_task(task: asyncio.Task) -> None:
    _BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        return
    # Retrieve the exception so asyncio does not emit an unhandled-task warning.
    # run_executor already records the failure in the session database.
    task.exception()


def active_mobile_task_count() -> int:
    """Return the number of live mobile tasks (primarily useful for diagnostics)."""

    return len(_BACKGROUND_TASKS)
