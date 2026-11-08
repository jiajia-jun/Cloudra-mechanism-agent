"""唯一状态应用器：内存状态 = 事件日志的投影（FP 内核化 3a）。

``apply_event`` 是从事件推导内存状态（projects/agents/roles）的唯一函数：
运行期写路径（CommandBus handlers / AgentHost）与恢复路径
（``persistence.restore_core`` 的快照后增量重放）都走这里，结构上消灭
双 applier 漂移。

约定：
- **无守卫**：重放必须无条件接受历史事件；非法迁移的拦截是 decide 侧
  职责（命令在 ``commands.py`` 的纯 decide、状态机在 ``agent_host`` 的
  ``plan_*`` 规划器，共用同一张 ``_TRANSITIONS`` 守卫表）。
- 拍序：守卫校验（decide/plan）→ ``event_log.append`` → ``apply_event``。
  状态永远只是已落日志事件的投影（命令路径的四拍见 commands.py
  docstring：append/publish/persist → apply → effects）。
- 时间戳口径统一取 ``envelope.created_at``（``updated_at``、
  ``current_run.started_at``），而不是应用时刻的 ``utc_now()``——否则
  活 core 与重放 core 会差出墙钟漂移（等价性门禁
  ``tests/test_runtime_v2_replay_equivalence.py`` 守的就是这条）。

状态承载事件（本模块处理）：
- project.created / project.updated / project.settings_changed /
  project.deleted（硬删除 tombstone：项目与其 agent 从投影移除）
- role.updated
- agent.spawned / agent.settings_changed / agent.state_changed /
  agent.context_reset（显式 restart 的上下文重置：清空该 session 的
  上下文投影；自动唤醒重开 run 不再重置上下文）
- run.started / run.finished / agent.cancelled
- compaction.requested（``pending_compactions`` 投影的唯一写入点；
  跨 run 存活，由 runner 在下个轮次边界应用到会话上下文）
- agent.message_emitted（同一条正文事件驱动可见消息与会话上下文）
- context.prefix_installed / context.appended / context.compacted
  （``session_contexts`` 会话级 LLM 上下文投影，Task 4）

纯通知/投影类事件（明确 no-op，与 projects/agents/roles 状态无关）：
- 意图与审计标记：agent.spawn_requested / agent.spawn_rejected /
  agent.cancel_requested / agent.restart_requested / agent.restarted /
  command.rejected /
  agent.warning / loop.detected / project.synced
- 消息与对话：agent.message_injected / agent.thinking（本函数对二者不投影任何
  projects/agents/roles 状态；输入消息进入会话上下文走 context.appended，inbox
  队列则由恢复路径 ``persistence._rebuild_inboxes_from_events`` 从
  agent.message_injected 重建——不是"易失即弃"）
- 运行过程流：llm.* / tool.* / run.retry / dag.gate_blocked /
  hub.posted / compaction.started / compaction.finished
- 自有恢复通道的投影（不经本函数）：approval.* / interaction.*
  （pending 投影直接查事件日志；孤儿由 restore 落 approval.expired /
  interaction.expired 显式闭合）、reminder.*（reminders 投影 + rearm）、
  context.pin_set / context.pin_cleared / context.injected
  （``notices.restore_from`` 重放重建 pin 状态和变更日志，消费游标随
  context.appended 正文原子落地）、email.received；
  context.run_summarized / context.handover_updated 已随 per-run 自动
  摘要管线删除（Task 4），只剩历史日志里的旧事件（transcript 只读渲染）。

不在事件模型内的状态：``runtime_defaults``（只由 API/嵌入方直接赋值，
无事件承载）、api_key（write-only 秘密，永不进事件/快照）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from cloudra.runtime_v2.schemas import (
    AgentSession,
    AgentState,
    CurrentRun,
    EventEnvelope,
    InvocationProtocol,
    Project,
    ProjectSettings,
    RuntimeSettingsPatch,
    SessionContext,
)

if TYPE_CHECKING:
    from cloudra.runtime_v2.core import RuntimeCore


def _strip_computed_fields(value: Any) -> Any:
    """Remove computed-only keys (currently api_key_set) before persistence."""
    if isinstance(value, dict):
        return {k: _strip_computed_fields(v) for k, v in value.items() if k != "api_key_set"}
    if isinstance(value, list):
        return [_strip_computed_fields(item) for item in value]
    return value


def _strip_removed_agent_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Drop agent fields removed after older snapshots/events were written.

    AgentSession validates with extra="forbid", so a pre-removal snapshot
    carrying ``state_since`` or ``current_run.current_tool`` would fail to
    restore; both fields had no readers, so dropping them is lossless.
    """
    data = {k: v for k, v in data.items() if k != "state_since"}
    run = data.get("current_run")
    if isinstance(run, dict):
        data["current_run"] = {k: v for k, v in run.items() if k != "current_tool"}
    return data


