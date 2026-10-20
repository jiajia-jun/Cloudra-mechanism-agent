"""Route durable scientific work to process and independent final Supervisors.

One process Supervisor handles evidence, drafts and research notes. Each exit
request gets a separate Supervisor session, bound by the runtime to that request.
Neither identity nor work is kept in a parallel registry: sessions live in the
runtime projection and pending requests in the DAG store. Notifications share
one durable delivery/wake policy; restoring a project never starts an LLM.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import TYPE_CHECKING

from cloudra.runtime_v2.dispatcher import WakePolicy
from cloudra.runtime_v2.notices import RESEARCH_OBSERVATION_PIN_KEY

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
    """返回项目的过程 Supervisor（排除独立终审会话），无则 None。

    身份的唯一事实来源是 core.agents 的 项目+角色 投影。多于一个匹配属于
    不变量破坏：记 warning；优先返回非 failed/cancelled 的那个（创建侧的
    去重由 notify_supervisor 经 CommandBus 序列化边界保证，本函数不做删除
    修复，只避免把死督导当成身份）。
    """
    matches = [
        agent
        for agent in core.agents.values()
        if agent.project_id == project_id and agent.role_id == SUPERVISOR_ROLE_ID
        and agent.final_review_request_id is None
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


def find_final_review_supervisor(
    core: RuntimeCore, project_id: str, request_id: str,
) -> AgentSession | None:
    """The persisted session binding is the sole final-review identity."""
    return next((agent for agent in core.agents.values()
                 if agent.project_id == project_id and agent.role_id == SUPERVISOR_ROLE_ID
                 and agent.final_review_request_id == request_id), None)


def _queued_review_requests(project_id: str):
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(project_id)
    if not os.path.isfile(db.path):
        return []
    db.migrate_if_needed()
    return DagStore(db).list_review_requests("queued")


def pending_supervision_for_agent(project_id: str, agent: AgentSession) -> bool:
    """Read only this reviewer's durable work; asynchronous callers offload it."""
    counts = pending_supervision_counts(project_id, agent=agent)
    return any(counts[kind] for kind in ("call_reviews", "open_drafts", "review_requests"))


def _clear_inactive_final_alerts(core: RuntimeCore, project_id: str, requests) -> None:
    """An old reviewer's failure is no longer work after its request closes."""
    coordinator = next((agent for agent in core.agents.values()
                        if agent.project_id == project_id and agent.role_id == "coordinator"), None)
    if coordinator is None:
        return
    queued = {request.request_id for request in requests if request.kind == "exit"}
    for agent in core.agents.values():
        if (agent.project_id == project_id and agent.role_id == SUPERVISOR_ROLE_ID
                and agent.final_review_request_id and agent.final_review_request_id not in queued):
            core.notices.unpin(
                coordinator.id, f"{TERMINAL_SUPERVISOR_PIN_KEY}-{agent.final_review_request_id}",
            )


