"""Thin FastAPI v2 routing over RuntimeCore + CommandBus.

This module knows HTTP concerns only.  Every write is submitted as a Command;
handlers live in runtime_v2.commands.  No business logic is allowed here.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cloudra import __version__
from cloudra.runtime.compute_executor import ComputeBroker
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import (
    Command,
    CommandRejected,
    RuntimeSettingsPatch,
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
    images: Optional[list[str]] = None
    image_artifact_ids: Optional[list[Optional[str]]] = None


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


class DagReplanRequest(BaseModel):
    note: str = ""


class GoalSetRequest(BaseModel):
    objective: str = ""
    completion_criteria: str = ""
    current_focus: str = ""


class CompactRequest(BaseModel):
    keep_recent: int = Field(default=20, ge=1, le=500)


class ContextInjectRequest(BaseModel):
    kind: Literal["pin", "unpin", "push"] = "push"
    key: str = ""
    content: str = ""


class GlobalConfigFieldPatch(BaseModel):
    """Fields of one global LLM slot; ``key`` is write-only (empty clears)."""

    model: Optional[str] = None
    url: Optional[str] = None
    key: Optional[str] = None
    context_window: Optional[int] = Field(default=None, ge=1)
    timeout: Optional[int] = Field(default=None, ge=1)


class GlobalConfigPatch(BaseModel):
    slot: Literal["coordinator", "follower"]
    changes: GlobalConfigFieldPatch


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
            # llm.chunk deltas are transient hub-only events: no replay value,
            # and persisting them would flood the event table.
            if envelope.type == "llm.chunk":
                return
            await asyncio.to_thread(core.store.append_event, envelope)

        core.event_hub.subscribe(persist_event)
    bus = CommandBus(core)
    compute_broker = ComputeBroker()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await core.reminders.rearm_all()
        await core.email_listener.start()
        await compute_broker.start()
        try:
            yield
        finally:
            await compute_broker.close()
            await core.email_listener.close()
            await core.reminders.close()

    app = FastAPI(title="Cloudra API v2", version=__version__, lifespan=lifespan)
    app.state.runtime_core = core
    app.state.legacy_service = legacy_service
    app.state.compute_broker = compute_broker
    # Local SPA origins (browser dev/build servers) are
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

    @app.get("/api/v2/runtime/config", dependencies=protected)
    async def runtime_config() -> dict[str, Any]:
        """Global LLM config: the fallback behind empty per-agent settings."""
        from cloudra.infra.config import get_config

        cfg = get_config()

        def slot(role) -> dict[str, Any]:
            return {
                "model": role.model,
                "url": role.url,
                "key_set": bool(role.key),
                "context_window": role.context_window,
                "timeout": role.timeout,
            }

        return {
            "config_file": str(cfg.config_file),
            "coordinator": slot(cfg.coordinator),
            "follower": slot(cfg.follower),
        }

    @app.patch("/api/v2/runtime/config", dependencies=protected)
    async def patch_runtime_config(body: GlobalConfigPatch) -> dict[str, Any]:
        """Update one global LLM slot and persist it to the YAML config.

        The in-memory config singleton is what empty per-agent settings fall
        back to (adapters.legacy_default_settings), so the change is live on
        the next LLM request.  ``key=""`` clears the stored key; keys are
        write-only and never returned by the GET endpoint.
        """
        from cloudra.infra.config import get_config

        cfg = get_config()
        target = cfg.coordinator if body.slot == "coordinator" else cfg.follower
        for field, value in body.changes.model_dump(exclude_unset=True).items():
            setattr(target, field, value)
        await asyncio.to_thread(cfg.save)
        return await runtime_config()

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

    @app.get("/api/v2/projects/{project_id}/transcript", dependencies=protected)
    async def project_transcript(project_id: str) -> Response:
        """Full human-readable Markdown dump of the project's event stream.

        Every persisted event with its complete payload (messages, thinking,
        tool arguments/results, compaction and context-tree snapshots) — built
        for offline diagnosis and ablation analysis.
        """
        from cloudra.runtime_v2.transcript import render_project_transcript

        project = core.require_project(project_id)
        events = core.event_log.query_project(project_id, limit=1_000_000)
        text = render_project_transcript(project, core.agents, events)
        safe = "".join(
            ch if ch.isascii() and (ch.isalnum() or ch in "-_") else "-"
            for ch in (project.name or project.id)
        ).strip("-")[:60] or project.id
        return Response(
            content=text,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="cloudra-transcript-{safe}.md"'
            },
        )

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
            if event.type in {"agent.message_injected", "agent.message_emitted"}:
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
        before: Optional[int] = Query(default=None, ge=0),
        types: Optional[str] = Query(default=None),
        limit: int = Query(default=1000, ge=1, le=5000),
        tail: bool = Query(default=False),
    ) -> list[dict[str, Any]]:
        """Page through one session's events.

        ``tail=true`` returns the most recent ``limit`` events (optionally at
        or before the ``before`` session_seq cursor — used to page backwards
        from the newest end); ``tail=false`` pages forward from ``after``.
        """
        core.require_agent(session_id)
        wanted = [t.strip() for t in types.split(",") if t.strip()] if types else None
        events = core.event_log.query_session(
            session_id,
            after_session_seq=after,
            before_session_seq=before,
            types=wanted,
            limit=limit,
            tail=tail,
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

    @app.get("/api/v2/agents/{session_id}/goal", dependencies=protected)
    async def get_goal(session_id: str) -> dict[str, Any]:
        from cloudra.runtime_v2.policies.goal_stage import read_goal

        agent = core.require_agent(session_id)
        return {"goal": await asyncio.to_thread(read_goal, agent)}

    @app.post("/api/v2/agents/{session_id}/goal", dependencies=protected)
    async def set_goal(session_id: str, body: GoalSetRequest) -> dict[str, Any]:
        from cloudra.runtime_v2.policies.goal_stage import write_goal

        agent = core.require_agent(session_id)
        goal = body.model_dump()
        await asyncio.to_thread(write_goal, agent, goal)
        return {"goal": goal}

    @app.post("/api/v2/agents/{session_id}/compact", dependencies=protected)
    async def compact_agent(session_id: str, body: CompactRequest) -> CommandResponse:
        command = Command(
            type="agent.compact",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        return await execute(command)

    @app.post("/api/v2/agents/{session_id}/context/inject", dependencies=protected)
    async def inject_context(session_id: str, body: ContextInjectRequest) -> CommandResponse:
        """Lightweight context injection (pin/unpin/push a notice).

        The notice reaches the agent's next LLM turn as a system message and
        lands in the event log (context.pin_set / pin_cleared / injected) —
        auditable, replayable, no wakeup.  Use /messages when a wakeup is
        wanted.
        """
        command = Command(
            type="context.inject",
            target={"session_id": session_id},
            payload=_command_payload(body),
        )
        # Validate here (not only in the command handler) so an unknown agent
        # surfaces as 404 instead of an accepted=false 200.
        core.require_agent(session_id)
        return await execute(command)

    @app.get("/api/v2/agents/{session_id}/context", dependencies=protected)
    async def agent_context_stats(session_id: str) -> dict[str, Any]:
        """Read-only per-agent context usage, derived from the session events.

        ``tokens`` is an estimate over persisted event text; the exact current
        context size is ``last_prompt_tokens`` from the latest LLM call.
        """
        from cloudra.infra.token_estimator import TokenEstimator

        core.require_agent(session_id)
        by_role: dict[str, dict[str, int]] = {
            role: {"messages": 0, "tokens": 0} for role in ("user", "assistant", "tool")
        }
        last_prompt_tokens: int | None = None
        for event in core.event_log.query_session(session_id, limit=100000):
            if event.type in {"agent.message_injected", "agent.message_emitted"}:
                role = "user" if event.type == "agent.message_injected" else "assistant"
                text = str(event.data.get("content") or "")
            elif event.type == "tool.finished":
                role = "tool"
                text = str(event.data.get("result_summary") or "")
            elif event.type == "llm.completed":
                usage = event.data.get("usage") or {}
                if usage.get("prompt_tokens"):
                    last_prompt_tokens = int(usage["prompt_tokens"])
                continue
            else:
                continue
            by_role[role]["messages"] += 1
            by_role[role]["tokens"] += TokenEstimator.count_text(text)
        return {
            "session_id": session_id,
            "messages": sum(bucket["messages"] for bucket in by_role.values()),
            "tokens": sum(bucket["tokens"] for bucket in by_role.values()),
            "by_role": by_role,
            "last_prompt_tokens": last_prompt_tokens,
        }

    @app.get("/api/v2/skills", dependencies=protected)
    async def list_skills() -> list[dict[str, Any]]:
        from cloudra.base.skill_class import skill_loader

        return await asyncio.to_thread(skill_loader().skill_datas_get)

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

    # ---------------------------------------------------- DAG / artifact reads

    def _artifacts_service():
        from cloudra.infra.config import get_config
        from cloudra.persistence.artifacts import ArtifactService

        return ArtifactService(Path(get_config().data_dir))

    def _dag_read_context(project_id: str):
        """Existing DAG store+engine for a project, or None (never initializes)."""
        from cloudra.dag.engine import DagEngine
        from cloudra.dag.store import DagStore, GraphBundleNotFound
        from cloudra.persistence.database import ConversationDB

        core.require_project(project_id)
        db = ConversationDB(project_id)
        if not Path(db.path).is_file():
            return None
        db.migrate_if_needed()
        store = DagStore(db)
        try:
            store.load_bundle()
        except GraphBundleNotFound:
            return None
        return store, DagEngine(store)

    def _dag_controller(core: RuntimeCore, project_id: str):
        project = core.require_project(project_id)
        from cloudra.dag.controller import DagController
        from cloudra.persistence.database import ConversationDB

        if project.settings.orchestration_mode.value == "standard":
            return None
        db = ConversationDB(project_id)
        if Path(db.path).is_file():
            db.migrate_if_needed()
        else:
            db.init()
        return DagController(
            db,
            project_id,
            project.settings.orchestration_mode,
            conversation_id=project_id,
            working_directory=project.workspace_dir,
            core=core,
        )

    @app.get("/api/v2/projects/{project_id}/approvals", dependencies=protected)
    async def list_approvals(project_id: str) -> list[dict[str, Any]]:
        core.require_project(project_id)
        return core.pending.list_pending_approvals(project_id)

    @app.post("/api/v2/projects/{project_id}/approvals/{approval_id}/decision", dependencies=protected)
    async def decide_approval(
        project_id: str, approval_id: str, body: ApprovalDecision
    ) -> dict[str, Any]:
        result = await bus.execute(
            Command(
                type="approval.decide",
                target={"project_id": project_id},
                payload={
                    "approval_id": approval_id,
                    "decision": "approved" if body.decision == "approve" else "denied",
                    "reason": body.reason,
                },
            )
        )
        if not result.accepted:
            error = (result.data or {}).get("error", {})
            http_code = 404 if error.get("code") == "not_found" else 400
            raise HTTPException(status_code=http_code, detail=error.get("message", "decision rejected"))
        return {"accepted": True}

    @app.get("/api/v2/projects/{project_id}/interactions", dependencies=protected)
    async def list_interactions(
        project_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        core.require_project(project_id)
        rows = core.pending.list_pending_interactions(project_id)
        if session_id is not None:
            rows = [row for row in rows if row["session_id"] == session_id]
        return rows

    @app.post("/api/v2/projects/{project_id}/interactions/{interaction_id}/response", dependencies=protected)
    async def respond_interaction(
        project_id: str,
        interaction_id: str,
        body: InteractionResponse,
    ) -> dict[str, Any]:
        result = await bus.execute(
            Command(
                type="interaction.respond",
                target={"project_id": project_id},
                payload={"interaction_id": interaction_id, "response": body.response},
            )
        )
        if not result.accepted:
            error = (result.data or {}).get("error", {})
            http_code = 404 if error.get("code") == "not_found" else 400
            raise HTTPException(status_code=http_code, detail=error.get("message", "response rejected"))
        return result.data

    @app.get("/api/v2/projects/{project_id}/artifacts", dependencies=protected)
    async def list_artifacts(
        project_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        core.require_project(project_id)
        artifacts = await asyncio.to_thread(
            _artifacts_service().list, project_id, session_id=session_id
        )
        return [artifact.to_dict() for artifact in artifacts]

    _UPLOAD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
    _UPLOAD_MAX_BYTES = 20 * 1024 * 1024

    @app.post("/api/v2/projects/{project_id}/uploads", dependencies=protected, status_code=status.HTTP_201_CREATED)
    async def upload_project_image(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        """User image upload: stored under the project workspace and registered as an artifact.

        The returned ``path`` is what ``agent.message`` accepts in ``images``;
        ``artifact_id`` lets the frontend render the bubble from storage.
        """
        from cloudra.persistence.fs_utils import atomic_write_bytes
        from cloudra.runtime_v2.turn_pipeline import register_workspace_image_artifact

        project = core.require_project(project_id)
        filename = Path(file.filename or "").name
        ext = Path(filename).suffix.lower()
        if ext not in _UPLOAD_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported image type {ext or '(none)'}; allowed: png, jpg, jpeg, webp",
            )
        data = await file.read()
        if not data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty upload")
        if len(data) > _UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail="upload exceeds the 20MB limit",
            )
        if project.workspace_dir:
            root = Path(project.workspace_dir)
            upload_dir = root / ".cloudra" / "uploads"
        else:
            # No workspace configured: fall back to the data dir so the
            # artifact boundary check still has a root to confine to.
            from cloudra.infra.config import get_config

            upload_dir = Path(get_config().data_dir) / "uploads" / project_id
            root = upload_dir
        path = upload_dir / f"{uuid.uuid4().hex[:12]}-{filename}"

        def write() -> None:
            upload_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(str(path), data)

        await asyncio.to_thread(write)
        artifact_id = await asyncio.to_thread(
            lambda: register_workspace_image_artifact(
                project_id=project_id,
                session_id="uploads",
                agent_id=None,
                workspace_root=str(root),
                image_path=str(path),
            )
        )
        return {"path": str(path), "artifact_id": artifact_id}

    @app.get("/api/v2/artifacts/{artifact_id}/download", dependencies=protected)
    async def download_artifact(artifact_id: str, project_id: str) -> StreamingResponse:
        from fastapi.responses import FileResponse

        artifacts = _artifacts_service()
        token, _ = await asyncio.to_thread(
            artifacts.issue_download_token, project_id, artifact_id
        )
        artifact, source = await asyncio.to_thread(
            artifacts.resolve_download, project_id, artifact_id, token
        )
        return FileResponse(source, filename=artifact.name)

    @app.get("/api/v2/projects/{project_id}/dag/process", dependencies=protected)
    async def dag_process(project_id: str) -> dict[str, Any]:
        # Phase 4：process 图已删除。路由保留一个版本，一律 410。
        raise HTTPException(
            status_code=410,
            detail="the process graph was removed (delivery-only orchestration); use /dag/delivery",
        )

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

    @app.get("/api/v2/projects/{project_id}/dag/projection", dependencies=protected)
    async def dag_projection(project_id: str) -> dict[str, Any] | None:
        from cloudra.dag.completion import build_projection

        context = await asyncio.to_thread(_dag_read_context, project_id)
        if context is None:
            return None
        store, engine = context
        mode = core.require_project(project_id).settings.orchestration_mode
        reviews = await asyncio.to_thread(store.list_call_reviews)
        pending = [
            {
                "review_id": row.review_id,
                "tool_name": row.tool_name,
                "is_success": row.is_success,
                "caller": row.caller_legacy_id or row.caller_role_id,
                "compute_job_id": row.compute_job_id,
                "result_summary": row.result_summary,
                "created_at": row.created_at,
            }
            for row in reviews
        ]
        projection = await asyncio.to_thread(
            build_projection,
            engine.snapshot(),
            mode=mode,
            contract=store.load_coverage_contract(),
            history=engine.history(limit=8),
            pending_reviews=pending,
        )
        return projection.model_dump(mode="json")

    @app.get("/api/v2/projects/{project_id}/dag/reviews", dependencies=protected)
    async def dag_reviews(project_id: str) -> dict[str, Any] | None:
        """CallReview 收件箱：pending 全量 + 最近已裁决/忽略（只读投影）。"""
        context = await asyncio.to_thread(_dag_read_context, project_id)
        if context is None:
            return None
        store, _engine = context
        pending = await asyncio.to_thread(store.list_call_reviews, "pending")
        everything = await asyncio.to_thread(store.list_call_reviews, None)

        def _row(review) -> dict[str, Any]:
            return {
                "review_id": review.review_id,
                "tool_name": review.tool_name,
                "is_success": review.is_success,
                "caller_session_id": review.caller_session_id,
                "caller_role_id": review.caller_role_id,
                "caller_legacy_id": review.caller_legacy_id,
                "arguments_digest": review.arguments_digest,
                "result_summary": review.result_summary,
                "compute_job_id": review.compute_job_id,
                "suggested_target_id": review.suggested_target_id,
                "state": review.state,
                "created_at": review.created_at,
            }

        return {
            "pending": [_row(review) for review in pending],
            "recent": [_row(review) for review in everything if review.state != "pending"][-20:],
        }

    @app.get("/api/v2/projects/{project_id}/dag/draft", dependencies=protected)
    async def dag_draft(project_id: str) -> dict[str, Any] | None:
        """当前机理草稿 + mechanism_accepted（D4：EXISTS accepted draft）。"""
        context = await asyncio.to_thread(_dag_read_context, project_id)
        if context is None:
            return None
        store, _engine = context
        draft = await asyncio.to_thread(store.latest_draft)
        accepted = await asyncio.to_thread(store.has_accepted_draft)
        return {"mechanism_accepted": accepted, "draft": draft}

    @app.post("/api/v2/projects/{project_id}/dag/replan", dependencies=protected)
    async def dag_replan(project_id: str, body: DagReplanRequest) -> dict[str, Any]:
        from cloudra.core.supervisor import GraphSupervisor
        from cloudra.dag.controller import DagController
        from cloudra.dag.models import OrchestrationMode
        from cloudra.persistence.database import ConversationDB

        context = await asyncio.to_thread(_dag_read_context, project_id)
        if context is None:
            raise HTTPException(status_code=404, detail="DAG bundle not initialized")
        mode = core.require_project(project_id).settings.orchestration_mode
        if mode is not OrchestrationMode.DAG_GUIDED:
            raise HTTPException(
                status_code=422,
                detail=f"replan is only available in dag_guided mode (current: {mode.value})",
            )

        def _controller() -> DagController:
            db = ConversationDB(project_id)
            db.migrate_if_needed()
            controller = DagController(
                db,
                "user_replan",
                mode,
                conversation_id=project_id,
                supervisor=GraphSupervisor(conversation_id=project_id),
                core=core,
            )
            controller.contract = controller.store.load_coverage_contract()
            controller._initialized = True
            return controller

        controller = await asyncio.to_thread(_controller)
        result = await controller.maybe_supervise("user_replan", coordinator_request=body.note or None)
        if result is None:
            return {
                "trigger": "user_replan",
                "supervised": False,
                "summary": "Supervisor 未产出结果（运行失败或未触发，详见日志）",
            }
        accepted = sum(1 for m in result.mutations if m.get("accepted"))
        summary = f"rounds={result.rounds} mutations={accepted}/{len(result.mutations)}"
        if result.note:
            summary += f" note={result.note}"
        return {
            "trigger": result.trigger,
            "supervised": True,
            "rounds": result.rounds,
            "mutations_accepted": accepted,
            "mutations_total": len(result.mutations),
            "note": result.note,
            "summary": summary,
        }

    @app.post("/api/v2/projects/{project_id}/dag/mutations", dependencies=protected)
    async def dag_mutations(project_id: str, body: DagMutationRequest) -> dict[str, Any]:
        from cloudra.dag.models import GraphActor, MutationBatch, parse_graph_operation

        context = await asyncio.to_thread(_dag_read_context, project_id)
        if context is None:
            raise HTTPException(status_code=404, detail="DAG bundle not initialized")
        _store, engine = context
        batch = MutationBatch(
            session_id="user",
            actor=GraphActor.USER,
            actor_id="user",
            base_revisions=body.base_revisions,
            operations=[parse_graph_operation(op) for op in body.operations],
            rationale=body.rationale,
        )
        result = await asyncio.to_thread(engine.apply_batch, batch)
        return result.model_dump(mode="json")

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
                async for chunk in _sse_replay(core, project, cursor):
                    yield chunk
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
    from cloudra.runtime_v2.plugins import attach_plugins, load_plugins_from_config
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    # 通用插件面（GraphRAG 图书馆、事件观察者等，plugins 配置声明）：
    # 加载即注册，attach 把 on_event 挂进事件总线、setup 拿到 core。
    # 失败只记日志。无自演化——核心不回写，插件自维护存储。
    load_plugins_from_config()

    core = RuntimeCore(strict_events=True)
    core.runtime_defaults = legacy_default_runtime_settings()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=LegacyLLMProvider(),
        tools=LegacyToolExecutor(core),
        prompt_provider=LegacyPromptProvider(),
        event_hub=core.event_hub,
        notices=core.notices,
    )
    app = create_v2_app(core, pipeline=pipeline, store_path=store_path)
    # Attach after the hub/store exist: setup(core) hooks get a fully wired
    # core, on_event hooks start receiving from this point (backfill events
    # from restore are intentionally not replayed to plugins).
    attach_plugins(core)
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


async def _sse_replay(core, project, cursor: int):
    """回放历史事件并以 project.synced 边界标记收尾（前端据此抑制历史事件
    触发的提示）。抽成模块级 helper 是为了可测：httpx ASGITransport 缓冲整个
    响应，无限 SSE 流无法经它断言，测试直接驱动这个生成器。"""
    from cloudra.runtime_v2.schemas import EventEnvelope

    replayed_through = cursor
    for event in core.event_log.query_project(project.id, after_seq=cursor):
        replayed_through = max(replayed_through, event.seq)
        yield _sse(event)
    # seq=0 不影响客户端 cursor
    yield _sse(
        EventEnvelope(
            stream="project",
            project_id=project.id,
            seq=0,
            type="project.synced",
            data={"replayed_through": replayed_through},
        )
    )
