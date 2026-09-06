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

    ``track``（可选）在 worker 任务创建时回调
    ``(parent_session_id, task, label)``——生产接线把它登记进 runner 的
    ``track_background``，使用户取消与 shutdown 都能取消并 await 组任务
    （裸 create_task 两者都碰不到）。
    """

    def __init__(
        self,
        *,
        spawner: Callable[[str], Any],
        track: Callable[[str, asyncio.Task, str], None] | None = None,
    ) -> None:
        self._spawner = spawner
        self._track = track
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
        # group_id 冲突绝不静默覆盖：重复 id 说明派生方有 bug，响亮拒绝。
        if group_id in self._groups:
            raise ValueError(f"launch group {group_id!r} already exists; refusing to overwrite it")
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
        group._task = asyncio.create_task(self._run(group), name=f"launch_group:{group_id}")
        if self._track is not None:
            self._track(parent_session_id, group._task, f"launch_group:{group_id}")
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

    async def cancel_for_parent(self, parent_session_id: str) -> list[LaunchGroup]:
        """取消某 agent 持有的全部组（父 agent 取消的级联入口）。"""
        groups = [
            group
            for group in self._groups.values()
            if group.parent_session_id == parent_session_id
        ]
        for group in groups:
            await self.cancel(group.group_id)
        return groups

    async def cancel_all(self) -> None:
        """shutdown 用：取消全部组并 await，逐项落 cancelled。"""
        for group_id in list(self._groups):
            await self.cancel(group_id)