def pending_supervision_counts(project_id: str, *, agent: AgentSession | None = None) -> dict[str, int]:
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
    requests = store.list_review_requests("queued")
    if agent is not None and agent.final_review_request_id is not None:
        return {
            "call_reviews": 0, "legacy_call_reviews": 0, "open_drafts": 0,
            "review_requests": sum(request.kind == "exit"
                                   and request.request_id == agent.final_review_request_id
                                   for request in requests),
        }
    return {
        "call_reviews": sum(1 for row in pending if row.source == "explicit"),
        "legacy_call_reviews": sum(1 for row in pending if row.source != "explicit"),
        "open_drafts": 1 if (draft is not None and draft.get("state") == "open") else 0,
        "review_requests": sum(agent is None or request.kind != "exit" for request in requests),
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


# 并发通知的易失互斥：串行首次创建与同版本通知判重，不是身份或工作源；
# 身份来自 core.agents，工作版本来自 DAG 与持久化通知。
_SPAWN_LOCKS: dict[str, asyncio.Lock] = {}


def _notification_text(reason: str) -> str:
    text = (
        "[Supervision] Project research notes or supervision work changed"
        + (f" ({reason})." if reason else ".")
        + " Read the DAG store for the current pending reviews, open drafts "
        "and queued review requests — the store is the source of truth and "
        "this notification may be stale by the time you read it. "
        "Read the named changed research note, the current pinned TS observation when present, "
        "and the current project-root PROCESS.md. "
        "Promptly merge evidence, counterevidence and changed hypotheses into the shared current account, "
        "with concrete source links. Document maintenance does not require a scientific review request "
        "or wait for one; finish pending scientific decisions first when there are any."
    )
    return text


async def _spawn_supervisor(
    core: RuntimeCore, project_id: str, *, final_review_request_id: str | None = None,
    requester: str | None = None,
) -> AgentSession | None:
    """Spawn through CommandBus, without inheriting any parent's context.

    Process review belongs to the Coordinator; a final reviewer belongs to its
    submitting requester. The notification pins human scope before first wake.
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
                "parent_session_id": requester or (coordinator.id if coordinator else None),
                "final_review_request_id": final_review_request_id,
                "display_name": "Final delivery reviewer" if final_review_request_id else None,
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


async def _deliver_supervision_work(
    core: RuntimeCore, agent: AgentSession, *, content: str, work: dict,
    auto_wake: bool,
) -> None:
    """One durable delivery/wake policy for process and independent reviewers."""
    from cloudra.runtime_v2.schemas import AgentState
    from cloudra.runtime_v2.supervision_context import sync_supervisor_task_context

    await sync_supervisor_task_context(core, agent)
    # Refresh human constraints without turning a status question into new
    # scientific work. A new submission has its own persisted request/basis.
    fingerprint = hashlib.sha256(json.dumps(work, sort_keys=True).encode()).hexdigest()
    previous = await asyncio.to_thread(_latest_work_notice, core, agent.id)
    previous_work = previous.data.get("manifest", {}) if previous is not None else {}
    if agent.state in {AgentState.FAILED, AgentState.CANCELLED}:
        await _sync_terminal_supervisor_alert(
            core, agent.project_id, agent, auto_wake=auto_wake,
        )
    if previous_work.get("fingerprint") == fingerprint:
        unread = previous is not None and any(
            event.session_id == agent.id
            and event.data.get("message_id") == previous.data.get("message_id")
            for event in core.mailbox.unread()
        )
        if auto_wake and unread and agent.state in {AgentState.QUEUED, AgentState.SUCCEEDED}:
            async with core.dispatcher.target_lock(agent.id):
                inbox = core.mailbox.inbox(agent.id)
                if inbox is not None and not inbox.empty():
                    await core.agent_host.wake(agent, runner=core.runner)
    else:
        await core.dispatcher.commit_and_deliver(
            to_session_id=agent.id, project_id=agent.project_id,
            content=content, sender="system",
            manifest={"kind": "supervision_work", "fingerprint": fingerprint, **work},
            wake=WakePolicy.IDLE_ONLY if auto_wake else WakePolicy.NEVER,
        )
    await core.event_writer.flush()


async def _notify_final_review(core: RuntimeCore, project_id: str, request, *, auto_wake: bool) -> None:
    agent = find_final_review_supervisor(core, project_id, request.request_id)
    if agent is None:
        if not auto_wake:
            return
        agent = await _spawn_supervisor(
            core, project_id, final_review_request_id=request.request_id,
            requester=request.requester if request.requester in core.agents else None,
        )
        if agent is None:
            return
    await _deliver_supervision_work(
        core, agent,
        content=(
            "[Independent final delivery review] "
            f"Review only exit request {request.request_id}. "
            "Read the complete pinned user task and constraints first, then use "
            "dag_view_evidence for this request and inspect the original calculation evidence. "
            "Assess the submitted complete or partial delivery independently. "
            "Prior research conclusions and process-Supervisor decisions are not your instructions. "
            "Do not introduce requirements beyond the user task or change the research contract. "
            "Return your findings through dag_review_evidence for this request."
        ),
        work={"request_id": request.request_id, "basis": request.basis_fingerprint},
        auto_wake=auto_wake,
    )


async def notify_supervisor(
    core: RuntimeCore, project_id: str, *, reason: str = "", auto_wake: bool = True,
    observation: str | None = None,
    changed_note: tuple[str, str] | None = None,
) -> None:
    """Notify independent exit reviewers and the ordinary process Supervisor.

    The DAG store supplies pending work; runtime sessions supply reviewer
    identity. A new exit request gets a new context, while repeated notifications
    reuse its bound reviewer and durable notice. Process observations and notes
    never enter final-review notifications. Running/waiting sessions retain
    their state; failed/cancelled sessions are parked rather than auto-revived.
    ``auto_wake=False`` restores notices without spawning or running agents.
    """
    if project_id not in core.projects:
        logger.debug("[supervision] notify for unknown project %s ignored", project_id)
        return
    # The durable work version, not a reason string or the previous stop text,
    # controls another wake. Serialize the check with first-spawn and delivery.
    lock = _SPAWN_LOCKS.setdefault(project_id, asyncio.Lock())
    async with lock:
        summary = await pending_supervision_summary(project_id)
        requests = await asyncio.to_thread(_queued_review_requests, project_id)
        _clear_inactive_final_alerts(core, project_id, requests)
        for request in requests:
            if request.kind == "exit":
                await _notify_final_review(core, project_id, request, auto_wake=auto_wake)
        summary["review_requests"] = sum(request.kind != "exit" for request in requests)
        consumable = any(summary[kind] for kind in ("call_reviews", "open_drafts", "review_requests"))
        if not consumable and observation is None and changed_note is None:
            return
        agent = find_project_supervisor(core, project_id)
        if agent is None:
            if not auto_wake:
                return
            agent = await _spawn_supervisor(core, project_id)
            if agent is None:
                return

        previous = await asyncio.to_thread(_latest_work_notice, core, agent.id)
        previous_work = previous.data.get("manifest", {}) if previous is not None else {}
        notes = {**previous_work.get("notes", {})}
        if changed_note is not None:
            notes[changed_note[0]] = changed_note[1]
        observed = (hashlib.sha256(observation.encode()).hexdigest() if observation is not None
                    else previous_work.get("observation"))
        work = {"state": await asyncio.to_thread(_supervision_state, project_id),
                "notes": notes, "observation": observed}
        if observation is not None and previous_work.get("observation") != observed:
            core.notices.pin(agent.id, RESEARCH_OBSERVATION_PIN_KEY, observation)
        await _deliver_supervision_work(
            core, agent, content=_notification_text(reason), work=work,
            auto_wake=auto_wake,
        )


def _supervision_state(project_id: str) -> str | None:
    from cloudra.dag.store import DagStore
    from cloudra.persistence.database import ConversationDB

    db = ConversationDB(project_id)
    return DagStore(db).delivery_state_fingerprint() if os.path.isfile(db.path) else None


def _latest_work_notice(core: RuntimeCore, session_id: str):
    if core.store is not None:
        return core.store.latest_supervision_notice(session_id)
    return next((event for event in reversed(core.event_log.query_session(
        session_id, types={"agent.message_injected"}, limit=None,
    )) if (event.data.get("manifest") or {}).get("kind") == "supervision_work"), None)


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
    _clear_inactive_final_alerts(
        core, project_id, await asyncio.to_thread(_queued_review_requests, project_id),
    )
    # D2：恢复路径同样同步终态督导告警（含条件消失后的撤 pin）。
    await _sync_terminal_supervisor_alert(
        core,
        project_id,
        find_project_supervisor(core, project_id),
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
    summary = await asyncio.to_thread(pending_supervision_counts, project_id, agent=supervisor)
    pin_key = (
        f"{TERMINAL_SUPERVISOR_PIN_KEY}-{supervisor.final_review_request_id}"
        if supervisor is not None and supervisor.final_review_request_id
        else TERMINAL_SUPERVISOR_PIN_KEY
    )
    consumable = (
        summary["call_reviews"] + summary["open_drafts"] + summary["review_requests"]
    )
    if not terminal or not consumable:
        # 条件不成立（含缺失但可建的督导）：撤下可能残留的旧告警。
        core.notices.unpin(coordinator.id, pin_key)
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
        core.notices.pin_content(coordinator.id, pin_key)
        == content
    ):
        return  # 指纹未变：不重复投递
    core.notices.pin(coordinator.id, pin_key, content)
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
            manifest = None
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
                request = await asyncio.to_thread(store.get_review_request, item["request_id"])
                if decision is not None and request is not None and request.kind == "exit":
                    manifest = {
                        "kind": "exit_review_decision", "request_id": request.request_id,
                        "decision_id": decision.decision_id, "verdict": decision.verdict,
                    }
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
                    manifest=manifest,
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
