"""Agent 间消息的唯一提交入口（评审 5.2）。

`Mailbox.deliver()` 曾是「append 内存事件 → 立即入队」，持久化留给调用方事后
`flush()`：多数正常路径确实会 flush，但 append 与 flush 之间仍有崩溃窗口，且
与 CommandBus 的 persist-before-apply 不变量不一致（「有的先落库、有的最终再
flush」两套语义）。

`MessageDispatcher.commit_and_deliver()` 把这条路径收成一个原语，四步固定顺序：

1. 组装 ``agent.message_injected`` 草稿（载荷形状仍由 ``Mailbox`` 唯一提供）；
2. 经 ``EventWriter.commit()`` **持久化并发布**——失败抛 ``EventPersistenceError``，
   此时**不入队、不唤醒**，并丢掉未持久化的尾巴；
3. 落库成功后才 enqueue；
4. 最后按 ``WakePolicy`` 决定是否唤醒（唤醒本身走 ``plan_wake``，RUNNING 为 no-op）。

唤醒纪律显式化为 ``WakePolicy``（唯一解析点），而不是散在各调用点：

- ``PARK_TERMINAL``：终态只驻留，其余照常唤醒（hub mention / 子 agent 回传）；
- ``PARK_WAITING``：终态、``WAITING_INPUT``、工具审批只驻留；``wait_review``
  的 ``WAITING_APPROVAL`` 要唤醒（督导裁决通知）；
- ``IDLE_ONLY``：只有 ``QUEUED``/``SUCCEEDED`` 才唤醒（督导通知：不打断运行态
  与等待态）；
- ``NEVER``：只投递（调用方自己正在跑，或恢复路径 ``auto_wake=False``）。

inbox 仍是**刻意易失**的内存队列：这里保证的是「消息先 durable 再可见」，
不承诺重启重建队列（恢复后由显式 resume / 新消息驱动，见 mailbox 模块说明）。
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING, Any

from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.mailbox import Mailbox
from cloudra.runtime_v2.schemas import AgentSession, AgentState, EventEnvelope, new_id

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore

_TERMINAL_STATES = {AgentState.FAILED, AgentState.CANCELLED}


class WakePolicy(str, Enum):
    """投递后的唤醒纪律（新增取值必须同时说明哪些状态不被唤醒）。"""

    PARK_TERMINAL = "park_terminal"
    PARK_WAITING = "park_waiting"
    IDLE_ONLY = "idle_only"
    NEVER = "never"


def latest_state_reason(core, session_id: str) -> str:
    """会话最近一次状态迁移的 reason（空串＝没有记录）。"""
    events = core.event_log.query_session(session_id, types={"agent.state_changed"})
    if not events:
        return ""
    return str(events[-1].data.get("reason") or "")


def should_wake(core, agent: AgentSession, policy: WakePolicy) -> bool:
    """唤醒判定（纯读；``wake`` 对 RUNNING 是 no-op，这里只表达纪律）。"""
    if policy is WakePolicy.NEVER:
        return False
    state = agent.state
    if state in _TERMINAL_STATES:
        return False
    if policy is WakePolicy.PARK_TERMINAL:
        return True
    if policy is WakePolicy.IDLE_ONLY:
        return state in {AgentState.QUEUED, AgentState.SUCCEEDED}
    # PARK_WAITING：复用 WAITING_APPROVAL，用挂起 reason 分流。
    if state is AgentState.WAITING_INPUT:
        return False
    if state is AgentState.WAITING_APPROVAL:
        return latest_state_reason(core, agent.id) == "wait_review"
    return True


class MessageDispatcher:
    """进程内消息提交 + 投递的唯一入口（见模块 docstring）。"""

    def __init__(self, core: "RuntimeCore") -> None:
        self._core = core
        self._target_locks: dict[str, asyncio.Lock] = {}

    @property
    def core(self) -> "RuntimeCore":
        return self._core

    def target_lock(self, session_id: str) -> asyncio.Lock:
        """Serialize delivery with the target runner's final inbox check."""
        lock = self._target_locks.get(session_id)
        if lock is None:
            lock = self._target_locks[session_id] = asyncio.Lock()
        return lock

    async def commit_and_deliver(
        self,
        *,
        to_session_id: str,
        project_id: str,
        content: str,
        sender: str,
        run_id: str | None = None,
        images: list[str] | None = None,
        image_artifact_ids: list[str | None] | None = None,
        post_id: str | None = None,
        manifest: dict[str, Any] | None = None,
        language: str | None = None,
        wake: WakePolicy = WakePolicy.PARK_TERMINAL,
    ) -> EventEnvelope:
        """持久化一条 ``agent.message_injected``，成功后才入队并按策略唤醒。"""
        core = self._core
        message_id = new_id("msg")
        draft = EventDraft(
            "agent.message_injected",
            stream="project",
            project_id=project_id,
            session_id=to_session_id,
            run_id=run_id,
            data=Mailbox.message_data(
                message_id=message_id,
                sender=sender,
                content=content,
                images=images,
                image_artifact_ids=image_artifact_ids,
                post_id=post_id,
                manifest=manifest,
                language=language,
            ),
        )
        # 2) 先 durable（失败即抛，不入队不唤醒）——这是本入口存在的理由。
        envelope = await core.event_writer.commit(draft)
        # Publication can call subscribers that send to this session. Lock only
        # the inbox/state boundary to avoid a reentrant commit deadlock.
        async with self.target_lock(to_session_id):
            # 3) 落库成功才入队。
            core.mailbox.enqueue(
                to_session_id,
                Mailbox.message_payload(
                    message_id=message_id,
                    sender=sender,
                    content=content,
                    images=images,
                    post_id=post_id,
                ),
            )
            # 4) 再按状态决定唤醒。
            target = core.agents.get(to_session_id)
            if target is not None and await asyncio.to_thread(should_wake, core, target, WakePolicy(wake)):
                await core.agent_host.wake(target, runner=core.runner)
            return envelope
