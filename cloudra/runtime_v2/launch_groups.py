"""Lightweight launch groups for non-blocking sub-agent swarms.

A launch group owns a set of child items and a max concurrency.  The
permission lifecycle covers the child's whole lifetime: the worker does not
release a slot when ``spawn`` returns, but only when the child reaches a
terminal state.  Groups are deliberately in-memory/event-adjacent in this
module; the authoritative event log continues to hold agent lifecycle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from cloudra.runtime_v2.schemas import AgentSession, AgentState

ItemState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
GroupState = Literal["running", "cancelled", "finished"]
_TERMINAL = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}


@dataclass
class LaunchGroupItem:
    item_id: str
    query: str
    state: ItemState = "queued"
    child_session_id: str = ""
    error: str = ""


@dataclass
class LaunchGroup:
    group_id: str
    parent_session_id: str
    items: list[LaunchGroupItem]
    max_concurrency: int
    # The spawner is part of the group identity.  A manager is shared by the
    # runtime, but each group must retain its project/parent/role closure.
    spawner: Callable[[str], Any] | None = field(default=None, repr=False)
    state: GroupState = "running"
    _task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def pending_count(self) -> int:
        return sum(1 for i in self.items if i.state == "queued")

    @property
    def running_count(self) -> int:
        return sum(1 for i in self.items if i.state == "running")

    def summary(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "parent_session_id": self.parent_session_id,
            "state": self.state,
            "max_concurrency": self.max_concurrency,
            "pending_count": self.pending_count,
            "running_count": self.running_count,
            "items": [
                {
                    "item_id": item.item_id,
                    "state": item.state,
                    "child_session_id": item.child_session_id,
                    "error": item.error,
                }
                for item in self.items
            ],
        }


class LaunchGroupManager:
    """Process-local launch group worker; one task per group.

    ``spawner`` is an async callable ``(query) -> AgentSession``.  The worker
    starts at most ``max_concurrency`` children and waits for each to become
    terminal before starting the next queued item.
    """

    def __init__(self, *, spawner: Callable[[str], Any]) -> None:
        self._spawner = spawner
        self._groups: dict[str, LaunchGroup] = {}

    def create(
        self,
        *,
        group_id: str,
        parent_session_id: str,
        items: list[tuple[str, str]],
        max_concurrency: int,
        spawner: Callable[[str], Any] | None = None,
    ) -> LaunchGroup:
        group = LaunchGroup(
            group_id=group_id,
            parent_session_id=parent_session_id,
            items=[
                LaunchGroupItem(item_id=item_id, query=query)
                for item_id, query in items
            ],
            max_concurrency=max_concurrency,
            spawner=spawner or self._spawner,
        )
        self._groups[group_id] = group
        group._task = asyncio.create_task(self._run(group))
        return group

    def get(self, group_id: str) -> LaunchGroup | None:
        return self._groups.get(group_id)

    async def _run(self, group: LaunchGroup) -> None:
        sem = asyncio.Semaphore(group.max_concurrency)

        async def run_one(item: LaunchGroupItem) -> None:
            try:
                async with sem:
                    # Waiting for a slot is still queued.  Mark running only
                    # once the permit is acquired so the public counters
                    # describe actual child lifetimes.
                    if group.state == "cancelled":
                        item.state = "cancelled"
                        return
                    item.state = "running"
                    child = await group.spawner(item.query)
                    item.child_session_id = child.id
                    await self._wait_terminal(child)
                    item.state = (
                        "succeeded"
                        if child.state is AgentState.SUCCEEDED
                        else "failed" if child.state is AgentState.FAILED else "cancelled"
                    )
            except asyncio.CancelledError:
                item.state = "cancelled"
                raise
            except Exception as exc:
                item.state = "failed"
                item.error = str(exc)

        await asyncio.gather(*(run_one(item) for item in group.items))
        if group.state != "cancelled":
            group.state = "finished"

    @staticmethod
    async def _wait_terminal(child: AgentSession) -> AgentSession:
        if child.state in _TERMINAL:
            return child
        # AgentHost state changes are published via the core event hub, but the
        # spawner may return a plain object in tests.  Polling is the portable
        # fallback for launch-group unit tests.
        # This is a production lifecycle wait, not a test timeout.  The
        # semaphore remains held until the child reaches a terminal state.
        while True:
            if child.state in _TERMINAL:
                return child
            await asyncio.sleep(0.01)

    async def cancel(self, group_id: str) -> LaunchGroup | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        group.state = "cancelled"
        if group._task is not None:
            group._task.cancel()
            try:
                await group._task
            except asyncio.CancelledError:
                pass
        for item in group.items:
            if item.state == "queued":
                item.state = "cancelled"
        return group
