"""事件驱动 Supervisor 的运行时接入口（Task 3：持久信箱通知）。

本模块实现 ``docs/superpowers/plans/2026-09-05-event-driven-supervisor.md``
（2026-09-06 修订，§5 显式送审契约）的运行时半边：

- ``notify_supervisor``：项目唯一 Supervisor 的身份确保 + 按状态表通知；
- ``reconcile_supervision``：项目装载/恢复后的持久化待办扫描与补通知；
- ``flush_review_notifications``：结构化裁决通知的非轮询投递；
- ``find_project_supervisor`` / ``pending_supervision_summary`` /
  ``reconcile_legacy_backlog_notice``：纯投影查询与持久化待办只读扫描。

设计契约要点（计划 §1/§2/§4/§5）：

- 待办的唯一事实来源是 DAG store（pending call reviews / open drafts / queued
  review requests）；本模块只做身份确保与通知/调度，不持有旧待办快照，不引入
  第二份内存队列。
- Supervisor 是项目内唯一的普通 runtime_v2 agent（``role_id="supervisor"``），
  由 AgentRunner / TurnPipeline / InvocationService 驱动，每轮自读持久信箱裁决，
  空信箱则 stop。身份由 core.agents 的项目+角色投影确定。
- 生产端（研究工具完成）只登记证据/事实后返回；显式送审（dag_bind_evidence）
  → 持久化 → notify_supervisor。两条路径都不等待督导 LLM 或裁决完成。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import AgentSession

logger = logging.getLogger(__name__)

SUPERVISOR_ROLE_ID = "supervisor"

# §5 历史 legacy_auto 待办的一次性 Coordinator 提示的 pin key（notices pin
# 事件溯源且同内容去重：重复调用/重启不会重复轰炸，见 NoticeManager.pin）。
LEGACY_BACKLOG_PIN_KEY = "supervisor-legacy-backlog"


def find_project_supervisor(
    core: RuntimeCore, project_id: str
) -> AgentSession | None:
    """返回项目内唯一的 Supervisor AgentSession（纯投影查询），无则 None。

    身份的唯一事实来源是 core.agents 的 项目+角色 投影。多于一个匹配属于
    不变量破坏：记 warning 并返回第一个（创建侧的去重由 notify_supervisor
    经 CommandBus 序列化边界保证，本函数不做修复）。
    """
    matches = [
        agent
        for agent in core.agents.values()
        if agent.project_id == project_id and agent.role_id == SUPERVISOR_ROLE_ID
    ]
    if len(matches) > 1:
        logger.warning(
            "[supervision] project %s has %d supervisor agents; identity "
            "invariant violated, using %s",
            project_id,
            len(matches),
            matches[0].id,
        )
    return matches[0] if matches else None


async def pending_supervision_summary(project_id: str) -> dict[str, int]:
    """读取项目的持久化督导待办计数（只读，绝不建库）。

    信箱三类来源：pending call reviews、open 机理草稿、queued review
    requests。§5 起 call reviews 按来源拆分：``call_reviews`` 只数可消费的
    显式送审行（source="explicit"）；``legacy_call_reviews`` 数历史自动行
    （legacy_auto/auto，保留审计但不自动消费）。会话库不存在（项目从未进入
    dag 模式）时返回全零。供 reconcile_supervision 与诊断面共用；同步
    SQLite 读经 ``asyncio.to_thread`` 卸载。
    """
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    def _read() -> dict[str, int]:
        db = ConversationDB(project_id)
        if not os.path.isfile(db.path):
            return {
                "call_reviews": 0,
                "legacy_call_reviews": 0,
                "open_drafts": 0,
                "review_requests": 0,
            }
        db.migrate_if_needed()
        store = DagStore(db)
        draft = store.latest_draft()
        pending = store.list_call_reviews("pending")
        return {
            "call_reviews": sum(1 for row in pending if row.source == "explicit"),
            "legacy_call_reviews": sum(1 for row in pending if row.source != "explicit"),
            "open_drafts": 1 if (draft is not None and draft.get("state") == "open") else 0,
            "review_requests": len(store.list_review_requests("queued")),
        }

    return await asyncio.to_thread(_read)


async def reconcile_legacy_backlog_notice(core: RuntimeCore, project_id: str) -> int:
    """§5 历史自动待办的一次性提示：恢复路径调用。

    有 legacy_auto/auto 的 pending review 时，把一条"升级前有 N 条自动入箱
    的历史复核待办被保留为审计、不会自动消费；请筛选后经 dag_bind_evidence
    （带 claim）显式重提仍相关者"的提示 pin 进项目 Coordinator 的上下文；
    没有则撤下该 pin。notices pin 事件溯源且同内容去重——重复调用与重启
    重放都不产生新事件，因此可以安全地在每次项目装载/恢复时调用而不轰炸。
    返回 legacy pending 数。
    """
    summary = await pending_supervision_summary(project_id)
    legacy = summary["legacy_call_reviews"]
    coordinator = next(
        (
            agent
            for agent in core.agents.values()
            if agent.project_id == project_id and agent.role_id == "coordinator"
        ),
        None,
    )
    if coordinator is None:
        return legacy
    if legacy:
        core.notices.pin(
            coordinator.id,
            LEGACY_BACKLOG_PIN_KEY,
            (
                f"[Supervision] {legacy} pre-upgrade automatic review(s) are kept "
                "in the inbox as audit records only — they are NOT consumed as "
                "supervision work. Triage them yourself: re-submit anything still "
                "relevant explicitly via dag_bind_evidence with a claim; the rest "
                "can be left as history."
            ),
        )
    else:
        core.notices.unpin(coordinator.id, LEGACY_BACKLOG_PIN_KEY)
    return legacy


# 并发首次通知的易失互斥（计划 §2）：只防同进程竞态，不是身份源——身份
# 唯一事实来源始终是 core.agents 的 项目+角色 投影（find_project_supervisor）。
_SPAWN_LOCKS: dict[str, asyncio.Lock] = {}


def _notification_text(reason: str) -> str:
    text = (
        "[Supervision] Your persistent supervision mailbox changed"
        + (f" ({reason})." if reason else ".")
        + " Read the DAG store for the current pending reviews, open drafts "
        "and queued review requests — the store is the source of truth and "
        "this notification may be stale by the time you read it."
    )
    return text


async def _spawn_supervisor(core: RuntimeCore, project_id: str) -> AgentSession | None:
    """经 CommandBus 正常 spawn 项目唯一 Supervisor（parent=Coordinator）。

    parent 必须指向 Coordinator（反馈走普通子 agent 完成回传），不是提交
    证据的研究子 agent；没有 Coordinator 时 parent 留空。spawn 不带 query
    （queued），随后由 notify 的同一状态表 deliver + wake 开跑。
    """
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.schemas import Command

    coordinator = next(
        (
            agent
            for agent in core.agents.values()
            if agent.project_id == project_id and agent.role_id == "coordinator"
        ),
        None,
    )
    result = await CommandBus(core).execute(
        Command(
            type="agent.spawn",
            target={"project_id": project_id},
            payload={
                "role_id": SUPERVISOR_ROLE_ID,
                "parent_session_id": coordinator.id if coordinator else None,
                # 督导的 dag_* 裁决工具是 guided-only（dag_review_evidence 在
                # dag_record 被拒）；桥接面的 orchestration_mode 取自 agent
                # settings，spawn 时显式钉 guided。
                "settings": {"orchestration_mode": "dag_guided"},
            },
            actor="system",
        )
    )
    if not result.accepted or not hasattr(result.data, "state"):
        logger.warning(
            "[supervision] supervisor spawn rejected for project %s: %s",
            project_id,
            result.data,
        )
        return None
    return result.data


async def notify_supervisor(
    core: RuntimeCore, project_id: str, *, reason: str = ""
) -> None:
    """确保项目唯一 Supervisor agent 身份并按状态表通知；不等待裁决。

    调用方必须先完成待办持久化（显式送审 review / open 草稿 / 结构化督导
    请求），本函数只负责身份与调度，不携带待办快照——Supervisor 苏醒后自读
    持久信箱取得最新状态。模式门禁在调用方（只有 dag_guided 的生产路径会
    走到这里）；本函数自身不读模式，以便恢复/诊断路径直接复用。

    状态表（计划 §2，系统新增待办时的行为）：

    - 尚未创建：创建项目唯一 Supervisor，经正常调度启动；并发首次通知只
      产生一个 agent（身份以 core.agents 投影为准；``_SPAWN_LOCKS`` 只是
      防同进程竞态的易失互斥，不是第二身份源）。
    - queued / running：注入信箱变更消息；不 restart、不重置上下文、不再
      创建 runner（queued 是 spawn 后尚未开跑的瞬态，deliver + wake 开
      新 run 属正常首跑，不是 restart）。
    - waiting：审批/输入等待不被普通通知绕过，消息保留投递到信箱。
    - succeeded（正常休眠）：正常 wake 开新 run，重读持久化信箱。
    - failed：保留待办与失败状态；不由每条系统通知反复 reopen，显式恢复
      后继续。
    - cancelled（用户取消）：仅保留待办，不自动复活；明确恢复后重新扫描
      信箱（走 reconcile_supervision）。

    通知通道是 ``mailbox.deliver`` + 条件 ``agent_host.wake`` 的组合：
    刻意不走 ``agent.message`` 命令——它的 decide 路径对 failed/cancelled
    终态 agent 自动 reopen（plan_wake），会违反状态表。``reason`` 只用于
    通知消息的可诊断标注，不构成路由或去重依据。
    """
    if project_id not in core.projects:
        logger.debug("[supervision] notify for unknown project %s ignored", project_id)
        return
    agent = find_project_supervisor(core, project_id)
    if agent is None:
        lock = _SPAWN_LOCKS.setdefault(project_id, asyncio.Lock())
        async with lock:
            agent = find_project_supervisor(core, project_id)
            if agent is None:
                agent = await _spawn_supervisor(core, project_id)
        if agent is None:
            return  # spawn 被拒：待办已持久化，reconcile 会补（已记 warning）

    from cloudra.runtime_v2.schemas import AgentState

    state = agent.state
    if state in {AgentState.FAILED, AgentState.CANCELLED}:
        # 待办留在持久化信箱；显式恢复（reconcile/用户重启）后再扫描。
        logger.debug(
            "[supervision] supervisor %s is %s; backlog stays persisted, no auto-revive",
            agent.id,
            state.value,
        )
        return
    core.mailbox.deliver(
        to_session_id=agent.id,
        project_id=project_id,
        content=_notification_text(reason),
        sender="system",
    )
    if state in {AgentState.QUEUED, AgentState.SUCCEEDED}:
        core.agent_host.wake(agent, runner=core.runner)
    # RUNNING：下一轮 drain 收件箱；WAITING_*：消息保留，不绕过等待语义。
    await core.event_writer.flush()


async def reconcile_supervision(core: RuntimeCore, project_id: str) -> None:
    """项目装载/显式恢复后扫描持久化待办，非空则按状态表补通知。

    覆盖"证据入库成功、通知前崩溃"的窗口（计划 §4）：以
    ``pending_supervision_summary`` 的三类持久化待办为准，非空时按
    notify_supervisor 的同一状态表补一次通知；空信箱为 no-op。
    先补投递已裁决但未送达的通知（flush_review_notifications），
    再调 ``reconcile_legacy_backlog_notice``（一次性 Coordinator 提示，
    pin 幂等），最后按显式计数决定是否补通知。

    恢复纪律：running/waiting 中的 agent 已由 runtime 恢复路径落 failed
    （见 runtime_v2/persistence.py），本函数不得把 failed/用户取消视作正常
    休眠而绕过恢复策略；只安排通知，绝不在 apply_event / 事件重放路径里
    执行任何 LLM 副作用。历史 legacy_auto 来源的 pending 不自动消费
    （计划 §5）：可消费待办只算 ``pending_supervision_summary`` 的
    ``call_reviews``（source="explicit"）等三类显式来源。
    """
    await flush_review_notifications(core, project_id)
    await reconcile_legacy_backlog_notice(core, project_id)
    summary = await pending_supervision_summary(project_id)
    consumable = (
        summary["call_reviews"] + summary["open_drafts"] + summary["review_requests"]
    )
    if not consumable:
        return
    await notify_supervisor(
        core, project_id, reason="persisted backlog found on project load"
    )


async def flush_review_notifications(core: RuntimeCore, project_id: str) -> int:
    """投递项目的 pending 裁决通知（非轮询）。

    触发点：Supervisor 的 dag_review_evidence 落库裁决后（dag_stage 的
    after_tool 钩子）与 reconcile_supervision（恢复补投）。通知行是
    durable 的：pin + mailbox.deliver + 条件 wake 的事件先经
    event_writer 落盘/发布，再把通知行标记 sent——投递与标记之间崩溃
    会在下次 flush 重投（pin 按 key 去重，mailbox 重投是一条冗余消息，
    接受）。recipient 已 cancelled 不复活（用户取消的运行不被迟到裁决
    唤醒），通知行照样闭环标记 sent；recipient 不是活 agent（如 replan
    的 "user"）只落标记。返回处理的通知条数。
    """
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB
    from cloudra.runtime_v2.schemas import AgentState

    def _store() -> DagStore | None:
        db = ConversationDB(project_id)
        if not os.path.isfile(db.path):
            return None
        # 旧库（早于 dag_review_* 表族）必须先补 schema，否则每 flush 抛
        # "no such table"；建库/升级统一走 ensure_schema（幂等）。
        db.ensure_schema()
        return DagStore(db)

    store = await asyncio.to_thread(_store)
    if store is None:
        return 0
    pending = await asyncio.to_thread(store.pending_review_notifications)
    handled = 0
    for item in pending:
        decision_id = item["decision_id"]
        try:
            decision = await asyncio.to_thread(store.get_review_decision, decision_id)
            content = (
                f"[Supervisor review decision] decision_id={decision_id} "
                f"request_id={item['request_id']} "
                f"verdict={decision.verdict if decision is not None else 'unknown'} "
                f"reason={decision.reason if decision is not None else ''} "
                f"next_action={decision.next_action or 'none' if decision is not None else 'none'}"
            )
            recipient = item["recipient_session_id"]
            agent = core.agents.get(recipient) if recipient else None
            if recipient and (agent is None or agent.state is not AgentState.CANCELLED):
                core.notices.pin(recipient, key=f"review-{decision_id}", content=content)
                # Mailbox 投递是 durable 唤醒握手；若裁决撞上对方正要进入
                # WAITING_APPROVAL，AgentRunner 的 transition 后 inbox 复查
                # 会确定性地观察到这条消息（不靠 timing sleep）。
                core.mailbox.deliver(
                    to_session_id=recipient,
                    project_id=project_id,
                    content=content,
                    sender="supervisor",
                )
                if agent is not None:
                    core.agent_host.wake(agent, runner=core.runner)
                # 本路径在 CommandBus 之外，自己持有 publish+persist 边界：
                # 事件落盘/发布先于标记 sent，否则崩溃会丢唤醒。
                await core.event_writer.flush()
            await asyncio.to_thread(store.mark_review_notification_sent, decision_id)
            handled += 1
        except Exception:
            logger.exception(
                "[supervision] review notification %s delivery failed for project %s",
                decision_id,
                project_id,
            )
    return handled
