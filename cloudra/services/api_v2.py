"""Thin FastAPI v2 routing over RuntimeCore + CommandBus.

This module knows HTTP concerns only.  Every write is submitted as a Command;
handlers live in runtime_v2.commands.  No business logic is allowed here.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cloudra import __version__
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import (
    Command,
    CommandRejected,
    RuntimeSettingsPatch,
    new_id,
)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    workspace_dir: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    workspace_dir: Optional[str] = None
    archived: Optional[bool] = None
    settings: Optional[dict[str, Any]] = None


class AgentSpawn(BaseModel):
    role_id: str
    parent_session_id: Optional[str] = None
    display_name: Optional[str] = None
    query: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)


class MessagePost(BaseModel):
    content: str = Field(min_length=1)


class CancelPost(BaseModel):
    message: Optional[str] = None


class RestartPost(BaseModel):
    message: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)


class RolePatch(BaseModel):
    permissions: Optional[dict[str, bool]] = None
    tool_policy: Optional[dict[str, Any]] = None
    can_spawn: Optional[bool] = None
    spawn_roles: Optional[list[str]] = None
    default_settings: Optional[dict[str, Any]] = None


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "deny"]
    reason: str = ""


class InteractionResponse(BaseModel):
    response: str = Field(min_length=1)


class DagMutationRequest(BaseModel):
    operations: list[dict[str, Any]]
    base_revisions: dict[str, int] = Field(default_factory=dict)
    rationale: str = ""


class CommandResponse(BaseModel):
    command_id: str
    accepted: bool
    event_id: str
    data: Any = None


def _command_payload(body: BaseModel) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)


def create_v2_app(
    core: RuntimeCore | None = None,
    pipeline: Any = None,
    store_path: str | None = None,
    legacy_service: Any = None,
) -> FastAPI:
    core = core or RuntimeCore()
    if pipeline is not None:
        from cloudra.runtime_v2.agent_runner import AgentRunner

        core.runner = AgentRunner(core, pipeline)
    if store_path is not None:
        from cloudra.runtime_v2.persistence import RuntimeStore

        core.store = RuntimeStore(store_path)

        async def persist_event(envelope) -> None:
            await asyncio.to_thread(core.store.append_event, envelope)

        core.event_hub.subscribe(persist_event)
    bus = CommandBus(core)

    app = FastAPI(title="Cloudra API v2", version=__version__)
    app.state.runtime_core = core
    app.state.legacy_service = legacy_service
    # Local SPA origins (Electron file:// and browser dev/build servers) are
    # cross-origin to this runtime.  No credentials are allowed, so wildcard
    # CORS is safe for the local single-user trust model.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_token = os.getenv("CLOUDRA_API_TOKEN", "").strip()

    async def authorize(authorization: Optional[str] = Header(default=None)) -> None:
        if not api_token:
            return
        if authorization != f"Bearer {api_token}":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    protected = [Depends(authorize)]

    @app.exception_handler(CommandRejected)
    async def handle_command_rejected(request: Request, exc: CommandRejected) -> JSONResponse:
        http_code = {
            "not_found": status.HTTP_404_NOT_FOUND,
            "state_conflict": status.HTTP_409_CONFLICT,
        }.get(exc.code, status.HTTP_400_BAD_REQUEST)
        return JSONResponse(
            status_code=http_code,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )

    async def execute(command: Command) -> CommandResponse:
        try:
            result = await bus.execute(command)
        except CommandRejected as exc:
            http_code = {
                "not_found": status.HTTP_404_NOT_FOUND,
                "state_conflict": status.HTTP_409_CONFLICT,
            }.get(exc.code, status.HTTP_400_BAD_REQUEST)
            raise HTTPException(
                status_code=http_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        return CommandResponse(
            command_id=result.command_id,
            accepted=result.accepted,
            event_id=result.event_id,
            data=result.data,
        )

    # ------------------------------------------------------------------ runtime

    @app.get("/api/v2/runtime/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v2/runtime/capabilities", dependencies=protected)
    async def runtime_capabilities() -> dict[str, Any]:
        roles = [role.model_dump(mode="json") for role in core.roles.list()]
        return {
            "version": __version__,
            "roles": roles,
            "platform": "desktop",
            "strict_events": core.event_log.strict,
        }

    @app.get("/api/v2/runtime/settings", dependencies=protected)
    async def runtime_settings() -> dict[str, Any]:
        return core.runtime_defaults.model_dump(mode="json")

    @app.patch("/api/v2/runtime/settings", dependencies=protected)
    async def patch_runtime_settings(patch: RuntimeSettingsPatch) -> CommandResponse:
        command = Command(type="runtime.settings_update", payload=patch.model_dump(exclude_unset=True))
        return await execute(command)

    # ----------------------------------------------------------------- projects

    @app.get("/api/v2/projects", dependencies=protected)
    async def list_projects(include_archived: bool = False) -> list[dict[str, Any]]:
        projects = core.projects.values()
        if not include_archived:
            projects = [p for p in projects if not p.archived]
        return [p.model_dump(mode="json") for p in projects]

    @app.post("/api/v2/projects", dependencies=protected, status_code=status.HTTP_201_CREATED)
    async def create_project(body: ProjectCreate) -> CommandResponse:
        command = Command(type="project.create", payload=_command_payload(body))
        return await execute(command)

    @app.get("/api/v2/projects/{project_id}", dependencies=protected)
    async def get_project(project_id: str) -> dict[str, Any]:
        return core.require_project(project_id).model_dump(mode="json")

    @app.patch("/api/v2/projects/{project_id}", dependencies=protected)
    async def patch_project(project_id: str, body: ProjectPatch) -> CommandResponse:
        command = Command(
            type="project.update",
            target={"project_id": project_id},
            payload=_command_payload(body),
        )
        return await execute(command)

    @app.delete("/api/v2/projects/{project_id}", dependencies=protected)
    async def archive_project(project_id: str) -> CommandResponse:
        command = Command(
            type="project.update",
            target={"project_id": project_id},
            payload={"archived": True},
        )
        return await execute(command)

    @app.get("/api/v2/projects/{project_id}/workspace", dependencies=protected)
    async def project_workspace(project_id: str) -> dict[str, Any]:
        project = core.require_project(project_id)
        return {"workspace_dir": project.workspace_dir, "valid": bool(project.workspace_dir)}

    @app.get("/api/v2/projects/{project_id}/agents", dependencies=protected)
    async def list_agents(project_id: str) -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in core.list_project_agents(project_id)]

    @app.post("/api/v2/projects/{project_id}/agents", dependencies=protected, status_code=status.HTTP_201_CREATED)
    async def spawn_agent(project_id: str, body: AgentSpawn) -> CommandResponse:
        command = Command(
            type="agent.spawn",
            target={"project_id": project_id},
            payload=_command_payload(body),
        )
        return await execute(command)

    # ------------------------------------------------------------------- agents

    @app.get("/api/v2/agents/{session_id}", dependencies=protected)
    async def get_agent(session_id: str) -> dict[str, Any]:
        agent = core.require_agent(session_id)
        data = agent.model_dump(mode="json")
        data["children"] = [
            child.id for child in core.agents.values() if child.parent_session_id == session_id
        ]
        return data

    @app.get("/api/v2/agents/{session_id}/transcript", dependencies=protected)
    async def agent_transcript(session_id: str) -> dict[str, Any]:
        agent = core.require_agent(session_id)
        messages = []
        for event in core.event_log.query_session(session_id):
            if event.type == "agent.message_injected":
                data = event.data
                messages.append(
                    {
                        "message_id": data.get("message_id"),
                        "sender": data.get("sender"),
                        "content": data.get("content"),
                        "event_id": event.event_id,
                        "created_at": event.created_at.isoformat(),
                    }
                )
        return {"session_id": session_id, "agent_id": agent.role_id, "messages": messages}

    @app.get("/api/v2/agents/{session_id}/events", dependencies=protected)
    async def agent_events(
        session_id: str,
        after: int = 0,
        types: Optional[str] = Query(default=None),
        limit: int = Query(default=500, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        core.require_agent(session_id)
        wanted = [t.strip() for t in types.split(",") if t.strip()] if types else None
        events = core.event_log.query_session(
            session_id, after_session_seq=after, types=wanted, limit=limit
        )
        return [event.model_dump(mode="json") for event in events]

    @app.get("/api/v2/agents/{session_id}/events/{event_id}", dependencies=protected)
    async def agent_event_detail(session_id: str, event_id: str) -> dict[str, Any]:
        core.require_agent(session_id)
        event = core.event_log.get(event_id)
        if event is None or event.session_id != session_id:
            raise HTTPException(status_code=404, detail="event not found")
        return event.model_dump(mode="json")

    @app.post("/api/v2/agents/{session_id}/messages", dependencies=protected)
    async def inject_message(session_id: str, body: MessagePost) -> CommandResponse:
        command = Command(
            type="agent.message",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        return await execute(command)

    @app.post("/api/v2/agents/{session_id}/cancel", dependencies=protected)
    async def cancel_agent(session_id: str, body: CancelPost) -> CommandResponse:
        command = Command(
            type="agent.cancel",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        return await execute(command)

    @app.post("/api/v2/agents/{session_id}/restart", dependencies=protected)
    async def restart_agent(session_id: str, body: RestartPost) -> CommandResponse:
        command = Command(
            type="agent.restart",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        return await execute(command)

    @app.patch("/api/v2/agents/{session_id}/settings", dependencies=protected)
    async def patch_agent_settings(session_id: str, patch: RuntimeSettingsPatch) -> CommandResponse:
        command = Command(
            type="agent.settings_update",
            target={"session_id": session_id},
            payload=patch.model_dump(exclude_unset=True),
        )
        return await execute(command)

    # -------------------------------------------------------------------- roles

    @app.get("/api/v2/roles", dependencies=protected)
    async def list_roles() -> list[dict[str, Any]]:
        return [role.model_dump(mode="json") for role in core.roles.list()]

    @app.get("/api/v2/roles/{role_id}", dependencies=protected)
    async def get_role(role_id: str) -> dict[str, Any]:
        return core.roles.require(role_id).model_dump(mode="json")

    @app.patch("/api/v2/roles/{role_id}", dependencies=protected)
    async def patch_role(role_id: str, body: RolePatch) -> CommandResponse:
        command = Command(
            type="role.update",
            target={"role_id": role_id, "project_id": "runtime"},
            payload=_command_payload(body),
        )
        return await execute(command)

    # ------------------------------------------------ legacy control surface

    def _service(request: Request):
        service = request.app.state.legacy_service
        if service is None:
            from cloudra.services.service import CloudraService

            service = CloudraService()
            request.app.state.legacy_service = service
        return service

    def _dag_controller(core: RuntimeCore, project_id: str):
        project = core.require_project(project_id)
        from cloudra.dag.controller import DagController
        from cloudra.persistence.database import ConversationDB

        if project.settings.orchestration_mode.value == "standard":
            return None
        db = ConversationDB(project_id).init()
        return DagController(
            db,
            project_id,
            project.settings.orchestration_mode,
            conversation_id=project_id,
            working_directory=project.workspace_dir,
        )

    @app.get("/api/v2/projects/{project_id}/approvals", dependencies=protected)
    async def list_approvals(project_id: str, request: Request) -> list[dict[str, Any]]:
        return await _service(request).alist_pending_approvals_for_conversation(project_id)

    @app.post("/api/v2/projects/{project_id}/approvals/{approval_id}/decision", dependencies=protected)
    async def decide_approval(
        project_id: str, approval_id: int, body: ApprovalDecision, request: Request
    ) -> dict[str, Any]:
        decision = "approved" if body.decision == "approve" else "denied"
        accepted = await _service(request).decide_approval(
            project_id, approval_id, decision, body.reason
        )
        if not accepted:
            raise HTTPException(status_code=404, detail="approval not found")
        return {"accepted": True}

    @app.get("/api/v2/projects/{project_id}/interactions", dependencies=protected)
    async def list_interactions(
        project_id: str, request: Request, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            _service(request).list_pending_interactions,
            project_id,
            session_id=session_id,
        )

    @app.post("/api/v2/projects/{project_id}/interactions/{interaction_id}/response", dependencies=protected)
    async def respond_interaction(
        project_id: str,
        interaction_id: str,
        body: InteractionResponse,
        request: Request,
    ) -> dict[str, Any]:
        _, latest = await _service(request).respond_interaction_command(
            command_id=new_id("cmd"),
            conversation_id=project_id,
            interaction_id=interaction_id,
            response=body.response,
        )
        return latest.to_dict()

    @app.get("/api/v2/projects/{project_id}/artifacts", dependencies=protected)
    async def list_artifacts(
        project_id: str, request: Request, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        service = _service(request)
        artifacts = await asyncio.to_thread(
            service.artifacts.list, project_id, session_id=session_id
        )
        return [artifact.to_dict() for artifact in artifacts]

    @app.get("/api/v2/artifacts/{artifact_id}/download", dependencies=protected)
    async def download_artifact(
        artifact_id: str, project_id: str, request: Request
    ) -> StreamingResponse:
        from fastapi.responses import FileResponse

        service = _service(request)
        token, _ = await asyncio.to_thread(
            service.artifacts.issue_download_token, project_id, artifact_id
        )
        artifact, source = await asyncio.to_thread(
            service.artifacts.resolve_download, project_id, artifact_id, token
        )
        return FileResponse(source, filename=artifact.name)

    @app.get("/api/v2/projects/{project_id}/dag/process", dependencies=protected)
    async def dag_process(project_id: str) -> dict[str, Any]:
        controller = await asyncio.to_thread(_dag_controller, core, project_id)
        if controller is None:
            return {"mode": "standard", "graph": None}
        await controller.initialize()
        snapshot = await asyncio.to_thread(controller.engine.snapshot)
        return {"mode": controller.mode.value, "graph": snapshot.process.model_dump(mode="json")}

    @app.get("/api/v2/projects/{project_id}/dag/delivery", dependencies=protected)
    async def dag_delivery(project_id: str) -> dict[str, Any]:
        controller = await asyncio.to_thread(_dag_controller, core, project_id)
        if controller is None:
            return {"mode": "standard", "graph": None}
        await controller.initialize()
        snapshot = await asyncio.to_thread(controller.engine.snapshot)
        return {"mode": controller.mode.value, "graph": snapshot.delivery.model_dump(mode="json")}

    @app.get("/api/v2/projects/{project_id}/dag/report", dependencies=protected)
    async def dag_report(project_id: str) -> dict[str, Any] | None:
        controller = await asyncio.to_thread(_dag_controller, core, project_id)
        if controller is None:
            return None
        await controller.initialize()
        report = await asyncio.to_thread(controller.delivery_report)
        return report.model_dump(mode="json") if report is not None else None

    @app.get("/api/v2/projects/{project_id}/dag/history", dependencies=protected)
    async def dag_history(project_id: str) -> list[dict[str, Any]]:
        controller = await asyncio.to_thread(_dag_controller, core, project_id)
        if controller is None:
            return []
        return await asyncio.to_thread(controller.engine.history, limit=100)

    @app.post("/api/v2/projects/{project_id}/dag/mutations", dependencies=protected)
    async def dag_mutations(project_id: str, body: DagMutationRequest, request: Request) -> dict[str, Any]:
        result = await asyncio.to_thread(
            _service(request).dag_apply_user_mutation,
            project_id,
            body.operations,
            body.base_revisions,
            body.rationale,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="DAG bundle not initialized")
        return result

    # ---------------------------------------------------------------------- SSE

    @app.get("/api/v2/projects/{project_id}/stream", dependencies=protected)
    async def project_stream(project_id: str, request: Request, cursor: int = 0) -> StreamingResponse:
        project = core.require_project(project_id)
        queue: asyncio.Queue = asyncio.Queue()

        async def forward(event) -> None:
            if event.project_id == project.id:
                await queue.put(event)

        handler = core.event_hub.subscribe(forward)

        async def generate():
            try:
                for event in core.event_log.query_project(project.id, after_seq=cursor):
                    yield _sse(event)
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield _sse(event)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                    if await request.is_disconnected():
                        break
            finally:
                core.event_hub.unsubscribe(handler)

        return StreamingResponse(generate(), media_type="text/event-stream")

    return app


def create_default_v2_app(*, store_path: str | None = None) -> FastAPI:
    """Production wiring: legacy LLM/tool bridges + policy stages + durability."""
    store_path = store_path or os.environ.get("CLOUDRA_RUNTIME_STORE") or None
    from cloudra.runtime_v2.adapters import (
        LegacyLLMProvider,
        LegacyPromptProvider,
        LegacyToolExecutor,
        legacy_default_runtime_settings,
    )
    from cloudra.runtime_v2.persistence import restore_core
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    core = RuntimeCore(strict_events=True)
    core.runtime_defaults = legacy_default_runtime_settings()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=LegacyLLMProvider(),
        tools=LegacyToolExecutor(core),
        prompt_provider=LegacyPromptProvider(),
    )
    app = create_v2_app(core, pipeline=pipeline, store_path=store_path)
    if core.store is not None:
        restore_core(core, core.store)
    # Optional single-port browser mode: serve the built SPA from the same
    # uvicorn process.  Static mount is added last so /api/* routes win.
    serve_dir = os.environ.get("CLOUDRA_FRONTEND_SERVE_DIR", "").strip()
    if serve_dir and Path(serve_dir, "index.html").is_file():
        app.mount("/", StaticFiles(directory=serve_dir, html=True), name="frontend")
    return app


def _sse(event) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