def _apply_project_created(core: RuntimeCore, envelope: EventEnvelope) -> None:
    project = Project.model_validate(_strip_computed_fields(envelope.data))
    core.projects[project.id] = project


def _apply_project_updated(core: RuntimeCore, envelope: EventEnvelope) -> None:
    project = core.require_project(envelope.project_id)
    project = project.model_copy(update=envelope.data.get("changes", {}))
    project.updated_at = envelope.created_at
    core.projects[project.id] = project


def _apply_project_settings_changed(core: RuntimeCore, envelope: EventEnvelope) -> None:
    project = core.require_project(envelope.project_id)
    settings = ProjectSettings.model_validate(envelope.data["changes"])
    project = project.model_copy(update={"settings": settings})
    project.updated_at = envelope.created_at
    core.projects[project.id] = project


def _apply_project_deleted(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """硬删除 tombstone：项目与其全部 agent 从内存投影移除。

    幂等（重放安全）：全部 pop-with-default。事件日志（权威）不动——重放
    后 core 同样不含该项目；inbox 是刻意易失的内存队列，随 agent 一并丢弃。
    """
    project_id = envelope.project_id
    core.projects.pop(project_id, None)
    core.deleted_project_ids.add(project_id)
    for session_id in [sid for sid, a in core.agents.items() if a.project_id == project_id]:
        core.agents.pop(session_id, None)
    core.prune_orphaned_state()


def _apply_launch_group(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """launch_group.* → 组清单投影（唯一写入点；恢复重放据此重建）。"""
    core.launch_groups.apply(envelope)


def _apply_role_updated(core: RuntimeCore, envelope: EventEnvelope) -> None:
    core.roles.update(envelope.data["role_id"], envelope.data["changes"])


def _apply_agent_spawned(core: RuntimeCore, envelope: EventEnvelope) -> None:
    # 事件 payload 是 model_dump 直出：computed field（api_key_set）在
    # extra="forbid" 下必须剥掉，否则重放直接 ValidationError。
    agent = AgentSession.model_validate(
        _strip_removed_agent_fields(_strip_computed_fields(envelope.data))
    )
    core.agents[agent.id] = agent
    core.mailbox.ensure_inbox(agent.id)


def _apply_agent_settings_changed(core: RuntimeCore, envelope: EventEnvelope) -> None:
    agent = core.require_agent(envelope.session_id or "")
    # api_key 永不进事件；changes 里的 api_key_set 只是审计布尔，过滤后再校验。
    changes = {k: v for k, v in envelope.data.get("changes", {}).items() if k != "api_key_set"}
    agent.settings = agent.settings.apply(RuntimeSettingsPatch.model_validate(changes))
    agent.settings_revision = int(envelope.data.get("settings_revision", agent.settings_revision))
    agent.updated_at = envelope.created_at


def _apply_agent_state_changed(core: RuntimeCore, envelope: EventEnvelope) -> None:
    agent = core.require_agent(envelope.session_id or "")
    agent.state = AgentState(envelope.data["to"])
    agent.updated_at = envelope.created_at


def _apply_agent_task_updated(core: RuntimeCore, envelope: EventEnvelope) -> None:
    agent = core.agents.get(envelope.session_id or "")
    if agent is not None:
        agent.current_task = envelope.data.get("current_task")
        agent.updated_at = envelope.created_at


def _apply_run_started(core: RuntimeCore, envelope: EventEnvelope) -> None:
    agent = core.require_agent(envelope.session_id or "")
    protocol = envelope.data.get("invocation_protocol") or InvocationProtocol.TRADITIONAL
    agent.current_run = CurrentRun(
        run_id=envelope.run_id or "",
        started_at=envelope.created_at,
        invocation_protocol=InvocationProtocol(protocol),
    )
    agent.updated_at = envelope.created_at
    # 上下文是 session 级投影（Task 4），跨 run 连续：pending 压缩请求
    # 不再随 run.started 作废，由 runner 在下个轮次边界应用到会话上下文。


def _apply_run_cleared(core: RuntimeCore, envelope: EventEnvelope) -> None:
    agent = core.require_agent(envelope.session_id or "")
    agent.current_run = None
    agent.updated_at = envelope.created_at


def _apply_compaction_requested(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """手动压缩请求投影：pending_compactions 的唯一写入点（runner 只读/消费）。

    压缩范围是整个会话投影（没有 keep_recent 参数）：请求只表达"下个轮次
    边界压缩这个 session"，因此投影是 session id 集合。
    """
    session_id = envelope.session_id
    if not session_id:
        return
    core.pending_compactions.add(session_id)


def _context_of(core: RuntimeCore, session_id: str) -> SessionContext:
    ctx = core.session_contexts.get(session_id)
    if ctx is None:
        ctx = SessionContext()
        core.session_contexts[session_id] = ctx
    return ctx


def _apply_context_prefix_installed(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """上下文初始安装：静态前缀消息位于已有内容（如 compact 残留）之前。"""
    if not envelope.session_id:
        return
    ctx = _context_of(core, envelope.session_id)
    data = envelope.data or {}
    installed = [dict(message) for message in data.get("messages") or []]
    ctx.messages = [*installed, *ctx.messages]
    ctx.prefix_meta = dict(data.get("meta") or {})


def _apply_assistant_message(core: RuntimeCore, envelope: EventEnvelope) -> None:
    data = envelope.data or {}
    # Events that only announced output have no context payload: their context
    # was recorded in context.appended. New text commits use this event alone.
    if not envelope.session_id or "context" not in data:
        return
    _context_of(core, envelope.session_id).messages.append({
        "role": "assistant", "content": data["content"], **data["context"],
    })


def _apply_context_appended(core: RuntimeCore, envelope: EventEnvelope) -> None:
    if not envelope.session_id:
        return
    ctx = _context_of(core, envelope.session_id)
    data = envelope.data or {}
    if data.get('prefix_meta') is not None:
        ctx.prefix_meta = {**(ctx.prefix_meta or {}), **data['prefix_meta']}
    ctx.messages.extend(dict(message) for message in data.get("messages") or [])
    _track_tool_document_versions(ctx, data.get('messages') or [])
    if data.get("notices_through") is not None:
        core.notices.apply_consumed(envelope.session_id, int(data["notices_through"]))


def _apply_context_compacted(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """compact 候选原子安装：整条会话上下文一次替换；事件携带的新头部
    （重新装配的前缀）元数据一并更新 prefix_meta。"""
    if not envelope.session_id:
        return
    ctx = _context_of(core, envelope.session_id)
    data = envelope.data or {}
    ctx.messages = [dict(message) for message in data.get("messages") or []]
    ctx.prefix_meta = dict(data["prefix_meta"]) if data.get("prefix_meta") else None


def _apply_context_reset(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """显式 restart 的上下文重置：会话上下文投影随之清空（新边界）。"""
    if envelope.session_id:
        core.session_contexts.pop(envelope.session_id, None)


def _apply_tool_document_selection(core: RuntimeCore, envelope: EventEnvelope) -> None:
    from cloudra.runtime_v2.tool_selection import ToolSelectionRecord
    if not envelope.session_id:
        return
    data = envelope.data or {}
    record = ToolSelectionRecord.model_validate(data['record'])
    ctx = _context_of(core, envelope.session_id)
    ctx.prefix_meta = {**(ctx.prefix_meta or {}), 'tool_selection':record.model_dump(mode='json')}
    ctx.messages.extend(dict(message) for message in data.get('messages', []))
    _track_tool_document_versions(ctx, data.get('messages') or [])


def _track_tool_document_versions(ctx: SessionContext, messages: list[dict]) -> None:
    """Track only host-tagged contracts in durable context messages."""
    versions = dict((ctx.prefix_meta or {}).get('tool_document_revisions') or {})
    changed = False
    for message in messages:
        if message.get('role') not in ('system', 'tool'):
            continue
        if 'tool_document_revisions' in message:
            versions = dict(message['tool_document_revisions'])
            changed = True
        for doc in message.get('tool_documents') or []:
            versions[doc['name']] = doc['revision']
            changed = True
    if changed:
        ctx.prefix_meta = {**(ctx.prefix_meta or {}), 'tool_document_revisions': versions}


_APPLIERS: dict[str, Callable[[RuntimeCore, EventEnvelope], None]] = {
    "project.created": _apply_project_created,
    "project.updated": _apply_project_updated,
    "project.settings_changed": _apply_project_settings_changed,
    "project.deleted": _apply_project_deleted,
    "role.updated": _apply_role_updated,
    "launch_group.created": _apply_launch_group,
    "launch_group.item_dispatched": _apply_launch_group,
    "launch_group.item_finished": _apply_launch_group,
    "launch_group.finished": _apply_launch_group,
    "agent.spawned": _apply_agent_spawned,
    "agent.settings_changed": _apply_agent_settings_changed,
    "agent.state_changed": _apply_agent_state_changed,
    "agent.task_updated": _apply_agent_task_updated,
    "run.started": _apply_run_started,
    "run.finished": _apply_run_cleared,
    "agent.cancelled": _apply_run_cleared,
    "agent.context_reset": _apply_context_reset,
    "compaction.requested": _apply_compaction_requested,
    "context.prefix_installed": _apply_context_prefix_installed,
    "context.appended": _apply_context_appended,
    "agent.message_emitted": _apply_assistant_message,
    "context.compacted": _apply_context_compacted,
    'tool_documents.selection_started': _apply_tool_document_selection,
    'tool_documents.selection_finished': _apply_tool_document_selection,
}


def apply_event(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """Apply one event's state projection; unknown/notification types no-op."""
    applier = _APPLIERS.get(envelope.type)
    if applier is not None:
        applier(core, envelope)
    core.apply_runtime_projection(envelope)
