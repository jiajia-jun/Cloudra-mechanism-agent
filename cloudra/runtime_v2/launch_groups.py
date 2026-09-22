"""Launch groups: event-sourced swarm batches (评审 5.2 后半).

一个 launch group 拥有若干 item 与并发上限，权限生命周期覆盖 child 的**整个**
生命（spawn 返回不释放名额，child 终态才释放），父取消级联到 worker 与已派发后代。

评审 5.2 之前本模块是纯进程内状态：重启后未派发的 queued item、组级状态和
``get_subagent_report(group_id=...)`` 查询能力全部消失。现在组的生命周期是**事件
投影**（与 agent 生命周期同一个事实源）：

- ``launch_group.created``          组清单（item_id + query + 并发上限）
- ``launch_group.item_dispatched``  某个 item 派发到 child session
- ``launch_group.item_finished``    item 终态（succeeded/failed/cancelled）
- ``launch_group.finished``         组终态（finished / cancelled / interrupted）

投影唯一写入点是 ``apply_event``（走 ``LaunchGroupManager.apply``），因此
``persistence.restore_core`` 的事件重放会把组清单原样重建。**恢复不重放外部
副作用**：重启后不会重新 spawn 任何 child，未终态的组被标记 ``interrupted``
（由用户显式重新派发），已存在的 child session 只做状态对账。

worker 任务本身仍是进程内的（``create_task`` 经 ``track`` 登记进 runner 的
``track_background``）：它只负责驱动 spawn 与等待 child 终态，可被取消；状态则
一律落事件，不靠内存。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal

from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.schemas import AgentSession, AgentState

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

logger = logging.getLogger(__name__)

ItemState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
GroupState = Literal["running", "cancelled", "finished", "interrupted"]
_TERMINAL = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}
_TERMINAL_GROUP_STATES = {"cancelled", "finished", "interrupted"}


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
    project_id: str = ""
    state: GroupState = "running"
    reason: str = ""
    #: 只属于活进程：组 worker 任务（恢复出来的组没有它，也不该有）。
    _task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def pending_count(self) -> int:
        return sum(1 for i in self.items if i.state == "queued")

    @property
    def running_count(self) -> int:
        return sum(1 for i in self.items if i.state == "running")

    def item(self, item_id: str) -> LaunchGroupItem | None:
        return next((i for i in self.items if i.item_id == item_id), None)

    def summary(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "parent_session_id": self.parent_session_id,
            "state": self.state,
            "reason": self.reason,
            "max_concurrency": self.max_concurrency,
            "pending_count": self.pending_count,
            "running_count": self.running_count,
            "items": [
                {
                    "item_id": item.item_id,
                    "query": item.query,
                    "state": item.state,
                    "child_session_id": item.child_session_id,
                    "error": item.error,
                }
                for item in self.items
            ],
        }


class LaunchGroupManager:
    """组的事件投影 + 进程内 worker（见模块 docstring）。"""

    def __init__(
        self,
        *,
        core: "RuntimeCore | None" = None,
        spawner: Callable[[str], Any] | None = None,
        track: Callable[[str, asyncio.Task, str], None] | None = None,
    ) -> None:
        self._core = core
        self._spawner = spawner
        self._track = track
        self._groups: dict[str, LaunchGroup] = {}

    # ------------------------------------------------------------------ 投影

    def configure(
        self,
        *,
        spawner: Callable[[str], Any] | None = None,
        track: Callable[[str, asyncio.Task, str], None] | None = None,
    ) -> "LaunchGroupManager":
        """接线进程内能力（spawner / 任务登记）；事件与投影不受影响。"""
        if spawner is not None:
            self._spawner = spawner
        if track is not None:
            self._track = track
        return self

    def get(self, group_id: str) -> LaunchGroup | None:
        return self._groups.get(group_id)

    def groups(self) -> list[LaunchGroup]:
        return list(self._groups.values())

    def apply(self, envelope) -> None:
        """组事件 → 投影（唯一写入点：``apply_event`` 与恢复重放共用）。"""
        data = envelope.data or {}
        group_id = str(data.get("group_id") or "")
        if not group_id:
            return
        if envelope.type == "launch_group.created":
            self._groups[group_id] = LaunchGroup(
                group_id=group_id,
                parent_session_id=str(envelope.session_id or data.get("parent_session_id") or ""),
                project_id=str(envelope.project_id or ""),
                max_concurrency=int(data.get("max_concurrency") or 1),
                items=[
                    LaunchGroupItem(item_id=str(i.get("item_id") or ""), query=str(i.get("query") or ""))
                    for i in data.get("items") or []
                ],
            )
            return
        group = self._groups.get(group_id)
        if group is None:
            return
        if envelope.type == "launch_group.item_dispatched":
            item = group.item(str(data.get("item_id") or ""))
            if item is not None:
                item.state = "running"
                item.child_session_id = str(data.get("child_session_id") or "")
        elif envelope.type == "launch_group.item_finished":
            item = group.item(str(data.get("item_id") or ""))
            if item is not None:
                item.state = str(data.get("state") or "failed")  # type: ignore[assignment]
                item.error = str(data.get("error") or "")
        elif envelope.type == "launch_group.finished":
            group.state = str(data.get("state") or "finished")  # type: ignore[assignment]
            group.reason = str(data.get("reason") or "")

    # ------------------------------------------------------------------ 派发

    async def create(
        self,
        *,
        group_id: str,
        parent_session_id: str,
        items: list[tuple[str, str]],
        max_concurrency: int,
        spawner: Callable[[str], Any] | None = None,
        project_id: str | None = None,
    ) -> LaunchGroup:
        """组清单先落库（durable），再启动 worker；重复 group_id 响亮拒绝。"""
        if group_id in self._groups:
            raise ValueError(f"launch group {group_id!r} already exists; refusing to overwrite it")
        await self._commit(
            "launch_group.created",
            project_id=project_id or self._project_of(parent_session_id),
            session_id=parent_session_id,
            data={
                "group_id": group_id,
                "parent_session_id": parent_session_id,
                "max_concurrency": max_concurrency,
                "items": [{"item_id": item_id, "query": query} for item_id, query in items],
            },
        )
        group = self._groups[group_id]
        group._task = asyncio.create_task(
            self._run(group, spawner or self._spawner), name=f"launch_group:{group_id}"
        )
        if self._track is not None:
            self._track(parent_session_id, group._task, f"launch_group:{group_id}")
        return group

    async def _run(self, group: LaunchGroup, spawner: Callable[[str], Any] | None) -> None:
        sem = asyncio.Semaphore(group.max_concurrency)

        async def run_one(item: LaunchGroupItem) -> None:
            try:
                async with sem:
                    # Waiting for a slot is still queued.  Mark running only
                    # once the permit is acquired so the public counters
                    # describe actual child lifetimes.
                    if group.state != "running":
                        return
                    child = await spawner(item.query)  # type: ignore[misc]
                    await self._commit(
                        "launch_group.item_dispatched",
                        project_id=group.project_id,
                        session_id=group.parent_session_id,
                        data={
                            "group_id": group.group_id,
                            "item_id": item.item_id,
                            "child_session_id": child.id,
                        },
                    )
                    await self._wait_terminal(child)
                    state = (
                        "succeeded"
                        if child.state is AgentState.SUCCEEDED
                        else "failed" if child.state is AgentState.FAILED else "cancelled"
                    )
                    await self._commit(
                        "launch_group.item_finished",
                        project_id=group.project_id,
                        session_id=group.parent_session_id,
                        data={
                            "group_id": group.group_id,
                            "item_id": item.item_id,
                            "state": state,
                            "error": "",
                        },
                    )
            except asyncio.CancelledError:
                item.state = "cancelled"
                raise
            except Exception as exc:
                logger.warning("[launch_groups] item %s failed: %s", item.item_id, exc)
                if item.state == "running":
                    await self._commit(
                        "launch_group.item_finished",
                        project_id=group.project_id,
                        session_id=group.parent_session_id,
                        data={
                            "group_id": group.group_id,
                            "item_id": item.item_id,
                            "state": "failed",
                            "error": str(exc),
                        },
                    )
                else:
                    item.error = str(exc)

        try:
            await asyncio.gather(*(run_one(item) for item in group.items))
        except asyncio.CancelledError:
            # 取消路径：尽力落一条 durable 终态；即便这条没写下去，重启恢复也会
            # 把非终态的组标 interrupted（不会重复派发）。
            await self._commit_cancelled_best_effort(group)
            raise
        if group.state == "running":
            await self._commit(
                "launch_group.finished",
                project_id=group.project_id,
                session_id=group.parent_session_id,
                data={"group_id": group.group_id, "state": "finished", "reason": ""},
            )

    @staticmethod
    async def _wait_terminal(child: AgentSession) -> AgentSession:
        if child.state in _TERMINAL:
            return child
        # AgentHost 状态变化会经 core 事件总线发布，但 spawner 在单测里可能返回
        # 普通对象——轮询是可移植的回退。这里是**生产生命周期等待**（不是测试
        # 超时）：名额一直持有到 child 终态。
        while True:
            if child.state in _TERMINAL:
                return child
            await asyncio.sleep(0.01)

    # ------------------------------------------------------------------ 取消

    async def cancel(self, group_id: str) -> LaunchGroup | None:
        """取消一个组：先落 durable 终态，再取消 worker 并结算未派发 item。"""
        group = self._groups.get(group_id)
        if group is None:
            return None
        if group.state not in _TERMINAL_GROUP_STATES:
            await self._commit(
                "launch_group.finished",
                project_id=group.project_id,
                session_id=group.parent_session_id,
                data={
                    "group_id": group.group_id,
                    "state": "cancelled",
                    "reason": "parent cancelled",
                },
            )
        if group._task is not None and not group._task.done():
            group._task.cancel()
            try:
                await group._task
            except asyncio.CancelledError:
                pass
        for item in group.items:
            if item.state in {"queued", "running"}:
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

    # ------------------------------------------------------------------ 事件写入

    def _project_of(self, session_id: str) -> str:
        if self._core is None:
            return ""
        agent = self._core.agents.get(session_id)
        return agent.project_id if agent is not None else ""

    async def _commit(self, type_: str, *, project_id: str, session_id: str, data: dict) -> None:
        from cloudra.runtime_v2.apply import apply_event

        core = self._core
        if core is None:
            # 无 core（纯并发单测）：事件照常投影，只是没有持久化载体。
            self.apply(
                type(
                    "E",
                    (),
                    {
                        "type": type_,
                        "data": data,
                        "session_id": session_id,
                        "project_id": project_id,
                    },
                )()
            )
            return
        envelope = await core.event_writer.commit(
            EventDraft(type_, stream="agent", project_id=project_id, session_id=session_id, data=data)
        )
        apply_event(core, envelope)

    async def _commit_cancelled_best_effort(self, group: LaunchGroup) -> None:
        try:
            await asyncio.shield(
                self._commit(
                    "launch_group.finished",
                    project_id=group.project_id,
                    session_id=group.parent_session_id,
                    data={"group_id": group.group_id, "state": "cancelled", "reason": ""},
                )
            )
        except Exception as exc:  # 关停竞态：交给恢复路径标 interrupted
            logger.debug("[launch_groups] cancel finalization for %s skipped: %s", group.group_id, exc)
