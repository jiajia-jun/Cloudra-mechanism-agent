import hashlib
import json

import httpx
import pytest

from cloudra.backends import (
    BackendProtocolError,
    BackendUnavailable,
    RemoteCloudraBackend,
    RemoteStateStore,
    ServerProfile,
)


def _envelope(cursor: int, event_type: str, data: dict) -> dict:
    return {
        "protocol": "cloudra-control",
        "version": 1,
        "message_id": f"evt_{cursor}",
        "type": "session.event",
        "timestamp": "2026-07-29T00:00:00+00:00",
        "trace_id": None,
        "cursor": cursor,
        "payload": {
            "conversation_id": "conv_1",
            "session_id": "session_1",
            "event_type": event_type,
            "data": data,
        },
    }


def _sse(envelope: dict) -> str:
    return (
        f"id: {envelope['cursor']}\n"
        f"event: {envelope['type']}\n"
        f"data: {json.dumps(envelope)}\n\n"
    )


def test_remote_state_store_never_persists_token_and_cursor_is_monotonic(tmp_path):
    store = RemoteStateStore(tmp_path / "remote-state.json")
    profile = ServerProfile(
        server_url="https://cloudra.test",
        display_name="Lab",
        token="top-secret",
    )
    store.save_profile(profile)
    raw = (tmp_path / "remote-state.json").read_text(encoding="utf-8")

    assert "top-secret" not in raw
    assert "top-secret" not in repr(profile)
    assert store.load_profile().server_url == "https://cloudra.test"

    store.save_cursor("https://cloudra.test", "conv", "session", 9)
    store.save_cursor("https://cloudra.test", "conv", "session", 4)
    assert store.load_cursor(
        "https://cloudra.test",
        "conv",
        "session",
    ) == 9


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "server_url",
    [
        "https://user:secret@cloudra.test",
        "https://cloudra.test?token=secret",
        "https://cloudra.test/#secret",
    ],
)
async def test_remote_reconfigure_rejects_url_embedded_secrets_before_persisting(
    tmp_path,
    server_url,
):
    store = RemoteStateStore(tmp_path / "remote-state.json")
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test"),
        store,
    )

    with pytest.raises(BackendUnavailable):
        await backend.reconfigure(ServerProfile(server_url=server_url))

    assert not store.path.exists()


@pytest.mark.asyncio
async def test_remote_backend_uses_v1_and_sends_only_server_token(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/conversations":
            if request.method == "GET":
                return httpx.Response(200, json=[{"id": "conv_1"}])
            return httpx.Response(201, json={"id": "conv_2", "state": "active"})
        if request.url.path.endswith("/sessions"):
            return httpx.Response(
                202,
                json={"session_id": "session_1", "state": "queued"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://cloudra.test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="https://cloudra.test",
            token="server-token",
        ),
        RemoteStateStore(tmp_path / "state.json"),
        client=client,
    )

    assert await backend.list_conversations() == [{"id": "conv_1"}]
    assert (await backend.create_conversation())["id"] == "conv_2"
    _, session = await backend.submit_session("分析", "conv_1")
    assert session["session_id"] == "session_1"

    assert all(
        request.headers["Authorization"] == "Bearer server-token"
        for request in requests
    )
    assert all(
        request.headers["X-Cloudra-Protocol-Version"] == "1"
        for request in requests
    )
    assert requests[-1].headers["Idempotency-Key"].startswith("cmd_")
    submitted = json.loads(requests[-1].content)
    assert submitted == {
        "query": "分析",
        "workspace_id": "default",
        "yolo": False,
    }
    assert "model" not in submitted
    assert "api_key" not in submitted
    await client.aclose()


@pytest.mark.asyncio
async def test_remote_command_retry_reuses_idempotency_key(tmp_path):
    observed_keys = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_keys.append(request.headers["Idempotency-Key"])
        if len(observed_keys) == 1:
            raise httpx.ConnectError("response lost", request=request)
        return httpx.Response(
            202,
            json={
                "session_id": "session_retry",
                "state": "queued",
                "command": {"state": "applied"},
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://cloudra.test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test"),
        RemoteStateStore(tmp_path / "state.json"),
        client=client,
    )

    _, record = await backend.submit_session("重试", "conv_1")

    assert record["session_id"] == "session_retry"
    assert len(observed_keys) == 2
    assert observed_keys[0] == observed_keys[1]
    await client.aclose()


@pytest.mark.asyncio
async def test_remote_backend_supports_messages_and_interactions(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                202,
                json={
                    "session_id": "session_1",
                    "state": "running",
                    "command": {"state": "applied"},
                },
            )
        if request.url.path == "/api/v1/interactions":
            return httpx.Response(
                200,
                json=[
                    {
                        "interaction_id": "int_1",
                        "session_id": "session_1",
                        "prompt": "继续吗？",
                    }
                ],
            )
        if request.url.path.endswith("/response"):
            return httpx.Response(
                200,
                json={
                    "interaction_id": "int_1",
                    "state": "answered",
                    "response": "继续",
                    "command": {"state": "applied"},
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://cloudra.test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test"),
        RemoteStateStore(tmp_path / "state.json"),
        client=client,
    )

    appended = await backend.append_session_message(
        "conv_1",
        "session_1",
        "补充要求",
    )
    interactions = await backend.list_pending_interactions("conv_1")
    answered = await backend.respond_interaction("conv_1", "int_1", "继续")

    assert appended["command"]["state"] == "applied"
    assert interactions[0]["interaction_id"] == "int_1"
    assert answered["state"] == "answered"
    assert json.loads(requests[0].content) == {"content": "补充要求"}
    assert requests[0].headers["Idempotency-Key"].startswith("cmd_")
    assert json.loads(requests[-1].content) == {"response": "继续"}
    assert requests[-1].headers["Idempotency-Key"].startswith("cmd_")
    await client.aclose()


@pytest.mark.asyncio
async def test_remote_backend_supports_approval_and_verified_artifact_download(
    tmp_path,
):
    requests = []
    content = b"verified-artifact"
    digest = hashlib.sha256(content).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/api/v1/approvals" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "approval_id": 9,
                        "conversation_id": "conv_1",
                        "tool_name": "edit_file",
                        "state": "pending",
                    }
                ],
            )
        if path.endswith("/approvals/9/decision"):
            return httpx.Response(
                200,
                json={
                    "approval_id": 9,
                    "state": "approved",
                    "command": {"state": "applied"},
                },
            )
        if path == "/api/v1/artifacts":
            return httpx.Response(
                200,
                json=[{"artifact_id": "art_1", "name": "result.dat"}],
            )
        if path == "/api/v1/artifacts/art_1":
            return httpx.Response(
                200,
                json={
                    "artifact_id": "art_1",
                    "name": "result.dat",
                    "size": len(content),
                    "sha256": digest,
                },
            )
        if path.endswith("/download-token"):
            return httpx.Response(
                200,
                json={
                    "download_token": "short-lived-token",
                    "download_url": (
                        "/api/v1/artifacts/art_1/download"
                        "?conversation_id=conv_1"
                    ),
                },
            )
        if path.endswith("/artifacts/art_1/download"):
            assert request.headers["X-Cloudra-Download-Token"] == (
                "short-lived-token"
            )
            assert "Authorization" not in request.headers
            return httpx.Response(200, content=content)
        raise AssertionError(
            f"unexpected request: {request.method} {request.url}"
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://cloudra.test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="https://cloudra.test",
            token="server-token",
        ),
        RemoteStateStore(tmp_path / "state.json"),
        client=client,
    )

    approvals = await backend.list_pending_approvals("conv_1")
    approved = await backend.decide_approval("conv_1", 9, "approved")
    artifacts = await backend.list_artifacts("conv_1")
    target = await backend.download_artifact(
        "conv_1",
        "art_1",
        tmp_path / "downloads",
    )

    assert approvals[0]["tool_name"] == "edit_file"
    assert approved is True
    assert artifacts[0]["artifact_id"] == "art_1"
    assert target.read_bytes() == content
    decision_request = next(
        request
        for request in requests
        if request.url.path.endswith("/approvals/9/decision")
    )
    assert decision_request.headers["Idempotency-Key"].startswith("cmd_")
    assert not list((tmp_path / "downloads").glob("*.part"))
    await client.aclose()


