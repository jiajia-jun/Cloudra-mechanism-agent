"""Launch groups: event-sourced swarm batches (评审 5.2 后半).

一个 launch group 拥有若干 item 与并发上限：首轮准入名额在 child 的首个
run 结束时释放，执行名额约束每个 run（包括后台计算通知后的恢复）。等待计算的
child 继续占有 item，供最终交付对账，但不堵住后续 item 派发。
父取消级联到 worker 与已派发后代。

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
_GROUP_STATES = {"running"} | _TERMINAL_GROUP_STATES
_ITEM_STATES = {"queued", "running", "succeeded", "failed", "cancelled"}


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
        self._child_final_cache: dict[str, tuple[object, bool]] = {}
        self._run_semaphores: dict[str, asyncio.Semaphore] = {}
        self._child_groups: dict[str, str] = {}

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

    def prune_projects(self, project_ids: set[str], session_ids: set[str]) -> None:
        """Release group manifests and local workers for deleted projects."""
        for group_id, group in list(self._groups.items()):
            if group.project_id in project_ids:
                continue
            self._groups.pop(group_id)
            self._run_semaphores.pop(group_id, None)
            if group._task is not None and not group._task.done():
                group._task.cancel()
        for child_id, group_id in list(self._child_groups.items()):
            if child_id not in session_ids or group_id not in self._groups:
                self._child_groups.pop(child_id)
        for child_id in self._child_final_cache.keys() - session_ids:
            self._child_final_cache.pop(child_id)

    def snapshot(self) -> list[dict[str, Any]]:
        """组清单的快照载荷（纯数据）。

        快照水位一旦越过 ``launch_group.*`` 事件，增量重放就看不到它们——
        与 session_contexts / pending_compactions 同理，投影必须随快照落地，
        否则下一次恢复会凭空丢组。
        """
        return [
            {
                "group_id": group.group_id,
                "parent_session_id": group.parent_session_id,
                "project_id": group.project_id,
                "max_concurrency": group.max_concurrency,
                "state": group.state,
                "reason": group.reason,
                "items": [
                    {
                        "item_id": item.item_id,
                        "query": item.query,
                        "state": item.state,
                        "child_session_id": item.child_session_id,
                        "error": item.error,
                    }
                    for item in group.items
                ],
            }
            for group in self._groups.values()
        ]

    def restore(self, entries: list[dict[str, Any]] | None) -> None:
        """从快照载荷重建投影；快照点之后的 ``launch_group.*`` 事件由重放补上。

        载荷形状错误（未知状态、缺 group_id）直接抛错——快照是我们自己写的，
        坏了就是 bug，不静默降级。
        """
        for data in entries or []:
            group_id = str(data.get("group_id") or "")
            if not group_id:
                raise ValueError("launch group snapshot entry without group_id")
            state = str(data.get("state") or "")
            if state not in _GROUP_STATES:
                raise ValueError(f"unknown launch group state in snapshot: {state!r}")
            items: list[LaunchGroupItem] = []
            for raw in data.get("items") or []:
                item_state = str(raw.get("state") or "")
                if item_state not in _ITEM_STATES:
                    raise ValueError(f"unknown launch group item state in snapshot: {item_state!r}")
                items.append(
                    LaunchGroupItem(
                        item_id=str(raw.get("item_id") or ""),
                        query=str(raw.get("query") or ""),
                        state=item_state,  # type: ignore[arg-type]
                        child_session_id=str(raw.get("child_session_id") or ""),
                        error=str(raw.get("error") or ""),
                    )
                )
            self._groups[group_id] = LaunchGroup(
                group_id=group_id,
                parent_session_id=str(data.get("parent_session_id") or ""),
                project_id=str(data.get("project_id") or ""),
                max_concurrency=int(data.get("max_concurrency") or 1),
                state=state,  # type: ignore[arg-type]
                reason=str(data.get("reason") or ""),
                items=items,
            )
            self._run_semaphores[group_id] = asyncio.Semaphore(self._groups[group_id].max_concurrency)
            for item in items:
                if item.child_session_id:
                    self._child_groups[item.child_session_id] = group_id

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
            self._run_semaphores[group_id] = asyncio.Semaphore(self._groups[group_id].max_concurrency)
            return
        group = self._groups.get(group_id)
        if group is None:
            return
        if envelope.type == "launch_group.item_dispatched":
            item = group.item(str(data.get("item_id") or ""))
            if item is not None:
                item.state = "running"
                item.child_session_id = str(data.get("child_session_id") or "")
                if item.child_session_id:
                    self._child_groups[item.child_session_id] = group_id
        elif envelope.type == "launch_group.item_finished":
            item = group.item(str(data.get("item_id") or ""))
            if item is not None and item.state not in {"succeeded", "failed", "cancelled"}:
                item.state = str(data.get("state") or "failed")  # type: ignore[assignment]
                item.error = str(data.get("error") or "")
                child_id = str(data.get("child_session_id") or "")
                if child_id and not item.child_session_id:
                    item.child_session_id = child_id
                    self._child_groups[child_id] = group_id
        elif envelope.type == "launch_group.finished":
            new_state = str(data.get("state") or "finished")
            new_reason = str(data.get("reason") or "")
            # 幂等：已终态时保留首条非空 reason（cancel 写 "parent cancelled" 后
            # worker CancelledError 的 best-effort 再写 reason="" 不得抹掉）。
            if group.state in _TERMINAL_GROUP_STATES:
                if new_reason and not group.reason:
                    group.reason = new_reason
                return
            group.state = new_state  # type: ignore[assignment]
            group.reason = new_reason

    def run_semaphore(self, session_id: str) -> asyncio.Semaphore | None:
        """Per-group run capacity for an unfinished child, including resumed runs."""
        group_id = self._child_groups.get(session_id)
        if group_id is None:
            return None
        agent = self._core.agents.get(session_id) if self._core is not None else None
        if agent is None or self._child_is_final(agent):
            return None
        return self._run_semaphores.get(group_id)

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
        admission = asyncio.Semaphore(group.max_concurrency)

        async def run_one(item: LaunchGroupItem) -> None:
            child = None
            try:
                async with admission:
                    # Bound the number of first runs admitted at once. A
                    # parked run releases this permit so later work can start.
                    if group.state != "running":
                        return
                    child = await spawner(item.query)  # type: ignore[misc]
                    from cloudra.runtime_v2.event_writer import EventPersistenceError

                    for attempt in range(2):
                        try:
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
                            break
                        except EventPersistenceError:
                            # Spawn has already committed. Retry its ownership
                            # record with the same child, never spawn again.
                            if attempt:
                                raise
                    runner = getattr(self._core, "runner", None)
                    if runner is not None and isinstance(child, AgentSession):
                        # The capped swarm deferred its initial ScheduleAgent
                        # effect. Membership is now durable, so every run can
                        # acquire the group's execution permit.
                        first_task = runner.task_for(child.id)
                        if child.state is AgentState.QUEUED:
                            first_task = runner.schedule(child.id)
                        if first_task is not None:
                            await asyncio.wait({first_task})
                    else:
                        # Pure concurrency tests and cores without a runner
                        # have no run task to observe.
                        await self._wait_terminal(child)
                await self._wait_terminal(child)
                # cancel() 可能已把 item 收口为 cancelled——勿再写成功终态。
                if item.state != "running":
                    return
                final_state = child.state
                if self._core is not None and getattr(child, "parent_session_id", None):
                    from cloudra.runtime_v2.subagent_bridge import child_final_event

                    terminal = await asyncio.to_thread(child_final_event, self._core, child)
                    if terminal is not None:
                        final_state = AgentState(terminal.data["to"])
                state = (
                    "succeeded"
                    if final_state is AgentState.SUCCEEDED
                    else "failed" if final_state is AgentState.FAILED else "cancelled"
                )
                await self._commit_item_finished(
                    group, item, state=state, error=""
                )
            except asyncio.CancelledError:
                # item 终态由 cancel() 落 durable item_finished；这里不摸投影。
                raise
            except Exception as exc:
                logger.warning("[launch_groups] item %s failed: %s", item.item_id, exc)
                if item.state in {"queued", "running"}:
                    child_id = str(getattr(child, "id", "") or "")
                    error = str(exc)
                    if child_id and item.state == "queued" and self._core is not None:
                        # Spawn is already durable, but the deferred child has
                        # no group membership yet. Cancel it durably before the
                        # worker exits; it must never run as a queued orphan.
                        from cloudra.runtime_v2.commands import CommandBus
                        from cloudra.runtime_v2.schemas import Command

                        try:
                            await CommandBus(self._core).execute(Command(
                                type="agent.cancel", target={"session_id": child_id},
                                payload={}, actor="system",
                            ))
                        except Exception as cancel_exc:
                            # An unavailable store cannot certify cancellation.
                            # Preserve the child id in the item failure event
                            # so a later operator can identify the queued child.
                            logger.warning(
                                "[launch_groups] child %s cancellation failed: %s",
                                child_id, cancel_exc,
                            )
                            error += f"; child cancellation failed: {cancel_exc}"
                    await self._commit_item_finished(
                        group, item, state="failed", error=error,
                        child_session_id=child_id,
                    )

        try:
            await asyncio.gather(*(run_one(item) for item in group.items))
        except asyncio.CancelledError:
            # 取消路径：若 cancel() 已落组终态则 no-op；否则尽力写 cancelled。
            # 即便这条没写下去，重启恢复也会把非终态组标 interrupted。
            await self._commit_cancelled_best_effort(group)
            raise
        if group.state == "running":
            await self._commit(
                "launch_group.finished",
                project_id=group.project_id,
                session_id=group.parent_session_id,
                data={"group_id": group.group_id, "state": "finished", "reason": ""},
            )
        await self._notify_quiescence(group.project_id)

    async def _notify_quiescence(self, project_id: str) -> None:
        runner = getattr(self._core, "runner", None)
        hook = getattr(runner, "maybe_wake_parked_delivery", None)
        if hook is not None:
            await hook(project_id)

    async def _wait_terminal(self, child: AgentSession) -> AgentSession:
        if await asyncio.to_thread(self._child_is_final, child):
            return child
        # AgentHost 状态变化会经 core 事件总线发布，但 spawner 在单测里可能返回
        # 普通对象——轮询是可移植的回退。后台等待不会完成 item，
        # 但 run permit 已在首轮结束时释放。
        while True:
            if await asyncio.to_thread(self._child_is_final, child):
                return child
            await asyncio.sleep(0.1)

    def _child_is_final(self, child: AgentSession) -> bool:
        if self._core is None or not getattr(child, "parent_session_id", None):
            return child.state in _TERMINAL
        from cloudra.runtime_v2.subagent_bridge import child_final_event

        # The waiter polls at 100 ms. Scan the event log only when the child's
        # projected state changes; a parked run otherwise generates no work.
        signature = (child.state, child.updated_at)
        cached = self._child_final_cache.get(child.id)
        if cached is not None and cached[0] == signature:
            return cached[1]
        final = child_final_event(self._core, child) is not None
        self._child_final_cache[child.id] = (signature, final)
        return final

    # ------------------------------------------------------------------ 取消

    async def cancel(self, group_id: str, *, cancel_children: bool = True) -> LaunchGroup | None:
        """Cancel a group; service shutdown may preserve children for later wakeup."""
        group = self._groups.get(group_id)
        if group is None:
            return None
        child_ids = [
            item.child_session_id for item in group.items
            if item.state == "running" and item.child_session_id
        ]
        for item in group.items:
            if item.state in {"queued", "running"}:
                await self._commit_item_finished(
                    group, item, state="cancelled", error=""
                )
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
        if cancel_children and self._core is not None:
            from cloudra.runtime_v2.commands import CommandBus
            from cloudra.runtime_v2.schemas import Command, CommandRejected

            bus = CommandBus(self._core)
            for child_id in child_ids:
                try:
                    await bus.execute(Command(
                        type="agent.cancel", target={"session_id": child_id},
                        payload={}, actor="system",
                    ))
                except CommandRejected:
                    # A child may have genuinely finished or already been
                    # cancelled while the group was settling its items.
                    continue
        if group._task is not None and not group._task.done():
            group._task.cancel()
            try:
                await group._task
            except asyncio.CancelledError:
                pass
        await self._notify_quiescence(group.project_id)
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
        """Shutdown: stop group workers but preserve child sessions and QM jobs."""
        for group_id in list(self._groups):
            await self.cancel(group_id, cancel_children=False)

    # ------------------------------------------------------------------ 事件写入

    def _project_of(self, session_id: str) -> str:
        if self._core is None:
            return ""
        agent = self._core.agents.get(session_id)
        return agent.project_id if agent is not None else ""

    async def _commit_item_finished(
        self,
        group: LaunchGroup,
        item: LaunchGroupItem,
        *,
        state: str,
        error: str,
        child_session_id: str = "",
    ) -> None:
        """item 终态唯一写口（persist-then-apply）；已终态则 no-op。"""
        if item.state in {"succeeded", "failed", "cancelled"}:
            return
        await self._commit(
            "launch_group.item_finished",
            project_id=group.project_id,
            session_id=group.parent_session_id,
            data={
                "group_id": group.group_id,
                "item_id": item.item_id,
                "state": state,
                "error": error,
                "child_session_id": child_session_id,
            },
        )

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
        if group.state in _TERMINAL_GROUP_STATES:
            return
        try:
            await asyncio.shield(
                self._commit(
                    "launch_group.finished",
                    project_id=group.project_id,
                    session_id=group.parent_session_id,
                    data={
                        "group_id": group.group_id,
                        "state": "cancelled",
                        "reason": "worker cancelled",
                    },
                )
            )
        except Exception as exc:  # 关停竞态：交给恢复路径标 interrupted
            logger.debug("[launch_groups] cancel finalization for %s skipped: %s", group.group_id, exc)
