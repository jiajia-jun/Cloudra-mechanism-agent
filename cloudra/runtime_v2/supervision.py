"""事件驱动 Supervisor 的运行时接入口（Task 3：持久信箱通知）。

本模块实现 ``docs/superpowers/plans/2026-09-05-event-driven-supervisor.md``
（2026-09-06 修订，§5 显式送审契约）的运行时半边：

- ``notify_supervisor``：项目唯一 Supervisor 的身份确保 + 按状态表通知；
- ``reconcile_supervision``：项目装载/恢复后的持久化待办扫描与补通知；
- ``flush_review_notifications``：三类裁决通知（review_decision /
  call_verdict / draft_verdict，共用同一张 durable 通知表）的非轮询投递；
- ``_sync_terminal_supervisor_alert``：D2 督导终态（failed/cancelled）+
  可消费待办时给 Coordinator 的一次性告警（pin 内容即指纹去重）；
- ``find_project_supervisor`` / ``pending_supervision_summary`` /
  ``reconcile_legacy_backlog_notice``：纯投影查询与持久化待办只读扫描。

设计契约要点（计划 §1/§2/§4/§5）：

- 科学待办的唯一事实来源是 DAG store（pending call reviews / open drafts / queued
  review requests）；本模块只做身份确保与通知/调度，不持有旧待办快照，不引入
  第二份内存队列。
- PROCESS.md 的文档维护以当前文件为准，复用通知，不创建科学审查待办。
- Supervisor 是项目内唯一的普通 runtime_v2 agent（``role_id="supervisor"``），
  由 AgentRunner / TurnPipeline / InvocationService 驱动，每轮自读持久信箱裁决，
  空信箱则 stop。身份由 core.agents 的项目+角色投影确定。
- 生产端（研究工具完成）只登记证据/事实后返回；显式送审经真实
  dag_bind_evidence 工具入口持久化后，由 DAG policy 完成钩子按新建
  review 回执调 notify_supervisor（送审方法本身不通知）。两条路径都不
  等待督导 LLM 或裁决完成。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING

from cloudra.runtime_v2.dispatcher import WakePolicy

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import AgentSession

logger = logging.getLogger(__name__)

SUPERVISOR_ROLE_ID = "supervisor"

# §5 历史 legacy_auto 待办的一次性 Coordinator 提示的 pin key（notices pin
# 事件溯源且同内容去重：重复调用/重启不会重复轰炸，见 NoticeManager.pin）。
LEGACY_BACKLOG_PIN_KEY = "supervisor-legacy-backlog"

# D2 督导终态告警的 pin key：内容即指纹（督导状态 + 待办摘要），pin 由事件
# 投影恢复——跨重启同指纹不重复投递，条件消失撤 pin 后复发可再投。
TERMINAL_SUPERVISOR_PIN_KEY = "supervisor-terminal-backlog"


def find_project_supervisor(
    core: RuntimeCore, project_id: str
) -> AgentSession | None:
    """返回项目内唯一的 Supervisor AgentSession（纯投影查询），无则 None。

    身份的唯一事实来源是 core.agents 的 项目+角色 投影。多于一个匹配属于
    不变量破坏：记 warning；优先返回非 failed/cancelled 的那个（创建侧的
    去重由 notify_supervisor 经 CommandBus 序列化边界保证，本函数不做删除
    修复，只避免把死督导当成身份）。
    """
    matches = [
        agent
        for agent in core.agents.values()
        if agent.project_id == project_id and agent.role_id == SUPERVISOR_ROLE_ID
    ]
    if not matches:
        return None
    chosen = matches[0]
    if len(matches) > 1:
        from cloudra.runtime_v2.schemas import AgentState

        terminal = {AgentState.FAILED, AgentState.CANCELLED}
        live = [agent for agent in matches if agent.state not in terminal]
        chosen = (live or matches)[0]
        logger.warning(
            "[supervision] project %s has %d supervisor agents; identity "
            "invariant violated, using %s",
            project_id,
            len(matches),
            chosen.id,
        )
    return chosen


def pending_supervision_counts(project_id: str) -> dict[str, int]:
    """读取项目的持久化督导待办计数（只读，绝不建库）。

    信箱三类来源：pending call reviews、open 机理草稿、queued review
    requests。§5 起 call reviews 按来源拆分：``call_reviews`` 只数可消费的
    显式送审行（source="explicit"）；``legacy_call_reviews`` 数历史自动行
    （legacy_auto/auto，保留审计但不自动消费）。会话库不存在（项目从未进入
    dag 模式）时返回全零。异步调用者须经 ``asyncio.to_thread`` 卸载。
    """
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

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


async def pending_supervision_summary(project_id: str) -> dict[str, int]:
    """Read durable scientific supervision counts without blocking the event loop."""
    return await asyncio.to_thread(pending_supervision_counts, project_id)


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
        "[Supervision] Project research notes or supervision work changed"
        + (f" ({reason})." if reason else ".")
        + " Read the DAG store for the current pending reviews, open drafts "
        "and queued review requests — the store is the source of truth and "
        "this notification may be stale by the time you read it. "
        "When PROCESS.md exists, organize useful hypothesis updates there after scientific review. "
        "Read the current file; notebook maintenance is not a scientific review request."
    )
    return text


async def _spawn_supervisor(core: RuntimeCore, project_id: str) -> AgentSession | None:
    """经 CommandBus 正常 spawn 项目唯一 Supervisor（parent=Coordinator）。

    parent 必须指向 Coordinator，而不是提交证据的研究子 agent；科学反馈
    走持久裁决通知，不发送普通子任务完成回报。没有 Coordinator 时 parent 留空。spawn 不带 query
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
    core: RuntimeCore, project_id: str, *, reason: str = "", auto_wake: bool = True
) -> None:
    """确保项目唯一 Supervisor agent 身份并按状态表通知；不等待裁决。

    调用方先完成科学待办持久化或 PROCESS.md 写入，本函数只负责身份与调度，
    不携带待办快照——Supervisor 苏醒后读取科学信箱和当前文档。
    模式门禁在调用方（只有 dag_guided 的生产路径会
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
    - failed / cancelled（用户取消）：不自动复活，但通知照常投递信箱驻留
      （park-don't-wake，与子 agent 完成回传 / hub mention 同一纪律）——
      用户显式复活（agent.message / agent.restart）后首轮 drain 即可读到，
      持久化待办也不会丢。

    通知通道是 ``dispatcher.commit_and_deliver``（``WakePolicy`` 按状态表选
    park / wake）：刻意不走 ``agent.message`` 命令——它的 decide 路径对
    failed/cancelled 终态 agent 自动 reopen（plan_wake），会违反状态表。
    ``reason`` 只用于通知消息的可诊断标注，不构成路由或去重依据。

    ``auto_wake=False``（API 装载 / 进程重启）：只把通知驻留信箱，不 spawn
    新督导、不 wake 任何已有 agent。待办仍在 DAG store，显式 resume /
    在线 notify 才开 LLM。
    """
    if project_id not in core.projects:
        logger.debug("[supervision] notify for unknown project %s ignored", project_id)
        return
    agent = find_project_supervisor(core, project_id)
    if agent is None:
        if not auto_wake:
            logger.info(
                "[supervision] project %s has backlog but no supervisor; "
                "load path will not spawn",
                project_id,
            )
            return
        lock = _SPAWN_LOCKS.setdefault(project_id, asyncio.Lock())
        async with lock:
            agent = find_project_supervisor(core, project_id)
            if agent is None:
                agent = await _spawn_supervisor(core, project_id)
        if agent is None:
            return  # spawn 被拒：待办已持久化，reconcile 会补（已记 warning）

    from cloudra.runtime_v2.schemas import AgentState

    state = agent.state
    # 统一不复活纪律（park-don't-wake）：所有状态都投递（通知是 durable 的
    # agent.message_injected + 内存队列）；failed/cancelled 只驻留不唤醒——
    # 用户显式复活后首轮 drain 即可读到。
    # 督导通知的唤醒纪律：只有 QUEUED/SUCCEEDED 才唤醒（不打断运行态与
    # 等待态）；auto_wake=False（装载）时任何状态都只驻留。
    await core.dispatcher.commit_and_deliver(
        to_session_id=agent.id,
        project_id=project_id,
        content=_notification_text(reason),
        sender="system",
        wake=WakePolicy.IDLE_ONLY if auto_wake else WakePolicy.NEVER,
    )
    if state in {AgentState.FAILED, AgentState.CANCELLED}:
        logger.debug(
            "[supervision] supervisor %s is %s; notification parked, no auto-revive",
            agent.id,
            state.value,
        )
        # D2：终态督导 + 可消费待办不再是隐形 wedge——给 Coordinator 发
        # 一次性告警（指纹去重），点名不自动复活与真实恢复入口。
        await _sync_terminal_supervisor_alert(
            core, project_id, agent, auto_wake=auto_wake
        )
    # RUNNING：下一轮 drain 收件箱；WAITING_*：消息保留，不绕过等待语义。
    # auto_wake=False：任何状态都只驻留，由显式 resume 开跑。
    await core.event_writer.flush()


