"""UI backend boundary for local desktop and remote Android operation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Protocol, runtime_checkable
from urllib.parse import urlsplit

import httpx

from cloudra import __version__

PROTOCOL_VERSION = 1
TERMINAL_STATES = frozenset(
    {"completed", "failed", "cancelled", "killed", "interrupted"}
)


class BackendError(RuntimeError):
    """Base error safe to display in the client UI."""


class BackendUnavailable(BackendError):
    pass


class BackendAuthenticationError(BackendError):
    pass


class BackendProtocolError(BackendError):
    pass


@dataclass(frozen=True)
class BackendEvent:
    cursor: int
    event_type: str
    data: dict
    created_at: str | None = None
    envelope_type: str = "session.event"
    trace_id: str | None = None


@dataclass
class ServerProfile:
    server_url: str = ""
    display_name: str = "Cloudra Server"
    token: str = field(default="", repr=False)
    allow_insecure_http: bool = False

    def persisted(self) -> dict:
        # Android credentials are persisted only by the native Keystore bridge.
        # This ordinary JSON profile deliberately never receives them.
        return {
            "server_url": self.server_url,
            "display_name": self.display_name,
            "allow_insecure_http": self.allow_insecure_http,
        }


class RemoteStateStore:
    """Small Android-side cache for non-secret profile data and event cursors."""

    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def load_profile(self) -> ServerProfile:
        raw = self._load().get("profile", {})
        if not isinstance(raw, dict):
            raw = {}
        return ServerProfile(
            server_url=str(raw.get("server_url", "")),
            display_name=str(raw.get("display_name", "Cloudra Server")),
            allow_insecure_http=bool(raw.get("allow_insecure_http", False)),
        )

    def save_profile(self, profile: ServerProfile) -> None:
        raw_url = profile.server_url.strip()
        parsed = urlsplit(raw_url)
        if (
            any(ord(character) < 32 for character in raw_url)
            or parsed.username is not None
            or parsed.password is not None
            or bool(parsed.query)
            or bool(parsed.fragment)
        ):
            raise ValueError(
                "refusing to persist a Server URL with embedded credentials"
            )
        data = self._load()
        data["profile"] = profile.persisted()
        self._save(data)

    @staticmethod
    def _cursor_key(server_url: str, conversation_id: str, session_id: str) -> str:
        return "\n".join((server_url.rstrip("/"), conversation_id, session_id))

    def load_cursor(
        self,
        server_url: str,
        conversation_id: str,
        session_id: str,
    ) -> int:
        cursors = self._load().get("cursors", {})
        if not isinstance(cursors, dict):
            return 0
        value = cursors.get(
            self._cursor_key(server_url, conversation_id, session_id),
            0,
        )
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def save_cursor(
        self,
        server_url: str,
        conversation_id: str,
        session_id: str,
        cursor: int,
    ) -> None:
        data = self._load()
        cursors = data.setdefault("cursors", {})
        if not isinstance(cursors, dict):
            cursors = {}
            data["cursors"] = cursors
        key = self._cursor_key(server_url, conversation_id, session_id)
        try:
            current = int(cursors.get(key, 0))
        except (TypeError, ValueError):
            current = 0
        cursors[key] = max(current, int(cursor))
        self._save(data)


@runtime_checkable
class CloudraBackend(Protocol):
    mode: str
    supports_approvals: bool

    async def list_conversations(self) -> list[dict]: ...

    async def create_conversation(self) -> dict: ...

    async def get_conversation_messages(
        self,
        conversation_id: str,
    ) -> list[dict]: ...

    async def list_sessions(self, conversation_id: str) -> list[dict]: ...

    async def submit_session(
        self,
        query: str,
        conversation_id: str,
        *,
        working_directory: str | None = None,
    ) -> tuple[str, dict]: ...

    async def get_session(
        self,
        conversation_id: str,
        session_id: str,
    ) -> dict | None: ...

    async def cancel_session(
        self,
        conversation_id: str,
        session_id: str,
    ) -> dict | None: ...

    async def append_session_message(
        self,
        conversation_id: str,
        session_id: str,
        content: str,
    ) -> dict: ...

    async def list_pending_interactions(
        self,
        conversation_id: str,
        *,
        session_id: str | None = None,
    ) -> list[dict]: ...

    async def respond_interaction(
        self,
        conversation_id: str,
        interaction_id: str,
        response: str,
    ) -> dict: ...

    async def stream_events(
        self,
        conversation_id: str,
        session_id: str,
        after_cursor: int = 0,
    ) -> AsyncIterator[BackendEvent]: ...

    def load_cursor(self, conversation_id: str, session_id: str) -> int: ...

    def save_cursor(
        self,
        conversation_id: str,
        session_id: str,
        cursor: int,
    ) -> None: ...

    async def list_pending_approvals(
        self,
        conversation_id: str | None = None,
    ) -> list[dict]: ...

    async def decide_approval(
        self,
        conversation_id: str,
        approval_id: int,
        decision: str,
        denial_reason: str = "",
    ) -> bool: ...

    async def list_artifacts(
        self,
        conversation_id: str,
        *,
        session_id: str | None = None,
    ) -> list[dict]: ...

    async def download_artifact(
        self,
        conversation_id: str,
        artifact_id: str,
        target_dir: Path,
    ) -> Path: ...


class LocalCloudraBackend:
    """Desktop adapter preserving the existing in-process service."""

    mode = "local"
    supports_approvals = True

    def __init__(self, service=None):
        if service is None:
            from cloudra.service import CloudraService

            service = CloudraService()
        self.service = service

    async def list_conversations(self) -> list[dict]:
        return self.service.list_conversations()

    async def create_conversation(self) -> dict:
        conversation = self.service.create_conversation()
        return {"id": conversation.id, "state": conversation.state}

    async def get_conversation_messages(
        self,
        conversation_id: str,
    ) -> list[dict]:
        return self.service.get_conversation_messages(conversation_id)

    async def list_sessions(self, conversation_id: str) -> list[dict]:
        return [
            record.to_dict()
            for record in self.service.session_runner.list(conversation_id)
        ]

    async def submit_session(
        self,
        query: str,
        conversation_id: str,
        *,
        working_directory: str | None = None,
    ) -> tuple[str, dict]:
        _, record = self.service.submit_session_command(
            command_id=f"cmd_{uuid.uuid4().hex}",
            query=query,
            conversation_id=conversation_id,
            working_directory=working_directory,
        )
        return conversation_id, record.to_dict()

    async def get_session(
        self,
        conversation_id: str,
        session_id: str,
    ) -> dict | None:
        record = self.service.session_runner.get(conversation_id, session_id)
        return record.to_dict() if record is not None else None

    async def cancel_session(
        self,
        conversation_id: str,
        session_id: str,
    ) -> dict | None:
        record = await self.service.session_runner.cancel(
            conversation_id,
            session_id,
        )
        return record.to_dict() if record is not None else None

    async def append_session_message(
        self,
        conversation_id: str,
        session_id: str,
        content: str,
    ) -> dict:
        configured_workspace = getattr(
            self.service.config,
            "workspace_dir",
            None,
        )
        command, record = await self.service.append_session_message_command(
            command_id=f"cmd_{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            session_id=session_id,
            content=content,
            working_directory=(
                str(configured_workspace)
                if configured_workspace is not None
                else None
            ),
        )
        payload = record.to_dict()
        payload["command"] = command.to_dict()
        return payload

    async def list_pending_interactions(
        self,
        conversation_id: str,
        *,
        session_id: str | None = None,
    ) -> list[dict]:
        return self.service.list_pending_interactions(
            conversation_id,
            session_id=session_id,
        )

    async def respond_interaction(
        self,
        conversation_id: str,
        interaction_id: str,
        response: str,
    ) -> dict:
        command, interaction = await self.service.respond_interaction_command(
            command_id=f"cmd_{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            interaction_id=interaction_id,
            response=response,
        )
        payload = interaction.to_dict()
        payload["command"] = command.to_dict()
        return payload

    async def stream_events(
        self,
        conversation_id: str,
        session_id: str,
        after_cursor: int = 0,
    ) -> AsyncIterator[BackendEvent]:
        cursor = after_cursor
        while True:
            rows = self.service.session_runner.events(
                conversation_id,
                session_id,
                cursor,
            )
            for row in rows:
                cursor = int(row["id"])
                yield BackendEvent(
                    cursor=cursor,
                    event_type=row["event_type"],
                    data=row["data"],
                    created_at=row.get("created_at"),
                )
            record = self.service.session_runner.get(
                conversation_id,
                session_id,
            )
            if record is None or (record.state in TERMINAL_STATES and not rows):
                return
            await asyncio.sleep(0.25)

    def load_cursor(self, conversation_id: str, session_id: str) -> int:
        return 0

    def save_cursor(
        self,
        conversation_id: str,
        session_id: str,
        cursor: int,
    ) -> None:
        return None

    async def list_pending_approvals(
        self,
        conversation_id: str | None = None,
    ) -> list[dict]:
        if conversation_id is not None:
            return self.service.list_pending_approvals_for_conversation(
                conversation_id
            )
        return await self.service.list_pending_approvals()

    async def decide_approval(
        self,
        conversation_id: str,
        approval_id: int,
        decision: str,
        denial_reason: str = "",
    ) -> bool:
        return await self.service.decide_approval(
            conversation_id,
            approval_id,
            decision,
            denial_reason,
        )

    async def list_artifacts(
        self,
        conversation_id: str,
        *,
        session_id: str | None = None,
    ) -> list[dict]:
        return [
            artifact.to_dict()
            for artifact in self.service.artifacts.list(
                conversation_id,
                session_id=session_id,
            )
        ]

    async def download_artifact(
        self,
        conversation_id: str,
        artifact_id: str,
        target_dir: Path,
    ) -> Path:
        token, _ = self.service.artifacts.issue_download_token(
            conversation_id,
            artifact_id,
        )
        artifact, source = self.service.artifacts.resolve_download(
            conversation_id,
            artifact_id,
            token,
        )
        return await asyncio.to_thread(
            _copy_artifact,
            source,
            artifact.to_dict(),
            target_dir,
        )

    def get_model_settings(self) -> dict:
        config = self.service.config
        return {
            "coordinator_model": config.coordinator.model,
            "coordinator_url": config.coordinator.url,
            "coordinator_key": config.coordinator.key,
            "follower_model": config.follower.model,
            "follower_url": config.follower.url,
            "follower_key": config.follower.key,
        }

    def save_model_settings(self, values: dict) -> None:
        config = self.service.config
        config.coordinator.model = values["coordinator_model"]
        config.coordinator.url = values["coordinator_url"]
        config.coordinator.key = values["coordinator_key"]
        config.follower.model = values["follower_model"]
        config.follower.url = values["follower_url"]
        config.follower.key = values["follower_key"]
        config.save()

    def set_workspace(self, path: Path) -> None:
        self.service.config.workspace_dir = path.resolve()
        self.service.config.save()


class RemoteCloudraBackend:
    """HTTP/SSE Android client. It never reads model-provider configuration."""

    mode = "remote"
    supports_approvals = True

    def __init__(
        self,
        profile: ServerProfile,
        state_store: RemoteStateStore,
        *,
        client: httpx.AsyncClient | None = None,
    ):
        self.profile = profile
        self.state_store = state_store
        self._injected_client = client
        self._owned_client: httpx.AsyncClient | None = None

    @staticmethod
    def _validated_base_url(profile: ServerProfile) -> str:
        raw = profile.server_url.strip().rstrip("/")
        if not raw:
            raise BackendUnavailable("请先配置 Cloudra Server 地址")
        if any(ord(character) < 32 for character in raw):
            raise BackendUnavailable("Server 地址包含非法控制字符")
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise BackendUnavailable("Server 地址必须是 http:// 或 https:// URL")
        if parsed.username is not None or parsed.password is not None:
            raise BackendUnavailable(
                "Server 地址不能包含用户名或密码；Token 请使用独立凭据字段"
            )
        if parsed.query or parsed.fragment:
            raise BackendUnavailable(
                "Server 地址不能包含 query 或 fragment"
            )
        local_host = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            parsed.scheme == "http"
            and not local_host
            and not profile.allow_insecure_http
        ):
            raise BackendUnavailable(
                "非本机 HTTP 仅允许在显式启用开发模式后使用"
            )
        return raw

    def _base_url(self) -> str:
        return self._validated_base_url(self.profile)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "X-Cloudra-Protocol-Version": str(PROTOCOL_VERSION),
            "X-Cloudra-Client-Version": __version__,
        }
        if self.profile.token:
            headers["Authorization"] = f"Bearer {self.profile.token}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        if self._injected_client is not None:
            return self._injected_client
        base_url = self._base_url()
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(30.0, read=60.0),
                follow_redirects=False,
            )
        return self._owned_client

    async def close(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def reconfigure(self, profile: ServerProfile) -> None:
        # Validate before RemoteStateStore can persist a URL carrying embedded
        # credentials or another malformed origin.
        self._validated_base_url(profile)
        await self.close()
        self.profile = profile
        self.state_store.save_profile(profile)

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        self._base_url()
        headers = dict(self._headers())
        headers.update(kwargs.pop("headers", {}))
        try:
            response = await self._client().request(
                method,
                path,
                headers=headers,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise BackendUnavailable(f"无法连接 Cloudra Server：{exc}") from exc
        if response.status_code == 401:
            raise BackendAuthenticationError("Cloudra Server Token 无效或已过期")
        if response.status_code == 426:
            raise BackendProtocolError("客户端与服务器协议版本不兼容")
        if response.is_error:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = response.text[:500]
            raise BackendError(f"Server 请求失败 ({response.status_code})：{detail}")
        return response

    async def _command_request(
        self,
        method: str,
        path: str,
        *,
        command_id: str | None = None,
        **kwargs,
    ) -> httpx.Response:
        """Retry transport failures with one stable idempotency key."""

        command_id = command_id or f"cmd_{uuid.uuid4().hex}"
        headers = dict(kwargs.pop("headers", {}))
        headers["Idempotency-Key"] = command_id
        delays = (0.0, 0.25, 0.75)
        last_error: BackendUnavailable | None = None
        for attempt, delay in enumerate(delays):
            if delay:
                await asyncio.sleep(delay)
            try:
                return await self._request(
                    method,
                    path,
                    headers=headers,
                    **kwargs,
                )
            except BackendUnavailable as exc:
                last_error = exc
                if attempt == len(delays) - 1:
                    raise
        raise last_error or BackendUnavailable("控制命令发送失败")

    async def probe(self) -> dict:
        return (await self._request("GET", "/api/v1/profile")).json()

    async def list_conversations(self) -> list[dict]:
        return (await self._request("GET", "/api/v1/conversations")).json()

    async def create_conversation(self) -> dict:
        return (await self._request("POST", "/api/v1/conversations")).json()

    async def get_conversation_messages(
        self,
        conversation_id: str,
    ) -> list[dict]:
        return (
            await self._request(
                "GET",
                f"/api/v1/conversations/{conversation_id}/messages",
            )
        ).json()

    async def list_sessions(self, conversation_id: str) -> list[dict]:
        return (
            await self._request(
                "GET",
                f"/api/v1/conversations/{conversation_id}/sessions",
            )
        ).json()

    async def submit_session(
        self,
        query: str,
        conversation_id: str,
        *,
        working_directory: str | None = None,
    ) -> tuple[str, dict]:
        record = (
            await self._command_request(
                "POST",
                f"/api/v1/conversations/{conversation_id}/sessions",
                json={
                    "query": query,
                    "workspace_id": "default",
                    "yolo": False,
                },
            )
        ).json()
        return conversation_id, record

    async def get_session(
        self,
        conversation_id: str,
        session_id: str,
    ) -> dict | None:
        try:
            response = await self._request(
                "GET",
                f"/api/v1/sessions/{session_id}",
                params={"conversation_id": conversation_id},
            )
        except BackendError as exc:
            if "(404)" in str(exc):
                return None
            raise
        return response.json()

    async def cancel_session(
        self,
        conversation_id: str,
        session_id: str,
    ) -> dict | None:
        try:
            response = await self._command_request(
                "POST",
                f"/api/v1/sessions/{session_id}/cancel",
                params={"conversation_id": conversation_id},
            )
        except BackendError as exc:
            if "(404)" in str(exc):
                return None
            raise
        return response.json()

    async def append_session_message(
        self,
        conversation_id: str,
        session_id: str,
        content: str,
    ) -> dict:
        response = await self._command_request(
            "POST",
            f"/api/v1/sessions/{session_id}/messages",
            params={"conversation_id": conversation_id},
            json={"content": content},
        )
        return response.json()

    async def list_pending_interactions(
        self,
        conversation_id: str,
        *,
        session_id: str | None = None,
    ) -> list[dict]:
        params = {"conversation_id": conversation_id}
        if session_id is not None:
            params["session_id"] = session_id
        response = await self._request(
            "GET",
            "/api/v1/interactions",
            params=params,
        )
        return response.json()

    async def respond_interaction(
        self,
        conversation_id: str,
        interaction_id: str,
        response: str,
    ) -> dict:
        result = await self._command_request(
            "POST",
            f"/api/v1/interactions/{interaction_id}/response",
            params={"conversation_id": conversation_id},
            json={"response": response},
        )
        return result.json()

    @staticmethod
    def _decode_event(envelope: dict) -> BackendEvent:
        if envelope.get("protocol") != "cloudra-control":
            raise BackendProtocolError("收到未知的事件协议")
        if envelope.get("version") != PROTOCOL_VERSION:
            raise BackendProtocolError("收到不兼容的事件协议版本")
        payload = envelope.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        data = payload.get("data", {})
        if not isinstance(data, dict):
            data = {"value": data}
        return BackendEvent(
            cursor=int(envelope.get("cursor", 0)),
            event_type=str(payload.get("event_type", "unknown")),
            data=data,
            created_at=envelope.get("timestamp"),
            envelope_type=str(envelope.get("type", "session.event")),
            trace_id=envelope.get("trace_id"),
        )

    async def stream_events(
        self,
        conversation_id: str,
        session_id: str,
        after_cursor: int = 0,
    ) -> AsyncIterator[BackendEvent]:
        self._base_url()
        cursor = max(0, int(after_cursor))
        retry_delay = 0.5
        while True:
            terminal = False
            received_event = False
            try:
                async with self._client().stream(
                    "GET",
                    (
                        f"/api/v1/conversations/{conversation_id}/sessions/"
                        f"{session_id}/events/stream"
                    ),
                    params={"after_cursor": cursor},
                    headers={
                        **self._headers(),
                        "Accept": "text/event-stream",
                    },
                ) as response:
                    if response.status_code == 401:
                        raise BackendAuthenticationError(
                            "Cloudra Server Token 无效或已过期"
                        )
                    if response.status_code == 426:
                        raise BackendProtocolError(
                            "客户端与服务器协议版本不兼容"
                        )
                    if response.is_error:
                        raise BackendError(
                            f"事件流请求失败 ({response.status_code})"
                        )
                    response.raise_for_status()
                    data_lines: list[str] = []
                    async for line in response.aiter_lines():
                        if not line:
                            if not data_lines:
                                continue
                            envelope = json.loads("\n".join(data_lines))
                            data_lines = []
                            event = self._decode_event(envelope)
                            if event.cursor <= cursor:
                                continue
                            received_event = True
                            yield event
                            # Resuming the generator means the UI successfully
                            # handled the previous event.
                            cursor = event.cursor
                            if (
                                event.event_type in TERMINAL_STATES
                                or event.data.get("state") in TERMINAL_STATES
                            ):
                                terminal = True
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].lstrip())
                if terminal:
                    return
                if not received_event:
                    # The server closes an already-terminal stream immediately
                    # when ``after_cursor`` is at its final event. Confirm the
                    # authoritative state so a resumed Android client can stop
                    # cleanly instead of reconnecting forever.
                    record = await self.get_session(conversation_id, session_id)
                    if record and record.get("state") in TERMINAL_STATES:
                        return
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 8.0)
                    continue
                retry_delay = 0.5
            except (BackendAuthenticationError, BackendProtocolError):
                raise
            except (httpx.HTTPError, json.JSONDecodeError, ValueError):
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 8.0)

    def load_cursor(self, conversation_id: str, session_id: str) -> int:
        return self.state_store.load_cursor(
            self.profile.server_url,
            conversation_id,
            session_id,
        )

    def save_cursor(
        self,
        conversation_id: str,
        session_id: str,
        cursor: int,
    ) -> None:
        self.state_store.save_cursor(
            self.profile.server_url,
            conversation_id,
            session_id,
            cursor,
        )

    async def list_pending_approvals(
        self,
        conversation_id: str | None = None,
    ) -> list[dict]:
        if conversation_id is None:
            return []
        response = await self._request(
            "GET",
            "/api/v1/approvals",
            params={"conversation_id": conversation_id},
        )
        return response.json()

    async def decide_approval(
        self,
        conversation_id: str,
        approval_id: int,
        decision: str,
        denial_reason: str = "",
    ) -> bool:
        response = await self._command_request(
            "POST",
            f"/api/v1/approvals/{approval_id}/decision",
            params={"conversation_id": conversation_id},
            json={
                "decision": decision,
                "denial_reason": denial_reason,
            },
        )
        return response.json().get("state") == decision

    async def pair_device(self, manifest: dict) -> dict:
        pairing = (
            await self._request(
                "POST",
                "/api/v1/pairing/start",
                json={"ttl_seconds": 300},
            )
        ).json()
        payload = dict(manifest)
        payload.update(
            {
                "pairing_id": pairing["pairing_id"],
                "pairing_secret": pairing["pairing_secret"],
            }
        )
        return (
            await self._request(
                "POST",
                "/api/v1/pairing/complete",
                json=payload,
            )
        ).json()

    async def _device_request(
        self,
        method: str,
        path: str,
        device_token: str,
        **kwargs,
    ) -> httpx.Response:
        if not device_token:
            raise BackendAuthenticationError("设备尚未配对")
        return await self._request(
            method,
            path,
            headers={"Authorization": f"Device {device_token}"},
            **kwargs,
        )

    async def device_hello(
        self,
        device_id: str,
        device_token: str,
        manifest: dict,
    ) -> dict:
        return (
            await self._device_request(
                "POST",
                f"/api/v1/devices/{device_id}/hello",
                device_token,
                json=manifest,
            )
        ).json()

    async def device_heartbeat(
        self,
        device_id: str,
        device_token: str,
        workspace_revision: int,
        config_revision: int,
        observations: list[dict] | None = None,
    ) -> dict:
        return (
            await self._device_request(
                "POST",
                f"/api/v1/devices/{device_id}/heartbeat",
                device_token,
                json={
                    "workspace_revision": workspace_revision,
                    "config_revision": config_revision,
                    "observations": observations or [],
                },
            )
        ).json()

    async def lease_device_tool_calls(
        self,
        device_id: str,
        device_token: str,
    ) -> list[dict]:
        return (
            await self._device_request(
                "POST",
                f"/api/v1/devices/{device_id}/tool-calls/lease",
                device_token,
                json={"max_count": 4, "lease_seconds": 30},
            )
        ).json()

    async def device_tool_action(
        self,
        device_id: str,
        device_token: str,
        tool_call_id: str,
        action: str,
        lease_id: str,
    ) -> dict:
        if action not in {"ack", "running", "waiting-for-approval"}:
            raise ValueError("无效的设备调用动作")
        return (
            await self._device_request(
                "POST",
                (
                    f"/api/v1/devices/{device_id}/tool-calls/"
                    f"{tool_call_id}/{action}"
                ),
                device_token,
                json={"lease_id": lease_id},
            )
        ).json()

    async def device_tool_result(
        self,
        device_id: str,
        device_token: str,
        tool_call_id: str,
        payload: dict,
    ) -> dict:
        return (
            await self._device_request(
                "POST",
                (
                    f"/api/v1/devices/{device_id}/tool-calls/"
                    f"{tool_call_id}/result"
                ),
                device_token,
                json=payload,
            )
        ).json()

    async def list_artifacts(
        self,
        conversation_id: str,
        *,
        session_id: str | None = None,
    ) -> list[dict]:
        params = {"conversation_id": conversation_id}
        if session_id is not None:
            params["session_id"] = session_id
        response = await self._request(
            "GET",
            "/api/v1/artifacts",
            params=params,
        )
        return response.json()

    async def download_artifact(
        self,
        conversation_id: str,
        artifact_id: str,
        target_dir: Path,
    ) -> Path:
        metadata = (
            await self._request(
                "GET",
                f"/api/v1/artifacts/{artifact_id}",
                params={"conversation_id": conversation_id},
            )
        ).json()
        grant = (
            await self._request(
                "POST",
                f"/api/v1/artifacts/{artifact_id}/download-token",
                params={"conversation_id": conversation_id},
                json={"ttl_seconds": 300},
            )
        ).json()
        self._base_url()
        try:
            async with self._client().stream(
                "GET",
                grant["download_url"],
                headers={
                    "X-Cloudra-Download-Token": grant["download_token"],
                },
            ) as response:
                if response.is_error:
                    raise BackendError(
                        f"Artifact 下载失败 ({response.status_code})"
                    )
                target_dir.mkdir(parents=True, exist_ok=True)
                filename = Path(str(metadata["name"])).name
                if not filename:
                    raise BackendProtocolError("Server 返回了无效的 Artifact 文件名")
                target = target_dir / filename
                temporary = target.with_suffix(target.suffix + ".part")
                digest = hashlib.sha256()
                size = 0
                try:
                    with temporary.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            handle.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                    if size != int(metadata["size"]):
                        raise BackendProtocolError("Artifact 下载大小校验失败")
                    if digest.hexdigest() != metadata["sha256"]:
                        raise BackendProtocolError("Artifact 下载哈希校验失败")
                    os.replace(temporary, target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                return target
        except httpx.HTTPError as exc:
            raise BackendUnavailable(f"Artifact 下载连接中断：{exc}") from exc


def _copy_artifact(source: Path, metadata: dict, target_dir: Path) -> Path:
    """Copy a trusted local artifact while applying the same client checks."""

    target_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(str(metadata["name"])).name
    if not filename:
        raise BackendProtocolError("Artifact 文件名无效")
    target = target_dir / filename
    temporary = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            while chunk := reader.read(1024 * 1024):
                writer.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size != int(metadata["size"]) or digest.hexdigest() != metadata["sha256"]:
            raise BackendProtocolError("Artifact 本地复制校验失败")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def create_default_backend(storage) -> CloudraBackend:
    """Android defaults to remote control; desktop retains local execution."""
    from cloudra.runtime_profile import is_mobile_runtime

    if storage.packaged or is_mobile_runtime():
        state_store = RemoteStateStore(storage.data_dir / "remote-state.json")
        profile = state_store.load_profile()
        profile.server_url = os.getenv(
            "CLOUDRA_SERVER_URL",
            profile.server_url,
        )
        profile.token = os.getenv("CLOUDRA_REMOTE_TOKEN", "")
        if os.getenv("CLOUDRA_REMOTE_ALLOW_HTTP", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            profile.allow_insecure_http = True
        return RemoteCloudraBackend(profile, state_store)
    return LocalCloudraBackend()
