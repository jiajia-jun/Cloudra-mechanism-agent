"""External task lifecycle over the existing Cloudra command and event paths."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Self

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, model_validator

from cloudra.persistence.artifacts import ArtifactService
from cloudra.persistence.paths import project_workspace_dir, workspaces_dir
from cloudra.runtime_v2.agent_host import is_background_parked
from cloudra.runtime_v2.child_manifest import build_child_manifest
from cloudra.runtime_v2.completion import completion_summary
from cloudra.runtime_v2.event_writer import EventPersistenceError
from cloudra.runtime_v2.schemas import AgentSession, AgentState, Command, CommandRejected, CommandResult, Project
from cloudra.services.delegation_schema import (
    MAX_RESULT_WAIT,
    CurrentResult,
    FinishedResult,
    NonBlank,
    PendingResult,
    ProjectName,
    TaskRef,
)

from ..context import LOOPBACK_CLIENTS, ApiContext

_TERMINAL_EVENTS = {"run.finished", "agent.cancelled"}
_WAIT_EVENTS = _TERMINAL_EVENTS | {
    "agent.spawned", "agent.state_changed", "approval.requested", "interaction.requested",
}
_TERMINAL_STATES = {AgentState.SUCCEEDED, AgentState.FAILED, AgentState.CANCELLED}


class StartTask(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    task: NonBlank
    name: ProjectName | None = None
    workspace_dir: NonBlank | None = None
    project_id: NonBlank | None = None

    @model_validator(mode="after")
    def check_project_selection(self) -> Self:
        if self.project_id is not None:
            if self.name is not None or self.workspace_dir is not None:
                raise ValueError("project_id cannot be combined with name or workspace_dir")
        elif self.name is None:
            raise ValueError("name is required when creating a project")
        return self


def _rejection(result: CommandResult, project_id: str | None = None) -> HTTPException:
    detail = dict(result.data["error"])
    if project_id is not None:
        detail["project_id"] = project_id
    code = {"not_found": 404, "forbidden": 403, "state_conflict": 409}.get(detail["code"], 400)
    return HTTPException(status_code=code, detail=detail)


def _independent_workspace(raw: str, occupied: list[Path]) -> str:
    try:
        workspace = Path(raw).expanduser()
        if not workspace.is_absolute() or not workspace.is_dir():
            raise ValueError("workspace is not an absolute directory")
        workspace = workspace.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CommandRejected(
            "invalid_request", "workspace_dir must be an absolute path to an existing directory.",
        ) from exc
    for path in occupied:
        other = path.resolve()
        if workspace.is_relative_to(other) or other.is_relative_to(workspace):
            raise CommandRejected("state_conflict", "workspace_dir overlaps a Cloudra workspace.")
    return str(workspace)


async def _start_task(ctx: ApiContext, body: StartTask) -> TaskRef:
    core = ctx.core
    async with core.command_lock:
        project_id = body.project_id
        if project_id is None:
            workspace_dir = None
            if body.workspace_dir is not None:
                occupied = [workspaces_dir(), *(
                    Path(project.workspace_dir) if project.workspace_dir else project_workspace_dir(project.id)
                    for project in core.projects.values()
                )]
                workspace_dir = await asyncio.to_thread(_independent_workspace, body.workspace_dir, occupied)
            created = await ctx.bus.execute(Command(
                type="project.create",
                payload={"name": body.name, "workspace_dir": workspace_dir},
            ))
            if not created.accepted:
                raise _rejection(created)
            project: Project = created.data
            project_id = project.id
        else:
            project = core.require_project(project_id)
        if project.archived:
            raise CommandRejected("state_conflict", "Project is archived.")
        if any(agent.role_id == "coordinator" for agent in core.list_project_agents(project_id)):
            raise CommandRejected("state_conflict", "Project already has a Coordinator. Send it a message instead.")
        try:
            spawned = await ctx.bus.execute(Command(
                type="agent.spawn",
                target={"project_id": project_id},
                payload={"role_id": "coordinator", "query": body.task},
            ))
        except EventPersistenceError as exc:
            raise HTTPException(503, detail={
                "code": "unavailable",
                "message": "Could not persist the Coordinator launch. Check project progress before retrying.",
                "project_id": project_id,
            }) from exc
        if not spawned.accepted:
            raise _rejection(spawned, project_id)
        # The command bus can return a durable Agent after a partial spawn.
        # A receipt for the spawn alone does not confirm the initial message.
        receipt = await asyncio.to_thread(core.event_log.get, spawned.event_id)
        if receipt is None or receipt.type != "agent.message_injected":
            raise HTTPException(503, detail={
                "code": "unavailable",
                "message": "Coordinator created, but the initial message was not confirmed. Check project progress.",
                "project_id": project_id,
            })
        return {"project_id": project_id, "session_id": spawned.data.id}


def _outcome(core, agent: AgentSession, boundary: int) -> FinishedResult | None:
    if is_background_parked(core, agent, before_session_seq=boundary):
        return None
    log = core.event_log
    terminals = log.query_session(
        agent.id, before_session_seq=boundary, types=_TERMINAL_EVENTS, limit=1,
    )
    if not terminals:
        return None
    terminal = terminals[0]
    events = [terminal]
    if terminal.run_id is not None:
        gates = log.query_session(
            agent.id, run_id=terminal.run_id, before_session_seq=terminal.session_seq,
            types={"agent.completion_gate"}, limit=1,
        )
        events.extend(gates)
        # build_child_manifest resolves the runner's explicit result reference.
        # Conversation replies are committed before the gate, not re-emitted.
    events.sort(key=lambda event: event.session_seq)
    completion = completion_summary(events)
    if completion is None or completion["run_outcome"] != agent.state.value:
        return None
    manifest = build_child_manifest(core, agent, session_events=events)
    artifacts = []
    delivery = terminal.data.get("delivery") or {}
    if artifact_ids := delivery.get("artifact_ids"):
        registry = ArtifactService()
        for artifact_id in artifact_ids:
            artifact = registry.get(agent.project_id, artifact_id)
            if artifact is not None:
                artifacts.append({
                    "artifact_id": artifact.artifact_id,
                    "name": artifact.name,
                    "mime_type": artifact.mime_type,
                    "size": artifact.size,
                    "uri": f"cloudra://projects/{agent.project_id}/artifacts/{artifact.artifact_id}",
                })
    return {
        "status": "finished",
        "result": {
            "terminal_event_id": terminal.event_id,
            "run_outcome": completion["run_outcome"],
            "summary": manifest["final_summary"] if manifest["final_summary_source"] == "message" else None,
            "verification_label": completion["verification_label"],
            "completion_basis": completion["completion_basis"],
            "unresolved": list(dict.fromkeys([*manifest["unresolved"], *delivery.get("unresolved", [])])),
            "artifacts": artifacts,
        },
    }


async def _get_outcome(ctx: ApiContext, project_id: str, session_id: str) -> FinishedResult | None:
    core = ctx.core
    async with core.command_lock, core.event_writer._lock:
        core.require_project(project_id)
        agent = core.require_agent(session_id)
        if agent.project_id != project_id:
            raise CommandRejected("not_found", "Agent session not found in this project.")
        if agent.state not in _TERMINAL_STATES or agent.current_run is not None:
            return None
        log = core.event_log
        marks = log.durable_metadata()["sessions"] if core.store is not None else log.high_session_watermarks
        snapshot = agent.model_copy(deep=True)
    return await asyncio.to_thread(_outcome, core, snapshot, marks.get(session_id, 0))


async def _pending_result(ctx: ApiContext, project_id: str, session_id: str) -> PendingResult:
    from .progress import project_progress

    progress = await project_progress(ctx, project_id, include_process=False)
    agents = {item["session_id"]: item for item in progress["agents"]}
    if session_id not in agents:
        raise CommandRejected("not_found", "Agent session not found in this project.")
    children: dict[str | None, list[str]] = {}
    for item in agents.values():
        children.setdefault(item["parent_session_id"], []).append(item["session_id"])
    descendants = {session_id}
    stack = [session_id]
    while stack:
        for child in children.get(stack.pop(), ()):
            if child not in descendants:
                descendants.add(child)
                stack.append(child)
    return {
        "status": "pending",
        "agent": agents[session_id],
        "pending": [item for item in progress["pending"] if item["session_id"] in descendants],
    }


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v2/tasks", dependencies=ctx.protected, status_code=201)
    async def start_task(body: StartTask, request: Request) -> TaskRef:
        if body.workspace_dir is not None and (request.client is None or request.client.host not in LOOPBACK_CLIENTS):
            raise HTTPException(403, detail={
                "code": "forbidden", "message": "Only local connections can choose a workspace directory.",
            })
        return await _start_task(ctx, body)

    @router.get(
        "/api/v2/projects/{project_id}/agents/{session_id}/result",
        dependencies=ctx.protected,
    )
    async def get_result(
        project_id: str,
        session_id: str,
        wait_seconds: Annotated[int, Query(ge=0, le=MAX_RESULT_WAIT)] = 0,
    ) -> CurrentResult:
        hub = ctx.core.event_hub
        changed = asyncio.Event()

        async def on_event(event) -> None:
            if event.seq and event.project_id == project_id and event.type in _WAIT_EVENTS:
                changed.set()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds
        if wait_seconds:
            hub.subscribe(on_event)
        try:
            while True:
                changed.clear()
                if result := await _get_outcome(ctx, project_id, session_id):
                    return result
                pending = await _pending_result(ctx, project_id, session_id)
                remaining = deadline - loop.time()
                if remaining <= 0 or any(item["kind"] in {"question", "approval"} for item in pending["pending"]):
                    return pending
                try:
                    await asyncio.wait_for(changed.wait(), timeout=remaining)
                except TimeoutError:
                    # Re-read once after the deadline to avoid losing a
                    # terminal event published while the timeout was firing.
                    pass
        finally:
            if wait_seconds:
                hub.unsubscribe(on_event)

    return router