async def reconcile_supervision(
    core: RuntimeCore, project_id: str, *, auto_wake: bool = True
) -> None:
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

    ``auto_wake=False`` 给 API 装载：补投递/pin 但不 spawn、不 wake，避免
    重启把休眠督导/协调者重新打进 LLM（issue #35）。在线切回 dag_guided
    仍用默认 ``auto_wake=True``。
    """
    await flush_review_notifications(core, project_id, auto_wake=auto_wake)
    await reconcile_legacy_backlog_notice(core, project_id)
    summary = await pending_supervision_summary(project_id)
    # D2：恢复路径同样同步终态督导告警（含条件消失后的撤 pin）。
    await _sync_terminal_supervisor_alert(
        core,
        project_id,
        find_project_supervisor(core, project_id),
        summary,
        auto_wake=auto_wake,
    )
    consumable = (
        summary["call_reviews"] + summary["open_drafts"] + summary["review_requests"]
    )
    if not consumable:
        return
    await notify_supervisor(
        core,
        project_id,
        reason="persisted backlog found on project load",
        auto_wake=auto_wake,
    )


_CALL_VERDICT_NEXT_ACTION = {
    "agree": "stage bound; continue with the remaining stages",
    "disagree": (
        "re-bind the stage with corrected evidence, or close it explicitly "
        "(skip/not_applicable with a reason) — rejected is still an open gap; "
        "before re-binding, record a one-line attribution of the disagreement in "
        "your next claim: numerical / initial-guess / model (solvent, protonation, "
        "H-bond network, conformer) / mechanism"
    ),
    "skip": "stage closed as skipped; no further evidence owed",
    "not_applicable": "stage closed as not applicable; no further evidence owed",
    "needs_evidence": (
        "supply the missing evidence named in reason and re-submit "
        "via dag_bind_evidence with a claim"
    ),
    "ignore": "no action required; the call was ruled not delivery evidence",
    "target_deleted": (
        "the target this evidence was submitted for was deleted from the "
        "delivery graph; re-submit against a live target if still relevant"
    ),
}


def _call_verdict_text(review_id: str, payload: dict) -> str:
    verdict = str(payload.get("verdict") or "unknown")
    target = str(payload.get("target_id") or "")
    target_type = str(payload.get("target_type") or "")
    stage = str(payload.get("stage_kind") or "")
    reason = str(payload.get("reason") or "")
    next_action = _CALL_VERDICT_NEXT_ACTION.get(
        verdict, "see the pinned DAG projection for the current stage state"
    )
    labeled_target = f"{target_type}:{target}" if target_type else target
    return (
        f"[Supervisor call verdict] review_id={review_id} verdict={verdict} "
        f"stage={stage} target={labeled_target} reason={reason} next={next_action}"
    )


def _draft_verdict_text(draft_id: str, payload: dict) -> str:
    verdict = str(payload.get("verdict") or "unknown")
    reason = str(payload.get("reason") or "")
    next_action = (
        "revise the mechanism per the reason and re-propose via dag_propose_mechanism"
        if verdict == "rejected"
        else "mechanism accepted; the substantive compute gate is open"
    )
    return (
        f"[Supervisor draft verdict] draft_id={draft_id} verdict={verdict} "
        f"reason={reason} next={next_action}"
    )


def _resolve_recipient_session(
    core: RuntimeCore, project_id: str, recipient: str
) -> str:
    """通知收件人解析：活 session id 直取；legacy a-N 词表（草稿 actor_id）
    经 D13 唯一映射解析到项目内活 session；都不可解返回原值（投递驻留、
    不唤醒——与 replan 的 "user" 收件人同一处置）。"""
    if not recipient:
        return ""
    if recipient in core.agents:
        return recipient
    from cloudra.base.role_identity import legacy_agent_id_for_role

    for agent in core.agents.values():
        if agent.project_id != project_id:
            continue
        if legacy_agent_id_for_role(agent.role_id) == recipient:
            return agent.id
    return recipient


async def _sync_terminal_supervisor_alert(
    core: RuntimeCore,
    project_id: str,
    supervisor: AgentSession | None,
    summary: dict[str, int] | None = None,
    *,
    auto_wake: bool = True,
) -> None:
    """D2：failed/cancelled 督导 + 可消费待办 → Coordinator 的一次性告警。

    不自动复活是既定纪律（恢复 = 显式 agent.message / agent.restart），
    本告警只解决"项目被死督导无声 wedge"的不可见性：pin + mailbox 一次性
    投递，内容即指纹（督导终态 + 待办计数摘要）——指纹不变不重复投递
    （pin 由事件投影恢复，跨重启去重成立）；条件消失（督导非终态或待办
    清空）撤 pin，同指纹复发可再投。告警本身不复活督导；Coordinator 在
    queued/succeeded 时另 wake（waiting 不绕过，驻留下轮可见）。
    """
    from cloudra.runtime_v2.schemas import AgentState

    coordinator = next(
        (
            agent
            for agent in core.agents.values()
            if agent.project_id == project_id and agent.role_id == "coordinator"
        ),
        None,
    )
    if coordinator is None:
        return
    terminal = supervisor is not None and supervisor.state in {
        AgentState.FAILED,
        AgentState.CANCELLED,
    }
    if summary is None:
        summary = await pending_supervision_summary(project_id)
    consumable = (
        summary["call_reviews"] + summary["open_drafts"] + summary["review_requests"]
    )
    if not terminal or not consumable:
        # 条件不成立（含缺失但可建的督导）：撤下可能残留的旧告警。
        core.notices.unpin(coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY)
        return
    content = (
        f"[Supervision] ALERT: the Supervisor agent ({supervisor.id}) is in "
        f"terminal state {supervisor.state.value} and will not auto-revive. "
        f"{consumable} supervision item(s) are pending "
        f"(call_reviews={summary['call_reviews']}, "
        f"open_drafts={summary['open_drafts']}, "
        f"review_requests={summary['review_requests']}). "
        "Recovery: send the Supervisor an explicit message or restart it "
        "(agent.message / agent.restart reopen a terminal agent); it drains "
        "its parked mailbox on the first turn of the new run."
    )
    if (
        core.notices.pin_content(coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY)
        == content
    ):
        return  # 指纹未变：不重复投递
    core.notices.pin(coordinator.id, TERMINAL_SUPERVISOR_PIN_KEY, content)
    await core.dispatcher.commit_and_deliver(
        to_session_id=coordinator.id,
        project_id=project_id,
        content=content,
        sender="system",
        wake=WakePolicy.IDLE_ONLY if auto_wake else WakePolicy.NEVER,
    )


async def flush_review_notifications(
    core: RuntimeCore, project_id: str, *, auto_wake: bool = True
) -> int:
    """投递项目的 pending 裁决通知（非轮询；三类裁决共用同一通道）。

    通知行三类（kind）：review_decision（结构化请求裁决，渲染材料查
    dag_review_decisions）、call_verdict（per-CallReview 裁决）与
    draft_verdict（机理草稿裁决）（后两类渲染材料在通知行 payload，
    裁决与通知行同事务落表）。触发点：Supervisor 的裁决工具
    （dag_review_evidence / dag_review_call / dag_accept_mechanism）落库
    后（dag_stage 的 after_tool 钩子）与 reconcile_supervision（恢复补投）。
    通知行是 durable 的：pin + ``dispatcher.commit_and_deliver`` 的事件先经
    event_writer 落盘/发布，再把通知行标记 sent——投递与标记之间崩溃
    会在下次 flush 重投（pin 按 key 去重，mailbox 重投是一条冗余消息，
    接受）。failed/cancelled 收件人不唤醒（用户取消/失败的运行不被迟到
    裁决复活），WAITING_INPUT 与工具审批（WAITING_APPROVAL reason=approval）
    同样只驻留；wait_review 挂起就是在等这份 flush，必须 wake。裁决照常
    pin + 投递驻留信箱，通知行照样闭环标记 sent；recipient 不是活
    agent（如 replan 的 "user"）只落投递不唤醒。返回处理的通知条数。
    """
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

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
        subject_id = item["decision_id"]
        kind = item.get("kind") or "review_decision"
        try:
            if kind == 'review_superseded':
                payload = json.loads(item.get('payload') or '{}')
                content = (f"[Review superseded] request_id={subject_id} "
                           f"reason={payload['reason']} next_action={payload['next_action']}")
                pin_key = f'review-superseded-{subject_id}'
            elif kind == "call_verdict":
                content = _call_verdict_text(
                    subject_id, json.loads(item.get("payload") or "{}")
                )
                pin_key = f"call-verdict-{subject_id}"
            elif kind == "draft_verdict":
                content = _draft_verdict_text(
                    subject_id, json.loads(item.get("payload") or "{}")
                )
                pin_key = f"draft-verdict-{subject_id}"
            else:
                decision = await asyncio.to_thread(
                    store.get_review_decision, subject_id
                )
                content = (
                    f"[Supervisor review decision] decision_id={subject_id} "
                    f"request_id={item['request_id']} "
                    f"verdict={decision.verdict if decision is not None else 'unknown'} "
                    f"reason={decision.reason if decision is not None else ''} "
                    f"next_action={decision.next_action or 'none' if decision is not None else 'none'}"
                )
                pin_key = f"review-{subject_id}"
            recipient = _resolve_recipient_session(
                core, project_id, item["recipient_session_id"]
            )
            if recipient:
                core.notices.pin(recipient, key=pin_key, content=content)
                # Mailbox 投递是 durable 唤醒握手；若裁决撞上对方正要进入
                # WAITING_APPROVAL，AgentRunner 的 transition 后 inbox 复查
                # 会确定性地观察到这条消息（不靠 timing sleep）。
                # park-don't-wake：终态 / WAITING_INPUT / 工具审批只驻留。
                # wait_review 的 WAITING_APPROVAL 必须 wake（人已经 break）。
                # auto_wake=False（装载）：任何状态都只驻留。
                # 投递的 persist+发布边界在 dispatcher 内（落盘成功才入队、
                # 才唤醒），因此这里无需再自己 flush。
                await core.dispatcher.commit_and_deliver(
                    to_session_id=recipient,
                    project_id=project_id,
                    content=content,
                    sender="supervisor",
                    wake=WakePolicy.PARK_WAITING if auto_wake else WakePolicy.NEVER,
                )
                await asyncio.to_thread(store.mark_review_notification_sent, subject_id)
                handled += 1
        except Exception:
            logger.exception(
                "[supervision] review notification %s delivery failed for project %s",
                subject_id,
                project_id,
            )
    return handled
