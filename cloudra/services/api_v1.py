"""Version 1 remote-control API.

The v1 surface is intentionally small: the server remains authoritative for
Conversation, Session, and event state, while an Android client can disconnect
and resume from a persisted event cursor.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Awaitable, Callable, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from cloudra import __version__
from cloudra.dag.models import OrchestrationMode
from cloudra.persistence.database import ConversationDB
from cloudra.services import control_store
from cloudra.services.nodes import NodeRegistry, NodeRegistryError
from cloudra.services.service import validate_conversation_id

PROTOCOL_NAME = "cloudra-control"
PROTOCOL_VERSION = 1
TERMINAL_STATES = frozenset(
    {"completed", "failed", "cancelled", "killed", "interrupted"}
)

_EVENT_TYPE_MAP = {
    "queued": "session.created",
    "running": "session.state_changed",
    "cancel_requested": "session.state_changed",
    "completed": "session.state_changed",
    "failed": "session.state_changed",
    "cancelled": "session.state_changed",
    "killed": "session.state_changed",
    "interrupted": "session.state_changed",
    "llm_chunk": "session.output_delta",
    "llm_stream_end": "session.output_completed",
    "phase": "agent.phase_changed",
    "tool_started": "tool.started",
    "tool_finished": "tool.finished",
    "tool_failed": "tool.failed",
    "supervisor_review": "agent.supervisor_reviewed",
    "llm_request_diagnostics": "agent.request_diagnostics",
    "client_command_received": "command.received",
    "client_command_applied": "command.applied",
    "waiting_for_user": "session.state_changed",
    "waiting_for_approval": "session.state_changed",
    "waiting_for_device": "session.state_changed",
    "interaction_requested": "interaction.requested",
    "interaction_responded": "interaction.responded",
    "interaction_expired": "interaction.expired",
    "interaction_cancelled": "interaction.cancelled",
    "approval_pending": "approval.requested",
    "approval_decided": "approval.decided",
    "approval_expired": "approval.expired",
    "artifact_created": "artifact.created",
    "artifact_registration_failed": "artifact.registration_failed",
    "device_tool_state": "device.tool_state_changed",
}


class V1SessionCreate(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    workspace_id: str = Field(default="default", min_length=1, max_length=100)
    # Remote Phase 1 deliberately cannot silently enable automatic approval.
    yolo: bool = False
    orchestration_mode: OrchestrationMode = OrchestrationMode.STANDARD


class V1MessageAppend(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class V1InteractionResponse(BaseModel):
    response: str = Field(max_length=20_000)


class V1ApprovalDecision(BaseModel):
    decision: Literal["approved", "denied"]
    denial_reason: str = Field(default="", max_length=2_000)


class V1ArtifactTokenRequest(BaseModel):
    ttl_seconds: int = Field(default=300, ge=30, le=900)


class V1PairingStart(BaseModel):
    ttl_seconds: int = Field(default=300, ge=30, le=600)


class V1PairingComplete(BaseModel):
    pairing_id: str = Field(min_length=12, max_length=160)
    pairing_secret: str = Field(min_length=16, max_length=200)
    display_name: str = Field(default="Android Device", max_length=100)
    client_version: str = Field(default="unknown", max_length=100)
    capabilities: list[dict] = Field(default_factory=list, max_length=64)
    capability_revision: int = Field(default=1, ge=1)
    workspace_revision: int = Field(default=1, ge=0)
    config_revision: int = Field(default=1, ge=0)


class V1DeviceHello(BaseModel):
    display_name: str = Field(default="Android Device", max_length=100)
    client_version: str = Field(default="unknown", max_length=100)
    capabilities: list[dict] = Field(default_factory=list, max_length=64)
    capability_revision: int = Field(default=1, ge=1)
    workspace_revision: int = Field(default=1, ge=0)
    config_revision: int = Field(default=1, ge=0)


class V1DeviceHeartbeat(BaseModel):
    workspace_revision: int = Field(default=1, ge=0)
    config_revision: int = Field(default=1, ge=0)
    observations: list[dict] = Field(default_factory=list, max_length=64)


class V1DeviceLease(BaseModel):
    max_count: int = Field(default=4, ge=1, le=16)
    lease_seconds: int = Field(default=30, ge=10, le=60)


class V1DeviceLeaseAction(BaseModel):
    lease_id: str = Field(min_length=12, max_length=160)


class V1DeviceToolResult(BaseModel):
    status: Literal["succeeded", "failed", "declined", "cancelled"]
    result: dict = Field(default_factory=dict)
    error: str = Field(default="", max_length=2_000)


def _event_envelope(
    conversation_id: str,
    session_id: str,
    event: dict,
) -> dict:
    raw_type = str(event.get("event_type", "unknown"))
    data = event.get("data")
    if not isinstance(data, dict):
        data = {"value": data}
    else:
        data = dict(data)
    if raw_type in TERMINAL_STATES | {
        "queued",
        "running",
        "waiting_for_user",
        "waiting_for_approval",
        "waiting_for_device",
        "cancel_requested",
    }:
        data.setdefault("state", raw_type)
    cursor = int(event["id"])
    return {
        "protocol": PROTOCOL_NAME,
        "version": PROTOCOL_VERSION,
        "message_id": f"evt_{conversation_id}_{cursor}",
        "type": _EVENT_TYPE_MAP.get(raw_type, "session.event"),
        "timestamp": event.get("created_at")
        or datetime.now(timezone.utc).isoformat(),
        "trace_id": data.get("trace_id"),
        "cursor": cursor,
        "payload": {
            "conversation_id": conversation_id,
            "session_id": session_id,
            "event_type": raw_type,
            "data": data,
        },
    }


def _sse_message(envelope: dict) -> str:
    payload = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
    return (
        f"id: {envelope['cursor']}\n"
        f"event: {envelope['type']}\n"
        f"data: {payload}\n\n"
    )


def create_v1_router(
    service,
    authorize: Callable[[str | None], Awaitable[None]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    async def require_client(
        request: Request,
        authorization: str | None = Header(default=None),
        protocol_version: str = Header(
            default=str(PROTOCOL_VERSION),
            alias="X-Cloudra-Protocol-Version",
        ),
        client_version: str = Header(
            default="unknown",
            alias="X-Cloudra-Client-Version",
        ),
        node_id: str | None = Header(
            default=None,
            alias="X-Cloudra-Node-ID",
        ),
    ) -> None:
        await authorize(authorization)
        try:
            requested_version = int(protocol_version)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的 Cloudra 协议版本",
            ) from exc
        if requested_version != PROTOCOL_VERSION:
            raise HTTPException(
                status_code=status.HTTP_426_UPGRADE_REQUIRED,
                detail={
                    "message": "Cloudra 控制协议 major version 不兼容",
                    "supported_versions": [PROTOCOL_VERSION],
                },
                headers={"X-Cloudra-Protocol-Version": str(PROTOCOL_VERSION)},
            )
        try:
            registry = NodeRegistry.from_environment()
            selected_node = registry.node(node_id)
        except NodeRegistryError as exc:
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                    if node_id
                    else status.HTTP_503_SERVICE_UNAVAILABLE
                ),
                detail={
                    "message": "Cloudra 节点路由不可用",
                    "requested_node_id": (node_id or "")[:100],
                    "error": str(exc),
                },
            ) from exc
        request.state.cloudra_client_version = client_version[:100]
        request.state.cloudra_node_id = selected_node.node_id

    async def require_protocol(
        protocol_version: str = Header(
            default=str(PROTOCOL_VERSION),
            alias="X-Cloudra-Protocol-Version",
        ),
    ) -> None:
        try:
            requested_version = int(protocol_version)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的 Cloudra 协议版本",
            ) from exc
        if requested_version != PROTOCOL_VERSION:
            raise HTTPException(
                status_code=status.HTTP_426_UPGRADE_REQUIRED,
                detail={
                    "message": "Cloudra 控制协议 major version 不兼容",
                    "supported_versions": [PROTOCOL_VERSION],
                },
                headers={
                    "X-Cloudra-Protocol-Version": str(PROTOCOL_VERSION)
                },
            )

    async def require_device(
        request: Request,
        _protocol: None = Depends(require_protocol),
        authorization: str | None = Header(default=None),
    ) -> None:
        from cloudra.services.device_broker import DeviceAuthenticationError

        if not authorization or not authorization.startswith("Device "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少设备凭据",
                headers={"WWW-Authenticate": "Device"},
            )
        try:
            # DeviceBroker 是同步 sqlite3 实现，高频调用必须卸载出事件循环
            request.state.cloudra_device = await asyncio.to_thread(
                service.device_broker.authenticate,
                authorization.removeprefix("Device ").strip(),
            )
        except DeviceAuthenticationError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Device"},
            ) from exc

    protected = [Depends(require_client)]
    device_protected = [Depends(require_device)]

    @router.get("/profile", dependencies=protected)
    async def server_profile(request: Request) -> dict:
        return {
            "protocol": PROTOCOL_NAME,
            "protocol_version": PROTOCOL_VERSION,
            "server_version": __version__,
            "node_id": request.state.cloudra_node_id,
            "display_name": os.getenv("CLOUDRA_SERVER_NAME", "Cloudra Server"),
            "client_version": request.state.cloudra_client_version,
        }

    @router.get("/nodes", dependencies=protected)
    async def list_nodes() -> list[dict]:
        return NodeRegistry.from_environment().public_nodes()

    @router.get("/workspaces", dependencies=protected)
    async def list_workspaces() -> list[dict]:
        return NodeRegistry.from_environment().public_workspaces()

    @router.post("/pairing/start", dependencies=protected)
    async def start_pairing(body: V1PairingStart) -> dict:
        return await asyncio.to_thread(
            service.device_broker.start_pairing,
            ttl_seconds=body.ttl_seconds,
        )

    @router.post(
        "/pairing/complete",
        dependencies=[Depends(require_protocol)],
    )
    async def complete_pairing(body: V1PairingComplete) -> dict:
        from cloudra.services.device_broker import PairingError

        try:
            return await asyncio.to_thread(
                service.device_broker.complete_pairing,
                **body.model_dump(),
            )
        except PairingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/devices", dependencies=protected)
    async def list_devices() -> list[dict]:
        return await asyncio.to_thread(service.device_broker.list_devices)

    @router.delete("/devices/{device_id}", dependencies=protected)
    async def revoke_device(device_id: str) -> dict:
        try:
            revoked = await asyncio.to_thread(service.device_broker.revoke, device_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not revoked:
            raise HTTPException(status_code=404, detail="设备不存在或已撤销")
        return {"device_id": device_id, "state": "revoked"}

    def require_matching_device(request: Request, device_id: str) -> dict:
        device = request.state.cloudra_device
        if device["device_id"] != device_id:
            raise HTTPException(status_code=403, detail="设备身份不匹配")
        return device

    @router.post(
        "/devices/{device_id}/hello",
        dependencies=device_protected,
    )
    async def device_hello(
        device_id: str,
        body: V1DeviceHello,
        request: Request,
    ) -> dict:
        require_matching_device(request, device_id)
        try:
            return await asyncio.to_thread(
                service.device_broker.hello,
                device_id,
                **body.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/devices/{device_id}/heartbeat",
        dependencies=device_protected,
    )
    async def device_heartbeat(
        device_id: str,
        body: V1DeviceHeartbeat,
        request: Request,
    ) -> dict:
        require_matching_device(request, device_id)
        try:
            return await asyncio.to_thread(
                service.device_broker.heartbeat,
                device_id,
                **body.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/devices/{device_id}/tool-calls/lease",
        dependencies=device_protected,
    )
    async def lease_device_tool_calls(
        device_id: str,
        body: V1DeviceLease,
        request: Request,
    ) -> list[dict]:
        require_matching_device(request, device_id)
        return await asyncio.to_thread(
            service.device_broker.lease, device_id, **body.model_dump()
        )

    @router.post(
        "/devices/{device_id}/tool-calls/{tool_call_id}/ack",
        dependencies=device_protected,
    )
    async def acknowledge_device_tool_call(
        device_id: str,
        tool_call_id: str,
        body: V1DeviceLeaseAction,
        request: Request,
    ) -> dict:
        from cloudra.services.device_broker import DeviceInvocationError

        require_matching_device(request, device_id)
        try:
            return await asyncio.to_thread(
                service.device_broker.acknowledge,
                device_id,
                tool_call_id,
                body.lease_id,
            )
        except DeviceInvocationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        "/devices/{device_id}/tool-calls/{tool_call_id}/running",
        dependencies=device_protected,
    )
    async def start_device_tool_call(
        device_id: str,
        tool_call_id: str,
        body: V1DeviceLeaseAction,
        request: Request,
    ) -> dict:
        from cloudra.services.device_broker import DeviceInvocationError

        require_matching_device(request, device_id)
        try:
            return await asyncio.to_thread(
                service.device_broker.mark_running,
                device_id,
                tool_call_id,
                body.lease_id,
            )
        except DeviceInvocationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        (
            "/devices/{device_id}/tool-calls/{tool_call_id}/"
            "waiting-for-approval"
        ),
        dependencies=device_protected,
    )
    async def wait_for_local_device_approval(
        device_id: str,
        tool_call_id: str,
        body: V1DeviceLeaseAction,
        request: Request,
    ) -> dict:
        from cloudra.services.device_broker import DeviceInvocationError

        require_matching_device(request, device_id)
        try:
            return await asyncio.to_thread(
                service.device_broker.mark_waiting_for_local_approval,
                device_id,
                tool_call_id,
                body.lease_id,
            )
        except DeviceInvocationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        "/devices/{device_id}/tool-calls/{tool_call_id}/result",
        dependencies=device_protected,
    )
    async def finish_device_tool_call(
        device_id: str,
        tool_call_id: str,
        body: V1DeviceToolResult,
        request: Request,
    ) -> dict:
        from cloudra.services.device_broker import DeviceInvocationError

        require_matching_device(request, device_id)
        try:
            return await asyncio.to_thread(
                service.device_broker.finish,
                device_id,
                tool_call_id,
                **body.model_dump(),
            )
        except DeviceInvocationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get(
        "/device-tool-calls/{tool_call_id}",
        dependencies=protected,
    )
    async def get_device_tool_call(tool_call_id: str) -> dict:
        from cloudra.services.device_broker import DeviceInvocationError

        try:
            return await asyncio.to_thread(
                service.device_broker.get_invocation, tool_call_id
            )
        except DeviceInvocationError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post(
        "/conversations",
        status_code=status.HTTP_201_CREATED,
        dependencies=protected,
    )
    async def create_conversation() -> dict:
        conversation = await asyncio.to_thread(service.create_conversation)
        return {"id": conversation.id, "state": conversation.state}

    @router.get("/conversations", dependencies=protected)
    async def list_conversations() -> list[dict]:
        return await asyncio.to_thread(service.list_conversations)

    @router.get(
        "/conversations/{conversation_id}/messages",
        dependencies=protected,
    )
    async def get_conversation_messages(conversation_id: str) -> list[dict]:
        try:
            return await asyncio.to_thread(
                service.get_conversation_messages, conversation_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get(
        "/conversations/{conversation_id}/sessions",
        dependencies=protected,
    )
    async def list_sessions(conversation_id: str) -> list[dict]:
        try:
            records = await asyncio.to_thread(service.session_runner.list, conversation_id)
            return [record.to_dict() for record in records]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/conversations/{conversation_id}/sessions",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=protected,
    )
    async def create_session(
        request: Request,
        conversation_id: str,
        body: V1SessionCreate,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        try:
            workspace = NodeRegistry.from_environment().workspace(
                request.state.cloudra_node_id,
                body.workspace_id,
            )
        except NodeRegistryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if workspace.access != "read_write":
            raise HTTPException(
                status_code=403,
                detail="Workspace 是只读的，不能启动 Agent Session",
            )
        if body.yolo:
            raise HTTPException(
                status_code=422,
                detail="远程 Phase 1 不允许启用自动审批",
            )
        try:
            # 异步变体：DB 阶段在线程，执行任务调度留在 loop 线程（同步版
            # 经 to_thread 会炸 RuntimeError: no running event loop）。
            command, record = await service.submit_session_command_async(
                command_id=idempotency_key or control_store.new_command_id(),
                query=body.query,
                conversation_id=conversation_id,
                working_directory=str(workspace.path),
                node_id=workspace.node_id,
                workspace_id=workspace.workspace_id,
                orchestration_mode=body.orchestration_mode,
            )
        except control_store.CommandConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = record.to_dict()
        payload["command"] = command.to_dict()
        return payload

    @router.get("/sessions/{session_id}", dependencies=protected)
    async def get_session(
        session_id: str,
        conversation_id: str = Query(min_length=1, max_length=100),
    ) -> dict:
        try:
            record = await asyncio.to_thread(
                service.session_runner.get, conversation_id, session_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Session 不存在")
        return record.to_dict()

    @router.get("/sessions/{session_id}/children", dependencies=protected)
    async def list_session_children(
        session_id: str,
        conversation_id: str = Query(min_length=1, max_length=100),
    ) -> list[dict]:
        try:
            records = await asyncio.to_thread(
                service.session_runner.list_children, conversation_id, session_id
            )
            return [record.to_dict() for record in records]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/sessions/{session_id}/cancel", dependencies=protected)
    async def cancel_session(
        session_id: str,
        conversation_id: str = Query(min_length=1, max_length=100),
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        try:
            command, record = await service.cancel_session_command(
                command_id=idempotency_key or control_store.new_command_id(),
                conversation_id=conversation_id,
                session_id=session_id,
            )
        except control_store.CommandConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Session 不存在")
        payload = record.to_dict()
        payload["command"] = command.to_dict()
        return payload

    @router.post(
        "/sessions/{session_id}/messages",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=protected,
    )
    async def append_session_message(
        session_id: str,
        body: V1MessageAppend,
        conversation_id: str = Query(min_length=1, max_length=100),
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        try:
            command, record = await service.append_session_message_command(
                command_id=idempotency_key or control_store.new_command_id(),
                conversation_id=conversation_id,
                session_id=session_id,
                content=body.content,
            )
        except control_store.CommandConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            message = str(exc)
            code = 404 if message == "Session 不存在" else 422
            raise HTTPException(status_code=code, detail=message) from exc
        payload = record.to_dict()
        payload["command"] = command.to_dict()
        return payload

    @router.get("/commands/{command_id}", dependencies=protected)
    async def get_client_command(
        command_id: str,
        conversation_id: str = Query(min_length=1, max_length=100),
    ) -> dict:
        try:
            validate_conversation_id(conversation_id)
            command = await asyncio.to_thread(
                control_store.get_command,
                ConversationDB(conversation_id),
                command_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if command is None:
            raise HTTPException(status_code=404, detail="控制命令不存在")
        return command.to_dict()

    @router.get("/interactions", dependencies=protected)
    async def list_interactions(
        conversation_id: str = Query(min_length=1, max_length=100),
        session_id: str | None = Query(default=None, max_length=160),
    ) -> list[dict]:
        try:
            return await asyncio.to_thread(
                service.list_pending_interactions,
                conversation_id,
                session_id=session_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/interactions/{interaction_id}/response",
        dependencies=protected,
    )
    async def respond_interaction(
        interaction_id: str,
        body: V1InteractionResponse,
        conversation_id: str = Query(min_length=1, max_length=100),
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        try:
            command, interaction = await service.respond_interaction_command(
                command_id=idempotency_key or control_store.new_command_id(),
                conversation_id=conversation_id,
                interaction_id=interaction_id,
                response=body.response,
            )
        except control_store.CommandConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except control_store.InteractionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            message = str(exc)
            code = 404 if message == "Interaction 不存在" else 422
            raise HTTPException(status_code=code, detail=message) from exc
        payload = interaction.to_dict()
        payload["command"] = command.to_dict()
        return payload

    @router.get("/approvals", dependencies=protected)
    async def list_approvals(
        conversation_id: str = Query(min_length=1, max_length=100),
    ) -> list[dict]:
        try:
            async_reader = getattr(
                service, "alist_pending_approvals_for_conversation", None
            )
            if async_reader is not None:
                return await async_reader(conversation_id)
            return await asyncio.to_thread(
                service.list_pending_approvals_for_conversation,
                conversation_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/approvals/{approval_id}/decision",
        dependencies=protected,
    )
    async def decide_approval(
        approval_id: int,
        body: V1ApprovalDecision,
        conversation_id: str = Query(min_length=1, max_length=100),
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        try:
            command, approval = await service.decide_approval_command(
                command_id=idempotency_key or control_store.new_command_id(),
                conversation_id=conversation_id,
                approval_id=approval_id,
                decision=body.decision,
                denial_reason=body.denial_reason,
            )
        except control_store.CommandConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            message = str(exc)
            code = 404 if message == "Approval 不存在" else 422
            raise HTTPException(status_code=code, detail=message) from exc
        approval["command"] = command.to_dict()
        return approval

    @router.get("/artifacts", dependencies=protected)
    async def list_artifacts(
        conversation_id: str = Query(min_length=1, max_length=100),
        session_id: str | None = Query(default=None, max_length=160),
    ) -> list[dict]:
        try:
            validate_conversation_id(conversation_id)
            artifacts = await asyncio.to_thread(
                service.artifacts.list,
                conversation_id,
                session_id=session_id,
            )
            return [artifact.to_dict() for artifact in artifacts]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/artifacts/{artifact_id}", dependencies=protected)
    async def get_artifact(
        artifact_id: str,
        conversation_id: str = Query(min_length=1, max_length=100),
    ) -> dict:
        try:
            artifact = await asyncio.to_thread(
                service.artifacts.get, conversation_id, artifact_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact 不存在")
        return artifact.to_dict()

    @router.post(
        "/artifacts/{artifact_id}/download-token",
        dependencies=protected,
    )
    async def create_artifact_download_token(
        artifact_id: str,
        body: V1ArtifactTokenRequest,
        conversation_id: str = Query(min_length=1, max_length=100),
    ) -> dict:
        from cloudra.persistence.artifacts import ArtifactNotFound

        try:
            token, expires_at = await asyncio.to_thread(
                service.artifacts.issue_download_token,
                conversation_id,
                artifact_id,
                ttl_seconds=body.ttl_seconds,
            )
        except ArtifactNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "artifact_id": artifact_id,
            "download_token": token,
            "expires_at": expires_at,
            "download_url": (
                f"/api/v1/artifacts/{artifact_id}/download"
                f"?conversation_id={conversation_id}"
            ),
        }

    @router.get("/artifacts/{artifact_id}/download")
    async def download_artifact(
        artifact_id: str,
        conversation_id: str = Query(min_length=1, max_length=100),
        download_token: str = Header(alias="X-Cloudra-Download-Token"),
    ) -> FileResponse:
        from cloudra.persistence.artifacts import ArtifactDownloadDenied

        try:
            artifact, path = await asyncio.to_thread(
                service.artifacts.resolve_download,
                conversation_id,
                artifact_id,
                download_token,
            )
        except ArtifactDownloadDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return FileResponse(
            path,
            media_type=artifact.mime_type,
            filename=artifact.name,
        )

    @router.get(
        "/conversations/{conversation_id}/sessions/{session_id}/events",
        dependencies=protected,
    )
    async def get_events(
        conversation_id: str,
        session_id: str,
        after_cursor: int = Query(default=0, ge=0),
        limit: int = Query(default=500, ge=1, le=2_000),
    ) -> dict:
        try:
            validate_conversation_id(conversation_id)
            rows = await asyncio.to_thread(
                service.session_runner.events,
                conversation_id,
                session_id,
                after_cursor,
            )
            rows = rows[:limit]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        events = [
            _event_envelope(conversation_id, session_id, event)
            for event in rows
        ]
        next_cursor = events[-1]["cursor"] if events else after_cursor
        return {
            "protocol": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "events": events,
            "next_cursor": next_cursor,
        }

    @router.get(
        "/conversations/{conversation_id}/sessions/{session_id}/events/stream",
        dependencies=protected,
    )
    async def stream_events(
        request: Request,
        conversation_id: str,
        session_id: str,
        after_cursor: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        try:
            validate_conversation_id(conversation_id)
            # Fail early for malformed session IDs before response headers start.
            await asyncio.to_thread(
                service.session_runner.events,
                conversation_id,
                session_id,
                after_cursor,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        async def generate():
            cursor = after_cursor
            quiet_ticks = 0
            while True:
                if await request.is_disconnected():
                    return
                rows = await asyncio.to_thread(
                    service.session_runner.events,
                    conversation_id,
                    session_id,
                    cursor,
                )
                if rows:
                    quiet_ticks = 0
                    for event in rows:
                        envelope = _event_envelope(
                            conversation_id,
                            session_id,
                            event,
                        )
                        cursor = envelope["cursor"]
                        yield _sse_message(envelope)
                else:
                    quiet_ticks += 1

                record = await asyncio.to_thread(
                    service.session_runner.get,
                    conversation_id,
                    session_id,
                )
                if record is None:
                    yield _sse_message(
                        {
                            "protocol": PROTOCOL_NAME,
                            "version": PROTOCOL_VERSION,
                            "message_id": f"notice_{conversation_id}_{cursor}",
                            "type": "system.notice",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "trace_id": None,
                            "cursor": cursor,
                            "payload": {
                                "conversation_id": conversation_id,
                                "session_id": session_id,
                                "event_type": "session_missing",
                                "data": {"message": "Session 不存在"},
                            },
                        }
                    )
                    return
                if record.state in TERMINAL_STATES and not rows:
                    return
                if quiet_ticks >= 30:
                    quiet_ticks = 0
                    yield ": ping\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Cloudra-Protocol-Version": str(PROTOCOL_VERSION),
            },
        )

    return router
