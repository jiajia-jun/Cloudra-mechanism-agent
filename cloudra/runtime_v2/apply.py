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
- agent.spawned / agent.settings_changed / agent.state_changed
- run.started（顺带作废该 agent 的 pending_compactions 投影——新 run 的
  内存 history 与旧压缩请求无关）/ run.finished / agent.cancelled
- compaction.requested（``pending_compactions`` 投影的唯一写入点）

纯通知/投影类事件（明确 no-op，与 projects/agents/roles 状态无关）：
- 意图与审计标记：agent.spawn_requested / agent.spawn_rejected /
  agent.cancel_requested / agent.restart_requested / agent.restarted /
  agent.context_reset / command.rejected /
  agent.message_emitted / agent.warning / loop.detected / project.synced
- 消息与对话：agent.message_injected / agent.thinking（inbox 内容不重建：
  run 只活在内存，恢复后由新发消息驱动）
- 运行过程流：llm.* / tool.* / run.retry / dag.gate_blocked /
  hub.posted / compaction.started / compaction.finished
- 自有恢复通道的投影（不经本函数）：approval.* / interaction.*
  （pending 投影直接查事件日志；孤儿由 restore 落 approval.expired /
  interaction.expired 显式闭合）、reminder.*（reminders 投影 + rearm）、
  context.pin_set / context.pin_cleared / context.injected
  （``notices.restore_from``）、context.run_summarized /
  context.handover_updated（context tree）、email.received

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
    for session_id in [sid for sid, a in core.agents.items() if a.project_id == project_id]:
        core.agents.pop(session_id, None)
        core.mailbox.drop_inbox(session_id)


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


def _apply_run_started(core: RuntimeCore, envelope: EventEnvelope) -> None:
    agent = core.require_agent(envelope.session_id or "")
    protocol = envelope.data.get("invocation_protocol") or InvocationProtocol.TRADITIONAL
    agent.current_run = CurrentRun(
        run_id=envelope.run_id or "",
        started_at=envelope.created_at,
        invocation_protocol=InvocationProtocol(protocol),
    )
    agent.updated_at = envelope.created_at
    # A new run rebuilds its in-memory history from scratch, so a manual
    # compaction requested against the previous run's history is meaningless:
    # the projection entry expires here (resume has no run.started; the runner
    # shell discards the entry itself there — see agent_runner._run).
    core.pending_compactions.pop(agent.id, None)


def _apply_run_cleared(core: RuntimeCore, envelope: EventEnvelope) -> None:
    agent = core.require_agent(envelope.session_id or "")
    agent.current_run = None
    agent.updated_at = envelope.created_at


def _apply_compaction_requested(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """手动压缩请求投影：pending_compactions 的唯一写入点（runner 只读/消费）。"""
    session_id = envelope.session_id
    if not session_id:
        return
    core.pending_compactions[session_id] = int(envelope.data.get("keep_recent") or 20)


_APPLIERS: dict[str, Callable[[RuntimeCore, EventEnvelope], None]] = {
    "project.created": _apply_project_created,
    "project.updated": _apply_project_updated,
    "project.settings_changed": _apply_project_settings_changed,
    "project.deleted": _apply_project_deleted,
    "role.updated": _apply_role_updated,
    "agent.spawned": _apply_agent_spawned,
    "agent.settings_changed": _apply_agent_settings_changed,
    "agent.state_changed": _apply_agent_state_changed,
    "run.started": _apply_run_started,
    "run.finished": _apply_run_cleared,
    "agent.cancelled": _apply_run_cleared,
    "compaction.requested": _apply_compaction_requested,
}


def apply_event(core: RuntimeCore, envelope: EventEnvelope) -> None:
    """Apply one event's state projection; unknown/notification types no-op."""
    applier = _APPLIERS.get(envelope.type)
    if applier is not None:
        applier(core, envelope)
