"""Command bus: decide（纯）→ 落日志/发布/持久化 → apply_event → effects。

固定四拍（FP 内核化 3b）：

1. **decide**：``DECIDERS[type](core, command) -> Decision``，纯函数——全部
   守卫校验在这里（非法抛 ``CommandRejected``，拒绝前要留审计轨迹的草稿
   挂在异常的 ``events`` 上），零 IO、零 mutate、零 await 副作用。
2. **逐事件 persist-then-apply**：每条草稿 ``append`` → ``flush``（store
   存在时落库再发布）→ ``apply_event``。中途 ``EventPersistenceError`` 丢弃
   未落库尾巴再抛出，避免下次 flush 把从未 apply 的事件写进磁盘。包装路径
   已 apply 再扫尾 flush，失败不丢尾巴、留给下次重试。
3. **effects**：shell 统一执行副作用（EnsureDir 走 to_thread；runner
   schedule/cancel；mailbox enqueue；api_key 内存覆盖补挂）。

已是事件投影的 broker 不强行进 decide：``approval.decide`` /
``interaction.respond`` / ``context.inject`` / ``agent.compact`` 保持薄包装
（WRAPPERS）直接调 broker/manager——它们的"状态"本就事件可推导，且
future 解析是刻意的 shell 行为（等待者必须在本进程内被唤醒，无法从事件
重放）。包装路径的事件由 bus 在执行后统一扫尾发布/持久化；状态投影在
wrapper 内紧跟 append 过 ``apply_event``（如 agent.compact 的
pending_compactions 投影）。

快照是缓存不是权威：权威是事件表，纯重放（``events_after({})`` 全量）
必须与"快照+尾巴"逐字段等价（tests/test_runtime_v2_replay_equivalence.py
守这条）。execute 因此不再每命令整库快照，改为节流后台落（每
``_SNAPSHOT_EVENT_INTERVAL`` 条事件或 ``_SNAPSHOT_TIME_INTERVAL_S`` 秒，
取先到，在命令边界检查）；进程关闭路径（api_v2 lifespan finally /
benchmark backend finally）显式调 ``flush_snapshot()`` 补一次。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from cloudra.persistence.paths import conversation_db_path, conversation_dir, data_dir, project_workspace_dir
from cloudra.runtime_v2.agent_host import _CONTEXT_RESET_NOTE, plan_cancel, plan_restart, plan_wake
from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import (
    CancelLaunchGroups,
    CancelRunner,
    Decision,
    DeleteProjectData,
    DeliverMessage,
    Effect,
    EnsureDir,
    EventDraft,
    PatchApiKey,
    ReconcileSupervision,
    ResultRef,
    ScheduleAgent,
)
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.mailbox import Mailbox
from cloudra.runtime_v2.schemas import (
    AgentSession,
    AgentState,
    Command,
    CommandRejected,
    CommandResult,
    EventEnvelope,
    OrchestrationMode,
    Project,
    ProjectSettings,
    RuntimeSettingsPatch,
    new_id,
)

logger = logging.getLogger(__name__)

Decider = Callable[[RuntimeCore, Command], Decision]
Wrapper = Callable[[RuntimeCore, Command], Awaitable[CommandResult]]

# 快照节流参数（见模块 docstring"快照是缓存不是权威"）。
_SNAPSHOT_EVENT_INTERVAL = 200
_SNAPSHOT_TIME_INTERVAL_S = 60.0


def _project_id(core: RuntimeCore, command: Command) -> str:
    return command.target.get("project_id") or "runtime"


def _normalize_workspace(raw: Any) -> str:
    """Pure workspace validation/normalization; creation is an EnsureDir effect.

    A relative path would silently resolve against the server process cwd
    downstream (tools compose it with the workspace and produce nonsense
    nested paths), so reject it here instead; `~` is expanded.  The missing
    directory is created by the shell (EnsureDir), not here.
    """
    p = Path(str(raw)).expanduser()
    if not p.is_absolute():
        raise CommandRejected(
            "invalid_request",
            f"workspace_dir must be an absolute path (got {raw!r})",
        )
    return str(p)


def _message_drafts(
    *,
    project_id: str,
    session_id: str,
    sender: str,
    content: str,
    run_id: str | None = None,
    images: list[str] | None = None,
    image_artifact_ids: list[str | None] | None = None,
) -> tuple[EventDraft, DeliverMessage]:
    """一条投递 = message_injected 草稿 + DeliverMessage 效果（message_id 一致）。

    事件由 bus 在第二拍落日志，inbox 入队在第四拍——事件先于投递落地。
    """
    message_id = new_id("msg")
    return (
        EventDraft(
            "agent.message_injected",
            stream="project",
            project_id=project_id,
            session_id=session_id,
            run_id=run_id,
            data=Mailbox.message_data(
                message_id=message_id,
                sender=sender,
                content=content,
                images=images,
                image_artifact_ids=image_artifact_ids,
            ),
        ),
        DeliverMessage(
            session_id,
            Mailbox.message_payload(message_id=message_id, sender=sender, content=content, images=images),
        ),
    )


# --------------------------------------------------------------------- deciders


def _decide_create_project(core: RuntimeCore, command: Command) -> Decision:
    payload = command.payload
    name = str(payload.get("name") or "").strip()
    if not name:
        raise CommandRejected("invalid_request", "project name is required")
    project_id = new_id("prj")
    settings = ProjectSettings.model_validate(payload.get("settings") or {})
    effects: list[Effect] = []
    if payload.get("workspace_dir"):
        workspace_dir = _normalize_workspace(payload["workspace_dir"])
    else:
        # 未提供时默认 per-project 工作区：workspace_dir=None 会让下游
        # 文件/bash 工具的相对路径解析到进程 cwd，串到别的任务目录（GH #24）。
        workspace_dir = str(project_workspace_dir(project_id))
    effects.append(EnsureDir(workspace_dir))
    project = Project(id=project_id, name=name, workspace_dir=workspace_dir, settings=settings)
    return Decision(
        events=(
            EventDraft(
                "project.created",
                stream="project",
                project_id=project_id,
                data=project.model_dump(mode="json"),
            ),
        ),
        effects=tuple(effects),
        result=ResultRef("project", project_id),
    )


def _decide_update_project(core: RuntimeCore, command: Command) -> Decision:
    project = core.require_project(_project_id(core, command))
    payload = command.payload
    changes: dict[str, Any] = {}
    for field in ("name", "workspace_dir", "archived"):
        if field in payload:
            changes[field] = payload[field]
    effects: list[Effect] = []
    if changes.get("workspace_dir"):
        changes["workspace_dir"] = _normalize_workspace(changes["workspace_dir"])
        effects.append(EnsureDir(changes["workspace_dir"]))
    drafts: list[EventDraft] = []
    if changes:
        # dict(changes) 冻结事件负载：settings 合并走独立事件，绝不能让
        # 后续的本地变更漏进已落日志的 envelope（旧代码的引用泄漏曾让
        # project.updated 的 data 混入 ProjectSettings 对象，落盘即崩）。
        drafts.append(
            EventDraft(
                "project.updated",
                stream="project",
                project_id=project.id,
                data={"changes": dict(changes), "actor": command.actor},
            )
        )
    if "settings" in payload:
        # decide 侧校验：非法 settings 必须在事件落日志之前抛错。
        new_settings = ProjectSettings.model_validate(payload["settings"])
        drafts.append(
            EventDraft(
                "project.settings_changed",
                stream="project",
                project_id=project.id,
                data={"changes": payload["settings"], "actor": command.actor},
            )
        )
        # 事件驱动督导（Task 4）：切回 dag_guided 沿补一次待办通知——退出
        # guided 期间生产端通知口是关闭的，积压在持久化信箱里；只在迁移沿
        # 触发（guided→guided 重写不重复通知）。shell 侧的 reconcile 按
        # 状态表补通知：failed/cancelled 的 supervisor 不复活、待办不清空。
        if (
            new_settings.orchestration_mode is OrchestrationMode.DAG_GUIDED
            and project.settings.orchestration_mode is not OrchestrationMode.DAG_GUIDED
        ):
            effects.append(ReconcileSupervision(project.id))
    return Decision(events=tuple(drafts), effects=tuple(effects), result=ResultRef("project", project.id))


def _decide_delete_project(core: RuntimeCore, command: Command) -> Decision:
    """硬删除（两步道安全语义）：只允许删已归档且无存活 agent 的项目。

    非终态 compute job 的门禁在 API 路由层（需要查中央 compute.db，decide
    保持纯）。删除本体是 tombstone 事件 ``project.deleted``——事件日志
    （权威）不物理删，重放后 core 同样不含该项目；磁盘支撑数据的清理由
    DeleteProjectData 效果承担。
    """
    project = core.require_project(_project_id(core, command))
    if not project.archived:
        raise CommandRejected("state_conflict", "archive the project before deleting")
    live = [
        agent
        for agent in core.agents.values()
        if agent.project_id == project.id and agent.state not in _CANCEL_TERMINAL_STATES
    ]
    if live:
        raise CommandRejected(
            "state_conflict",
            f"project has {len(live)} live agent(s); cancel them before deleting",
        )
    return Decision(
        events=(
            EventDraft(
                "project.deleted",
                stream="project",
                project_id=project.id,
                data={"actor": command.actor},
            ),
        ),
        effects=(DeleteProjectData(project.id),),
        # 字面量结果：apply 后项目已从 core 移除，ResultRef 解析不到活对象。
        result={"deleted": project.id},
    )


def _decide_spawn_agent(core: RuntimeCore, command: Command) -> Decision:
    project_id = _project_id(core, command)
    project = core.require_project(project_id)
    payload = command.payload
    role_id = str(payload.get("role_id") or "")
    parent_session_id = payload.get("parent_session_id")
    requested = EventDraft(
        "agent.spawn_requested",
        stream="project",
        project_id=project_id,
        data={
            "role_id": role_id,
            "parent_session_id": parent_session_id,
            "actor": command.actor,
        },
    )
    try:
        role = core.roles.require(role_id)
        if parent_session_id is not None:
            parent = core.require_agent(parent_session_id)
            if parent.project_id != project_id:
                raise CommandRejected("invalid_request", "parent agent belongs to another project")
        settings_patch = RuntimeSettingsPatch.model_validate(payload.get("settings") or {})
        settings = core.agent_host.effective_settings(project, role, settings_patch)
        agent = core.agent_host.build(
            project=project,
            role=role,
            parent_session_id=parent_session_id,
            display_name=payload.get("display_name"),
            settings=settings,
        )
    except CommandRejected as exc:
        # 拒绝也要留领域审计轨迹：spawn_requested + spawn_rejected 随拒绝落日志。
        raise CommandRejected(
            exc.code,
            exc.message,
            events=(
                requested,
                EventDraft(
                    "agent.spawn_rejected",
                    stream="project",
                    project_id=project_id,
                    data={"code": exc.code, "message": exc.message, "actor": command.actor},
                ),
            ),
        ) from exc
    drafts: list[EventDraft] = [
        requested,
        EventDraft(
            "agent.spawned",
            stream="project",
            project_id=project_id,
            session_id=agent.id,
            data=agent.model_dump(mode="json"),
        ),
    ]
    effects: list[Effect] = []
    if settings.api_key:
        # api_key 是 write-only 秘密，不进事件/快照；活对象在 apply 后由
        # PatchApiKey 补挂内存覆盖（重放/恢复出的 core 回落全局 key，与既有语义一致）。
        effects.append(PatchApiKey(agent.id, settings.api_key))
    query = str(payload.get("query") or "").strip()
    if query:
        message_draft, deliver = _message_drafts(
            project_id=project_id, session_id=agent.id, sender="system", content=query
        )
        drafts.append(message_draft)
        effects.append(deliver)
        effects.append(ScheduleAgent(agent.id))
    return Decision(events=tuple(drafts), effects=tuple(effects), result=ResultRef("agent", agent.id))


def _decide_patch_agent_settings(core: RuntimeCore, command: Command) -> Decision:
    agent = core.require_agent(command.target.get("session_id", ""))
    patch = RuntimeSettingsPatch.model_validate(command.payload)
    changes = patch.model_dump(exclude_unset=True)
    effects: list[Effect] = []
    if patch.api_key is not None:
        # 空字符串表示"清除覆盖、回落全局 key"；按实际值记布尔，别把
        # api_key_set 记成 True（审计事件里要能区分覆盖/回落）。
        changes["api_key_set"] = bool(patch.api_key)
        # api_key 不进事件：apply 后由 PatchApiKey 补挂内存覆盖（含清 key）。
        effects.append(PatchApiKey(agent.id, patch.api_key))
    changes.pop("api_key", None)
    next_revision = agent.settings_revision + 1
    if (
        patch.orchestration_mode is OrchestrationMode.DAG_GUIDED
        and agent.settings.orchestration_mode is not OrchestrationMode.DAG_GUIDED
    ):
        # 与 _decide_update_project 同一迁移沿：agent 中途切入 dag_guided 也
        # 补一次督导待办通知（guided→guided 重补丁不重复触发）。
        effects.append(ReconcileSupervision(agent.project_id))
    return Decision(
        events=(
            EventDraft(
                "agent.settings_changed",
                stream="project",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=agent.current_run.run_id if agent.current_run else None,
                data={"changes": changes, "actor": command.actor, "settings_revision": next_revision},
            ),
        ),
        effects=tuple(effects),
        result=ResultRef("agent", agent.id),
    )


def _decide_inject_agent_message(core: RuntimeCore, command: Command) -> Decision:
    agent = core.require_agent(command.target.get("session_id", ""))
    content = str(command.payload.get("content") or "").strip()
    if not content:
        raise CommandRejected("invalid_request", "message content is required")
    images = command.payload.get("images")
    if images is not None:
        if not isinstance(images, list) or not all(isinstance(p, str) and p for p in images):
            raise CommandRejected("invalid_request", "images must be a list of workspace-absolute paths")
    image_artifact_ids = command.payload.get("image_artifact_ids")
    if image_artifact_ids is not None:
        if not isinstance(image_artifact_ids, list) or not all(
            a is None or isinstance(a, str) for a in image_artifact_ids
        ):
            raise CommandRejected(
                "invalid_request", "image_artifact_ids must be a list of strings or nulls"
            )
    message_draft, deliver = _message_drafts(
        project_id=agent.project_id,
        session_id=agent.id,
        sender=command.actor,
        content=content,
        run_id=agent.current_run.run_id if agent.current_run else None,
        images=images or None,
        image_artifact_ids=image_artifact_ids or None,
    )
    # A message to a sleeping or terminal agent is a fresh instruction to the
    # same identity: wake it (reopening a new run) instead of making the user
    # perform a separate restart step.  Externalised context (goal pin, DAG,
    # memory, workspace) is re-assembled every turn, so the new run picks up
    # where the agent left off conceptually.
    # system 投递（计算通知 / reminder）遵守 park-don't-wake：failed/cancelled
    # 只写信箱，绝不把用户取消过的 agent 拉回 queued。
    if command.actor == "system" and agent.state in {
        AgentState.FAILED,
        AgentState.CANCELLED,
    }:
        wake_drafts, should_schedule = [], False
    else:
        wake_drafts, should_schedule = plan_wake(agent)
    effects: list[Effect] = [deliver]
    if should_schedule:
        effects.append(ScheduleAgent(agent.id))
    return Decision(
        events=(message_draft, *wake_drafts),
        effects=tuple(effects),
        result=ResultRef("agent", agent.id),
    )


_CANCEL_TERMINAL_STATES = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}


def _live_descendants(core: RuntimeCore, session_id: str) -> list[AgentSession]:
    """全部存活（非终态）后代，父先子后（BFS，深度不设限）。

    今天的 spawn 规则只有 Coordinator 能派生（结构深度 1），但级联按树走，
    规则放开后无需再改。终态后代自然跳过：succeeded/failed 无可取消，
    cancelled 幂等。
    """
    by_parent: dict[str, list[AgentSession]] = {}
    for agent in core.agents.values():
        if agent.parent_session_id:
            by_parent.setdefault(agent.parent_session_id, []).append(agent)
    descendants: list[AgentSession] = []
    visited = {session_id}
    queue = [session_id]
    while queue:
        current = queue.pop(0)
        for child in by_parent.get(current, ()):
            if child.id in visited or child.state in _CANCEL_TERMINAL_STATES:
                continue
            visited.add(child.id)
            descendants.append(child)
            queue.append(child.id)
    return descendants


def _cancel_agent_drafts(
    agent: AgentSession,
    *,
    actor: str | None,
    message: str | None,
    cause: str,
    parent_session_id: str | None = None,
) -> list[EventDraft]:
    """一个 agent 的取消事件组：cancel_requested → state_changed → cancelled。

    被级联取消的后代带 ``cause="parent_cancelled"`` 审计标记；终态判定与
    顶层的差异（succeeded/failed 顶层抛错、后代静默跳过）在调用方。
    """
    data: dict[str, Any] = {"message": message, "actor": actor, "cause": cause}
    if parent_session_id is not None:
        data["parent_session_id"] = parent_session_id
    drafts = [
        EventDraft(
            "agent.cancel_requested",
            stream="project",
            project_id=agent.project_id,
            session_id=agent.id,
            data=data,
        )
    ]
    drafts.extend(plan_cancel(agent))
    drafts.append(
        EventDraft(
            "agent.cancelled",
            stream="project",
            project_id=agent.project_id,
            session_id=agent.id,
            data={"session_id": agent.id},
        )
    )
    return drafts


def _decide_cancel_agent(core: RuntimeCore, command: Command) -> Decision:
    agent = core.require_agent(command.target.get("session_id", ""))
    cancel_drafts = plan_cancel(agent)  # succeeded/failed 抛错；cancelled 幂等空计划
    if not cancel_drafts:
        return Decision(result=ResultRef("agent", agent.id))
    message = command.payload.get("message")
    # 取消级联（C2）：父取消时全部存活后代一并落 cancelled 终态——异步
    # （is_wait=False）子 agent 不再跑到完成空烧 LLM/计算。子的完成回传按
    # park-don't-wake 纪律投递信箱驻留，绝不唤醒已取消的父。
    descendants = _live_descendants(core, agent.id)
    drafts: list[EventDraft] = _cancel_agent_drafts(
        agent, actor=command.actor, message=message, cause="explicit"
    )
    effects: list[Effect] = []
    if message:
        message_draft, deliver = _message_drafts(
            project_id=agent.project_id,
            session_id=agent.id,
            sender=command.actor,
            content=str(message),
        )
        # 投递草稿放在 state_changed/cancelled 之前，与原事件顺序一致
        # （cancel_requested → message_injected → state_changed → cancelled）。
        drafts.insert(1, message_draft)
        effects.append(deliver)
    for child in descendants:
        drafts.extend(
            _cancel_agent_drafts(
                child,
                actor=command.actor,
                message=None,
                cause="parent_cancelled",
                parent_session_id=agent.id,
            )
        )
    # 效果顺序：先停 launch group（不再 spawn 新子 agent），再取消父的
    # run（父轮次不再推进、不再派生），最后逐个取消子的 run。
    effects.append(CancelLaunchGroups(agent.id))
    effects.append(CancelRunner(agent.id))
    effects.extend(CancelRunner(child.id) for child in descendants)
    return Decision(events=tuple(drafts), effects=tuple(effects), result=ResultRef("agent", agent.id))


def _decide_restart_agent(core: RuntimeCore, command: Command) -> Decision:
    agent = core.require_agent(command.target.get("session_id", ""))
    message = command.payload.get("message")
    settings_patch = RuntimeSettingsPatch.model_validate(command.payload.get("settings") or {})
    previous_outcome = agent.state.value
    requested = EventDraft(
        "agent.restart_requested",
        stream="project",
        project_id=agent.project_id,
        session_id=agent.id,
        data={"message": message, "actor": command.actor},
    )
    try:
        run_id, restart_drafts = plan_restart(agent)
    except CommandRejected as exc:
        # restart_requested 是已接受意图的审计，随拒绝一起落日志。
        raise CommandRejected(exc.code, exc.message, events=(requested,)) from exc
    drafts: list[EventDraft] = [requested, *restart_drafts]
    effects: list[Effect] = []
    if message:
        message_draft, deliver = _message_drafts(
            project_id=agent.project_id,
            session_id=agent.id,
            sender=command.actor,
            content=str(message),
            run_id=run_id,
        )
        drafts.append(message_draft)
        effects.append(deliver)
    planned_settings = None
    next_revision = agent.settings_revision
    if settings_patch.model_fields_set:
        changes = settings_patch.model_dump(exclude_unset=True)
        if settings_patch.api_key is not None:
            changes["api_key_set"] = bool(settings_patch.api_key)
            effects.append(PatchApiKey(agent.id, settings_patch.api_key))
        changes.pop("api_key", None)
        next_revision = agent.settings_revision + 1
        drafts.append(
            EventDraft(
                "agent.settings_changed",
                stream="project",
                project_id=agent.project_id,
                session_id=agent.id,
                run_id=run_id,
                data={"changes": changes, "actor": command.actor, "settings_revision": next_revision},
            )
        )
        planned_settings = agent.settings.apply(settings_patch)
    # restarted 载荷里的 agent 快照：decide 不 apply，按草稿将推出的状态构造
    # （state=queued、current_run=None、settings/revision 已补丁）。updated_at
    # 是 decide 前的值——该载荷仅审计展示，无程序化消费方。
    snapshot_agent = agent.model_copy(
        update={
            "state": AgentState.QUEUED,
            "current_run": None,
            "settings_revision": next_revision,
            **({"settings": planned_settings} if planned_settings is not None else {}),
        }
    )
    drafts.append(
        EventDraft(
            "agent.restarted",
            stream="project",
            project_id=agent.project_id,
            session_id=agent.id,
            data={"run_id": run_id, "agent": snapshot_agent.model_dump(mode="json")},
        )
    )
    drafts.append(
        EventDraft(
            "agent.context_reset",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={
                "reason": "restart_command",
                "previous_outcome": previous_outcome,
                "actor": command.actor,
                "note": _CONTEXT_RESET_NOTE,
            },
        )
    )
    if message:
        effects.append(ScheduleAgent(agent.id))
    return Decision(events=tuple(drafts), effects=tuple(effects), result=ResultRef("agent", agent.id))


def _decide_update_role(core: RuntimeCore, command: Command) -> Decision:
    role = core.roles.require(command.target.get("role_id", ""))
    payload = command.payload
    allowed = {"default_settings", "permissions", "tool_policy", "can_spawn", "spawn_roles"}
    changes = {key: value for key, value in payload.items() if key in allowed}
    if not changes:
        raise CommandRejected("invalid_request", "no mutable role fields supplied")
    return Decision(
        events=(
            EventDraft(
                "role.updated",
                stream="project",
                project_id=_project_id(core, command),
                data={"role_id": role.role_id, "changes": changes, "actor": command.actor},
            ),
        ),
        result=ResultRef("role", role.role_id),
    )


DECIDERS: dict[str, Decider] = {
    "project.create": _decide_create_project,
    "project.update": _decide_update_project,
    "project.delete": _decide_delete_project,
    "agent.spawn": _decide_spawn_agent,
    "agent.settings_update": _decide_patch_agent_settings,
    "agent.message": _decide_inject_agent_message,
    "agent.cancel": _decide_cancel_agent,
    "agent.restart": _decide_restart_agent,
    "role.update": _decide_update_role,
}


# --------------------------------------------------------------------- wrappers
# 已是事件投影的 broker 不进 decide（理由见模块 docstring）：这些 handler
# 只做校验 + 委托，事件由 broker/manager 自己落，bus 在执行后扫尾发布/持久化。


async def _compact_agent(core: RuntimeCore, command: Command) -> CommandResult:
    agent = core.require_agent(command.target.get("session_id", ""))
    envelope = core.record(
        "compaction.requested",
        stream="agent",
        project_id=agent.project_id,
        session_id=agent.id,
        run_id=agent.current_run.run_id if agent.current_run else None,
        data={"actor": command.actor},
    )
    # The runner picks this up at the next turn boundary; the session context
    # 跨 run 连续（Task 4），压缩请求跨 run 存活、应用到会话上下文投影。
    # pending_compactions 是 compaction.requested 的事件投影：唯一写入点是
    # apply_event（这里），消费在 runner 的轮次边界。
    apply_event(core, envelope)
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=agent)


async def _decide_approval(core: RuntimeCore, command: Command) -> CommandResult:
    project_id = _project_id(core, command)
    core.require_project(project_id)
    payload = command.payload
    approval_id = str(payload.get("approval_id") or "")
    decision = str(payload.get("decision") or "")
    if decision not in {"approved", "denied"}:
        raise CommandRejected("invalid_request", "decision must be 'approved' or 'denied'")
    await core.pending.decide_approval(project_id, approval_id, decision, str(payload.get("reason") or ""))
    return CommandResult(
        command_id=command.command_id,
        event_id=_last_event_id(core),
        data={"approval_id": approval_id, "decision": decision},
    )


async def _respond_interaction(core: RuntimeCore, command: Command) -> CommandResult:
    project_id = _project_id(core, command)
    core.require_project(project_id)
    payload = command.payload
    record = await core.pending.respond_interaction(
        project_id,
        str(payload.get("interaction_id") or ""),
        str(payload.get("response") or ""),
    )
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=record)


async def _inject_context(core: RuntimeCore, command: Command) -> CommandResult:
    """Lightweight context injection: pin / unpin / push a notice.

    The event-sourced NoticeManager writes the corresponding
    context.pin_set / context.pin_cleared / context.injected event itself
    (deduplicated), so this handler only validates and delegates.  The
    injected content reaches the agent's next LLM turn as a system message;
    the agent is NOT woken — use agent.message when a wakeup is wanted.
    """
    agent = core.require_agent(command.target.get("session_id", ""))
    kind = str(command.payload.get("kind") or "push")
    key = str(command.payload.get("key") or "")
    content = str(command.payload.get("content") or "")
    if kind == "pin":
        if not key:
            raise CommandRejected("invalid_request", "pin requires a key")
        core.notices.pin(agent.id, key, content)
    elif kind == "unpin":
        if not key:
            raise CommandRejected("invalid_request", "unpin requires a key")
        core.notices.unpin(agent.id, key)
    elif kind == "push":
        if not content.strip():
            raise CommandRejected("invalid_request", "push requires non-empty content")
        core.notices.push(agent.id, content)
    else:
        raise CommandRejected("invalid_request", f"unknown inject kind {kind!r}")
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=agent)


WRAPPERS: dict[str, Wrapper] = {
    "agent.compact": _compact_agent,
    "approval.decide": _decide_approval,
    "interaction.respond": _respond_interaction,
    "context.inject": _inject_context,
}


def _last_event_id(core: RuntimeCore) -> str:
    events = list(core.event_log)
    return events[-1].event_id if events else ""


# ------------------------------------------------------------------ effects shell


def _mkdir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


_ARTIFACT_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def _artifact_dir(artifacts_root: Path, artifact_id: str) -> Path | None:
    """Resolve a per-artifact directory only if it stays under ``artifacts_root``."""
    if not artifact_id or len(artifact_id) > 200:
        return None
    if any(ch not in _ARTIFACT_ID_CHARS for ch in artifact_id):
        return None
    root = artifacts_root.resolve()
    target = (root / artifact_id).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def _delete_project_data(project_id: str) -> None:
    """硬删除的磁盘清理：conversations/<pid>/ 整树 + 该项目 artifact 文件。

    artifact id 从 per-project 库的 artifacts 表枚举（表可能不存在，按空
    处理）；workspace_dir（用户数据）、compute.db 历史行、runtime-v2.db
    事件（权威）一律不动。全程 ignore_errors/按空处理：重放或部分清理后
    的重试必须幂等。
    """
    artifact_ids: list[str] = []
    db_path = conversation_db_path(project_id)
    if db_path.is_file():
        try:
            with contextlib.closing(
                sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            ) as con:
                rows = con.execute("SELECT artifact_id FROM artifacts").fetchall()
            artifact_ids = [str(row[0]) for row in rows]
        except sqlite3.OperationalError:
            pass  # artifacts 表不存在（从未登记过 artifact）按空处理
    artifacts_root = data_dir() / "artifacts"
    for artifact_id in artifact_ids:
        target = _artifact_dir(artifacts_root, artifact_id)
        if target is None:
            continue
        shutil.rmtree(target, ignore_errors=True)
    shutil.rmtree(conversation_dir(project_id), ignore_errors=True)


async def _execute_effect(core: RuntimeCore, effect: Effect) -> None:
    """执行单个效果。只在第四拍被 CommandBus 调用（事件与状态均已落地）。"""
    if isinstance(effect, EnsureDir):
        await asyncio.to_thread(_mkdir, effect.path)
    elif isinstance(effect, PatchApiKey):
        core.require_agent(effect.session_id).settings.api_key = effect.api_key
    elif isinstance(effect, DeliverMessage):
        core.mailbox.enqueue(effect.session_id, effect.message)
    elif isinstance(effect, ScheduleAgent):
        if core.runner is not None:
            core.runner.schedule(effect.session_id)
    elif isinstance(effect, CancelRunner):
        if core.runner is not None:
            await core.runner.cancel(effect.session_id)
    elif isinstance(effect, CancelLaunchGroups):
        manager = getattr(core, "launch_groups", None)
        if manager is not None:
            await manager.cancel_for_parent(effect.session_id)
    elif isinstance(effect, DeleteProjectData):
        await asyncio.to_thread(_delete_project_data, effect.project_id)
    elif isinstance(effect, ReconcileSupervision):
        # 切回 dag_guided 的补通知（Task 4）。失败不炸模式切换命令本身——
        # 待办已持久化，下次项目装载的 reconcile 仍会补；记 warning 可诊断。
        from cloudra.runtime_v2.supervision import reconcile_supervision

        try:
            await reconcile_supervision(core, effect.project_id)
        except Exception:
            logger.warning(
                "[supervision] reconcile on return to dag_guided failed for %s",
                effect.project_id,
                exc_info=True,
            )
    else:
        raise TypeError(f"unknown effect {effect!r}")


class CommandBus:
    """命令入口：四拍执行 + 快照节流（语义见模块 docstring）。"""

    def __init__(self, core: RuntimeCore) -> None:
        self.core = core
        self._snapshot_event_mark = len(core.event_log)
        self._snapshot_at = time.monotonic()

    async def execute(self, command: Command) -> CommandResult:
        async with self.core.command_lock:
            return await self._execute_locked(command)

    async def _execute_locked(self, command: Command) -> CommandResult:
        core = self.core
        cached = core.cached_result(command.command_id)
        if cached is not None:
            return cached
        decider = DECIDERS.get(command.type)
        wrapper = WRAPPERS.get(command.type)
        if decider is None and wrapper is None:
            raise CommandRejected("invalid_request", f"unknown command type {command.type!r}")
        try:
            if command.type == "project.delete":
                from cloudra.persistence.database import ComputeDB
                from cloudra.services.compute_store import acount_active_compute_jobs

                project_id = _project_id(core, command)
                active = await acount_active_compute_jobs(ComputeDB(), project_id)
                if active:
                    raise CommandRejected(
                        "state_conflict",
                        f"project has {active} active compute job(s); "
                        "run POST /api/v2/compute/cancel-all first",
                    )
            if decider is not None:
                # 拍 1：纯 decide（守卫校验在这里抛 CommandRejected）
                decision = decider(core, command)
                # 拍 2-4：落日志/发布/持久化 → apply → effects
                result = await self._apply_decision(command, decision)
            else:
                # 薄包装：broker 自带事件流与 future 解析，bus 扫尾发布/持久化
                result = await wrapper(core, command)
                await self._flush()
        except CommandRejected as exc:
            result = await self._reject(command, exc)
        core.remember(command, result)
        await self._maybe_snapshot()
        return result

    # -------------------------------------------------------------- internals

    def _append_draft(self, draft: EventDraft) -> EventEnvelope:
        return self.core.event_log.append(
            draft.type,
            stream=draft.stream,
            project_id=draft.project_id,
            session_id=draft.session_id,
            run_id=draft.run_id,
            data=draft.data,
        )

    async def _flush(self) -> None:
        """拍 2：经共享 EventWriter 持久化（store 存在时）并发布未发布事件。

        bus 直接持久化自己的事件，不再依赖 API 层的 hub 持久化订阅搭车；
        订阅仍在（运行期 turn 内事件靠它），append_event 幂等（INSERT OR
        IGNORE），重叠写无害。writer 的游标保证不重发/不重写。
        """
        await self.core.event_writer.flush()

    async def _persist_appended(self, keep: int | None = None) -> None:
        """Persist the just-appended tail; drop only this caller's addition if the store write fails."""
        try:
            await self._flush()
        except EventPersistenceError:
            self.core.event_writer.discard_unpersisted(keep=keep)
            raise

    async def _apply_decision(self, command: Command, decision: Decision) -> CommandResult:
        core = self.core
        envelopes: list[EventEnvelope] = []
        try:
            for draft in decision.events:
                before_append = len(core.event_log)
                envelope = self._append_draft(draft)
                await self._persist_appended(keep=before_append)
                apply_event(core, envelope)
                envelopes.append(envelope)
            # 拍 4：副作用（runner/mailbox/文件系统/内存秘密覆盖）
            for effect in decision.effects:
                await _execute_effect(core, effect)
        except EventPersistenceError:
            # spawned 已落盘：返回已创建的 agent 并尽量跑完 effects，
            # 避免 HTTP 500 触发新 command_id 再造一个 coordinator。
            if any(envelope.type == "agent.spawned" for envelope in envelopes):
                for effect in decision.effects:
                    try:
                        await _execute_effect(core, effect)
                    except Exception:
                        logger.exception(
                            "spawn effect after partial persist failed for %s",
                            command.command_id,
                        )
                return CommandResult(
                    command_id=command.command_id,
                    accepted=True,
                    event_id=envelopes[-1].event_id,
                    data=self._resolve_result(decision.result),
                )
            raise
        return CommandResult(
            command_id=command.command_id,
            event_id=envelopes[-1].event_id if envelopes else "",
            data=self._resolve_result(decision.result),
        )

    def _resolve_result(self, result: Any) -> Any:
        """ResultRef 在 apply+effects 之后解析为活对象；字面量原样返回。"""
        core = self.core
        if isinstance(result, ResultRef):
            if result.kind == "project":
                return core.require_project(result.key)
            if result.kind == "agent":
                return core.require_agent(result.key)
            if result.kind == "role":
                return core.roles.require(result.key)
        return result

    async def _reject(self, command: Command, exc: CommandRejected) -> CommandResult:
        """拒绝路径：先落异常携带的领域审计草稿，再落 command.rejected。

        （顺带修复旧行为：spawn_requested/spawn_rejected 等拒绝轨迹此前只进
        内存日志、从不发布/持久化，重启即丢。）
        """
        core = self.core
        appended: list[EventEnvelope] = []
        for draft in exc.events:
            before_append = len(core.event_log)
            appended.append(self._append_draft(draft))
            await self._persist_appended(keep=before_append)
        before_append = len(core.event_log)
        appended.append(
            core.record(
                "command.rejected",
                stream="project",
                project_id=_project_id(core, command),
                data={
                    "command_type": command.type,
                    "code": exc.code,
                    "message": exc.message,
                },
            )
        )
        await self._persist_appended(keep=before_append)
        return CommandResult(
            command_id=command.command_id,
            accepted=False,
            event_id=appended[-1].event_id,
            data={"error": {"code": exc.code, "message": exc.message}},
        )

    # ---------------------------------------------------------- snapshot cache

    async def _maybe_snapshot(self) -> None:
        """节流快照：距上次满 _SNAPSHOT_EVENT_INTERVAL 条事件或
        _SNAPSHOT_TIME_INTERVAL_S 秒（取先到，命令边界检查）落一次。"""
        core = self.core
        if core.store is None:
            return
        if (
            len(core.event_log) - self._snapshot_event_mark < _SNAPSHOT_EVENT_INTERVAL
            and time.monotonic() - self._snapshot_at < _SNAPSHOT_TIME_INTERVAL_S
        ):
            return
        await self.flush_snapshot()

    async def flush_snapshot(self) -> None:
        """无条件落一次快照（节流旁路）。进程关闭路径显式调用；无 store no-op。"""
        core = self.core
        if core.store is None:
            return
        # 先冲刷事件 writer：快照水位必须是已落盘前缀，不能用 live
        # high_watermarks——并发 append 会把水位抬过尚未 persist 的事件。
        await core.event_writer.flush()
        last_seqs = core.event_writer.persisted_watermarks()
        payload = {
            "projects": {k: v.model_dump(mode="json") for k, v in core.projects.items()},
            "agents": {k: v.model_dump(mode="json") for k, v in core.agents.items()},
            "roles": {k: v.model_dump(mode="json") for k, v in core.roles._roles.items()},
            "runtime_defaults": core.runtime_defaults.model_dump(mode="json"),
            "session_contexts": {
                k: v.model_dump(mode="json") for k, v in core.session_contexts.items()
            },
            "pending_compactions": sorted(core.pending_compactions),
        }
        await asyncio.to_thread(core.store.write_snapshot_payload, payload, last_seqs)
        self._snapshot_event_mark = len(core.event_log)
        self._snapshot_at = time.monotonic()
