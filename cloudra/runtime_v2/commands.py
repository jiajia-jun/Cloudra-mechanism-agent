"""Command bus: every user operation becomes an event, then mutates memory.

Handler contract:
- record all control events *before* applying the corresponding state change;
- return a ``CommandResult`` whose ``data`` is the latest resource snapshot;
- raise ``CommandRejected`` for stable, user-visible errors.
The bus publishes newly appended events to the hub after the handler returns.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import (
    Command,
    CommandRejected,
    CommandResult,
    Project,
    ProjectSettings,
    RuntimeSettingsPatch,
    new_id,
)

Handler = Callable[[RuntimeCore, Command], Awaitable[CommandResult]]


def _project_id(core: RuntimeCore, command: Command) -> str:
    return command.target.get("project_id") or "runtime"


def _normalize_workspace(raw: Any) -> str:
    """Normalize a workspace dir at the command layer.

    A relative path would silently resolve against the server process cwd
    downstream (tools compose it with the workspace and produce nonsense
    nested paths), so reject it here instead; `~` is expanded and a missing
    directory is created.
    """
    from pathlib import Path

    p = Path(str(raw)).expanduser()
    if not p.is_absolute():
        raise CommandRejected(
            "invalid_request",
            f"workspace_dir must be an absolute path (got {raw!r})",
        )
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


async def _create_project(core: RuntimeCore, command: Command) -> CommandResult:
    payload = command.payload
    name = str(payload.get("name") or "").strip()
    if not name:
        raise CommandRejected("invalid_request", "project name is required")
    project_id = new_id("prj")
    settings = ProjectSettings.model_validate(payload.get("settings") or {})
    workspace = payload.get("workspace_dir")
    project = Project(
        id=project_id,
        name=name,
        workspace_dir=_normalize_workspace(workspace) if workspace else None,
        settings=settings,
    )
    core.record(
        "project.created",
        stream="project",
        project_id=project_id,
        data=project.model_dump(mode="json"),
    )
    core.projects[project_id] = project
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=project)


async def _update_project(core: RuntimeCore, command: Command) -> CommandResult:
    project = core.require_project(_project_id(core, command))
    payload = command.payload
    changes: dict[str, Any] = {}
    for field in ("name", "workspace_dir", "archived"):
        if field in payload:
            changes[field] = payload[field]
    if changes.get("workspace_dir"):
        changes["workspace_dir"] = _normalize_workspace(changes["workspace_dir"])
    if changes:
        core.record(
            "project.updated",
            stream="project",
            project_id=project.id,
            data={"changes": changes, "actor": command.actor},
        )
    if "settings" in payload:
        settings = ProjectSettings.model_validate(payload["settings"])
        core.record(
            "project.settings_changed",
            stream="project",
            project_id=project.id,
            data={"changes": payload["settings"], "actor": command.actor},
        )
        changes["settings"] = settings
    project = project.model_copy(update=changes)
    project.touch()
    core.projects[project.id] = project
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=project)


async def _spawn_agent(core: RuntimeCore, command: Command) -> CommandResult:
    project_id = _project_id(core, command)
    project = core.require_project(project_id)
    payload = command.payload
    role_id = str(payload.get("role_id") or "")
    parent_session_id = payload.get("parent_session_id")
    core.record(
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
        core.record(
            "agent.spawn_rejected",
            stream="project",
            project_id=project_id,
            data={"code": exc.code, "message": exc.message, "actor": command.actor},
        )
        raise
    core.agents[agent.id] = agent
    core.mailbox.ensure_inbox(agent.id)
    query = str(payload.get("query") or "").strip()
    if query:
        core.mailbox.deliver(
            to_session_id=agent.id,
            project_id=project_id,
            content=query,
            sender="system",
        )
    core.record(
        "agent.spawned",
        stream="project",
        project_id=project_id,
        session_id=agent.id,
        data=agent.model_dump(mode="json"),
    )
    if query and core.runner is not None:
        core.runner.schedule(agent.id)
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=agent)


async def _patch_agent_settings(core: RuntimeCore, command: Command) -> CommandResult:
    agent = core.require_agent(command.target.get("session_id", ""))
    patch = RuntimeSettingsPatch.model_validate(command.payload)
    changes = patch.model_dump(exclude_unset=True)
    if patch.api_key is not None:
        # 空字符串表示"清除覆盖、回落全局 key"；按实际值记布尔，别把
        # api_key_set 记成 True（审计事件里要能区分覆盖/回落）。
        changes["api_key_set"] = bool(patch.api_key)
    changes.pop("api_key", None)
    next_revision = agent.settings_revision + 1
    core.record(
        "agent.settings_changed",
        stream="project",
        project_id=agent.project_id,
        session_id=agent.id,
        run_id=agent.current_run.run_id if agent.current_run else None,
        data={"changes": changes, "actor": command.actor, "settings_revision": next_revision},
    )
    core.agent_host.patch_settings(agent, patch)
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=agent)


async def _inject_agent_message(core: RuntimeCore, command: Command) -> CommandResult:
    agent = core.require_agent(command.target.get("session_id", ""))
    content = str(command.payload.get("content") or "").strip()
    if not content:
        raise CommandRejected("invalid_request", "message content is required")
    core.mailbox.deliver(
        to_session_id=agent.id,
        project_id=agent.project_id,
        content=content,
        sender=command.actor,
        run_id=agent.current_run.run_id if agent.current_run else None,
    )
    # A message to a sleeping or terminal agent is a fresh instruction to the
    # same identity: wake it (reopening a new run) instead of making the user
    # perform a separate restart step.  Externalised context (goal pin, DAG,
    # memory, workspace) is re-assembled every turn, so the new run picks up
    # where the agent left off conceptually.
    core.agent_host.wake(agent, runner=core.runner)
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=agent)


async def _compact_agent(core: RuntimeCore, command: Command) -> CommandResult:
    agent = core.require_agent(command.target.get("session_id", ""))
    keep_recent = int(command.payload.get("keep_recent") or 20)
    keep_recent = max(1, min(keep_recent, 500))
    core.record(
        "compaction.requested",
        stream="agent",
        project_id=agent.project_id,
        session_id=agent.id,
        run_id=agent.current_run.run_id if agent.current_run else None,
        data={"keep_recent": keep_recent, "actor": command.actor},
    )
    # The runner picks this up at the next turn boundary; history is
    # in-memory, so compaction only has meaning while a run is alive.
    core.pending_compactions[agent.id] = keep_recent
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=agent)


async def _cancel_agent(core: RuntimeCore, command: Command) -> CommandResult:
    agent = core.require_agent(command.target.get("session_id", ""))
    if agent.state.value in {"succeeded", "failed"}:
        raise CommandRejected("state_conflict", "agent already reached a terminal state")
    if agent.state.value == "cancelled":
        return CommandResult(command_id=command.command_id, event_id="", data=agent)
    message = command.payload.get("message")
    core.record(
        "agent.cancel_requested",
        stream="project",
        project_id=agent.project_id,
        session_id=agent.id,
        data={"message": message, "actor": command.actor},
    )
    if message:
        core.mailbox.deliver(
            to_session_id=agent.id,
            project_id=agent.project_id,
            content=str(message),
            sender=command.actor,
        )
    if core.runner is not None:
        await core.runner.cancel(agent.id)
    core.agent_host.cancel(agent)
    core.record(
        "agent.cancelled",
        stream="project",
        project_id=agent.project_id,
        session_id=agent.id,
        data={"session_id": agent.id},
    )
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=agent)


async def _restart_agent(core: RuntimeCore, command: Command) -> CommandResult:
    agent = core.require_agent(command.target.get("session_id", ""))
    message = command.payload.get("message")
    settings_patch = RuntimeSettingsPatch.model_validate(command.payload.get("settings") or {})
    previous_outcome = agent.state.value
    core.record(
        "agent.restart_requested",
        stream="project",
        project_id=agent.project_id,
        session_id=agent.id,
        data={"message": message, "actor": command.actor},
    )
    run_id = core.agent_host.restart(agent)
    if message:
        core.mailbox.deliver(
            to_session_id=agent.id,
            project_id=agent.project_id,
            content=str(message),
            sender=command.actor,
            run_id=run_id,
        )
    if settings_patch.model_fields_set:
        changes = settings_patch.model_dump(exclude_unset=True)
        if settings_patch.api_key is not None:
            changes["api_key_set"] = bool(settings_patch.api_key)
        changes.pop("api_key", None)
        next_revision = agent.settings_revision + 1
        core.record(
            "agent.settings_changed",
            stream="project",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={"changes": changes, "actor": command.actor, "settings_revision": next_revision},
        )
        core.agent_host.patch_settings(agent, settings_patch)
    core.record(
        "agent.restarted",
        stream="project",
        project_id=agent.project_id,
        session_id=agent.id,
        data={"run_id": run_id, "agent": agent.model_dump(mode="json")},
    )
    core.record(
        "agent.context_reset",
        stream="agent",
        project_id=agent.project_id,
        session_id=agent.id,
        run_id=run_id,
        data={
            "reason": "restart_command",
            "previous_outcome": previous_outcome,
            "actor": command.actor,
            "note": (
                "dialogue history was reset; continuity via "
                "goal/memory/workspace files"
            ),
        },
    )
    if message and core.runner is not None:
        core.runner.schedule(agent.id)
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=agent)


async def _update_role(core: RuntimeCore, command: Command) -> CommandResult:
    role = core.roles.require(command.target.get("role_id", ""))
    payload = command.payload
    allowed = {"default_settings", "permissions", "tool_policy", "can_spawn", "spawn_roles"}
    changes = {key: value for key, value in payload.items() if key in allowed}
    if not changes:
        raise CommandRejected("invalid_request", "no mutable role fields supplied")
    core.record(
        "role.updated",
        stream="project",
        project_id=_project_id(core, command),
        data={"role_id": role.role_id, "changes": changes, "actor": command.actor},
    )
    updated = core.roles.update(role.role_id, changes)
    return CommandResult(command_id=command.command_id, event_id=_last_event_id(core), data=updated)


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


HANDLERS: dict[str, Handler] = {
    "project.create": _create_project,
    "project.update": _update_project,
    "agent.spawn": _spawn_agent,
    "agent.settings_update": _patch_agent_settings,
    "agent.message": _inject_agent_message,
    "agent.cancel": _cancel_agent,
    "agent.compact": _compact_agent,
    "agent.restart": _restart_agent,
    "approval.decide": _decide_approval,
    "interaction.respond": _respond_interaction,
    "role.update": _update_role,
}


def _last_event_id(core: RuntimeCore) -> str:
    events = list(core.event_log)
    return events[-1].event_id if events else ""


class CommandBus:
    def __init__(self, core: RuntimeCore) -> None:
        self.core = core

    async def execute(self, command: Command) -> CommandResult:
        core = self.core
        cached = core.cached_result(command.command_id)
        if cached is not None:
            return cached
        handler = HANDLERS.get(command.type)
        if handler is None:
            raise CommandRejected("invalid_request", f"unknown command type {command.type!r}")
        before = len(core.event_log)
        try:
            result = await handler(core, command)
        except CommandRejected as exc:
            envelope = core.record(
                "command.rejected",
                stream="project",
                project_id=_project_id(core, command),
                data={
                    "command_type": command.type,
                    "code": exc.code,
                    "message": exc.message,
                },
            )
            await core.event_hub.publish(envelope)
            result = CommandResult(
                command_id=command.command_id,
                accepted=False,
                event_id=envelope.event_id,
                data={"error": {"code": exc.code, "message": exc.message}},
            )
            core.remember(command, result)
            return result
        new_events = list(core.event_log)[before:]
        for envelope in new_events:
            await core.event_hub.publish(envelope)
        if core.store is not None:
            await asyncio.to_thread(
                core.store.save_snapshot,
                projects=core.projects,
                agents=core.agents,
                roles=core.roles._roles,
                runtime_defaults=core.runtime_defaults,
                last_seq=core.event_log.last_seq,
            )
        core.remember(command, result)
        return result