@pytest.mark.asyncio
async def test_remote_event_stream_reconnects_from_last_applied_cursor(tmp_path):
    observed_cursors = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_cursors.append(int(request.url.params["after_cursor"]))
        if len(observed_cursors) == 1:
            return httpx.Response(
                200,
                text=_sse(_envelope(3, "llm_chunk", {"delta": "a"})),
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(
            200,
            text=_sse(_envelope(4, "completed", {"result": "done"})),
            headers={"Content-Type": "text/event-stream"},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://cloudra.test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test"),
        RemoteStateStore(tmp_path / "state.json"),
        client=client,
    )

    received = [
        event
        async for event in backend.stream_events(
            "conv_1",
            "session_1",
            after_cursor=0,
        )
    ]

    assert [event.cursor for event in received] == [3, 4]
    assert [event.event_type for event in received] == ["llm_chunk", "completed"]
    assert observed_cursors == [0, 3]
    await client.aclose()


@pytest.mark.asyncio
async def test_remote_event_stream_stops_when_terminal_cursor_is_already_applied(
    tmp_path,
):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/events/stream"):
            assert request.url.params["after_cursor"] == "4"
            return httpx.Response(
                200,
                text="",
                headers={"Content-Type": "text/event-stream"},
            )
        if request.url.path == "/api/v1/sessions/session_1":
            return httpx.Response(
                200,
                json={"session_id": "session_1", "state": "completed"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://cloudra.test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test"),
        RemoteStateStore(tmp_path / "state.json"),
        client=client,
    )

    received = [
        event
        async for event in backend.stream_events(
            "conv_1",
            "session_1",
            after_cursor=4,
        )
    ]

    assert received == []
    assert requests == [
        (
            "GET",
            "/api/v1/conversations/conv_1/sessions/session_1/events/stream",
        ),
        ("GET", "/api/v1/sessions/session_1"),
    ]
    await client.aclose()


def test_remote_backend_rejects_insecure_http_without_explicit_opt_in(tmp_path):
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="http://192.168.1.20:8000"),
        RemoteStateStore(tmp_path / "state.json"),
    )
    with pytest.raises(BackendUnavailable, match="开发模式"):
        backend._base_url()


def test_remote_backend_rejects_unknown_event_protocol(tmp_path):
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test"),
        RemoteStateStore(tmp_path / "state.json"),
    )
    envelope = _envelope(1, "completed", {})
    envelope["version"] = 2
    with pytest.raises(BackendProtocolError, match="不兼容"):
        backend._decode_event(envelope)
