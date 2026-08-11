import hashlib
import json

import httpx
import pytest

from cloudra.services.backends import (
    BackendProtocolError,
    BackendUnavailable,
    LocalCloudraBackend,
    RemoteCloudraBackend,
    RemoteStateStore,
    ServerProfile,
)


@pytest.mark.asyncio
async def test_local_backend_exposes_dag_read_surface():
    class Service:
        def dag_projection(self, conversation_id):
            return {"conversation_id": conversation_id, "frontier": []}

        def dag_graph(self, conversation_id, graph_kind):
            return {"conversation_id": conversation_id, "graph_kind": graph_kind}

        def dag_delivery_report(self, conversation_id):
            return {"conversation_id": conversation_id, "complete": False}

        def dag_history(self, conversation_id, after_revision=0):
            return [{"conversation_id": conversation_id, "after": after_revision}]

    backend = LocalCloudraBackend(Service())

    assert (await backend.get_dag_projection("conv"))["frontier"] == []
    assert (await backend.get_dag_graph("conv", "delivery"))["graph_kind"] == "delivery"
    assert (await backend.get_dag_delivery_report("conv"))["complete"] is False
    assert (await backend.get_dag_history("conv", after_revision=3))[0]["after"] == 3


@pytest.mark.asyncio
async def test_remote_backend_exposes_dag_read_surface(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, dict(request.url.params)))
        path = request.url.path
        if path.endswith("/projection"):
            return httpx.Response(200, json={"frontier": []})
        if path.endswith("/graphs/process"):
            return httpx.Response(200, json={"graph_kind": "process"})
        if path.endswith("/delivery-report"):
            return httpx.Response(200, json={"complete": False})
        if path.endswith("/history"):
            return httpx.Response(200, json=[{"mutation_id": "mut_1"}])
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

    assert (await backend.get_dag_projection("conv"))["frontier"] == []
    assert (await backend.get_dag_graph("conv", "process"))["graph_kind"] == "process"
    assert (await backend.get_dag_delivery_report("conv"))["complete"] is False
    assert (await backend.get_dag_history("conv", after_revision=2))[0]["mutation_id"] == "mut_1"
    assert requests[-1][1] == {"after_revision": "2"}
    await client.aclose()


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


def test_remote_state_store_migrates_legacy_profile_to_multi_server_registry(
    tmp_path,
):
    path = tmp_path / "remote-state.json"
    path.write_text(
        json.dumps(
            {
                "profile": {
                    "server_url": "https://legacy.cloudra.test",
                    "display_name": "Legacy",
                }
            }
        ),
        encoding="utf-8",
    )
    store = RemoteStateStore(path)
    legacy = store.load_profile()
    second = ServerProfile(
        server_url="https://hpc.cloudra.test",
        display_name="HPC",
        node_id="login-1",
        workspace_id="project-a",
        token="never-persist-this",
    )

    store.save_profile(legacy)
    store.save_profile(second)
    assert {profile.server_url for profile in store.load_profiles()} == {
        "https://legacy.cloudra.test",
        "https://hpc.cloudra.test",
    }
    assert store.load_profile().profile_id == second.profile_id
    assert store.select_profile(legacy.profile_id).server_url == legacy.server_url
    assert "never-persist-this" not in path.read_text(encoding="utf-8")

    store.save_cursor(legacy.server_url, "conv", "session", 7)
    store.save_cursor(second.server_url, "conv", "session", 9)
    store.remove_profile(legacy.profile_id)
    assert store.load_profile().profile_id == second.profile_id
    assert store.load_cursor(legacy.server_url, "conv", "session") == 0
    assert store.load_cursor(second.server_url, "conv", "session") == 9


def test_remote_cursor_is_isolated_by_node_and_workspace(tmp_path):
    store = RemoteStateStore(tmp_path / "remote-state.json")
    store.save_cursor(
        "https://cloudra.test",
        "conv",
        "session",
        12,
        "node-a\nworkspace-a",
    )

    assert store.load_cursor(
        "https://cloudra.test",
        "conv",
        "session",
        "node-a\nworkspace-a",
    ) == 12
    assert store.load_cursor(
        "https://cloudra.test",
        "conv",
        "session",
        "node-b\nworkspace-a",
    ) == 0

    legacy_key = "https://legacy.test\nconv\nsession"
    legacy_store = RemoteStateStore(tmp_path / "legacy-cursor.json")
    legacy_store.path.write_text(
        json.dumps({"cursors": {legacy_key: 7}}),
        encoding="utf-8",
    )
    assert legacy_store.load_cursor(
        "https://legacy.test",
        "conv",
        "session",
        "node-local\ndefault",
    ) == 7


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
    _, session = await backend.submit_session(
        "分析",
        "conv_1",
        orchestration_mode="dag_guided",
    )
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
        "orchestration_mode": "dag_guided",
    }
    assert "model" not in submitted
    assert "api_key" not in submitted
    await client.aclose()


@pytest.mark.asyncio
async def test_remote_backend_revokes_device_with_server_not_device_token(tmp_path):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"device_id": "dev_123456789012", "state": "revoked"},
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://cloudra.test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test", token="server-token"),
        RemoteStateStore(tmp_path / "state.json"),
        client=client,
    )
    result = await backend.revoke_device("dev_123456789012")
    assert result["state"] == "revoked"
    assert captured[0].method == "DELETE"
    assert captured[0].url.path == "/api/v1/devices/dev_123456789012"
    assert captured[0].headers["Authorization"] == "Bearer server-token"
    assert not captured[0].headers["Authorization"].startswith("Device ")
    await client.aclose()


@pytest.mark.asyncio
async def test_remote_backend_validates_and_routes_selected_node_workspace(
    tmp_path,
):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/nodes":
            return httpx.Response(
                200,
                json=[{"node_id": "hpc-login", "state": "online"}],
            )
        if request.url.path == "/api/v1/workspaces":
            return httpx.Response(
                200,
                json=[
                    {
                        "node_id": "hpc-login",
                        "workspace_id": "project-a",
                    }
                ],
            )
        if request.url.path.endswith("/sessions"):
            return httpx.Response(
                202,
                json={"session_id": "session_hpc", "state": "queued"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://cloudra.test",
    )
    store = RemoteStateStore(tmp_path / "state.json")
    backend = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test"),
        store,
        client=client,
    )

    await backend.select_node_workspace("hpc-login", "project-a")
    _, record = await backend.submit_session("运行计算", "conv_hpc")

    assert record["session_id"] == "session_hpc"
    submitted = json.loads(requests[-1].content)
    assert submitted["workspace_id"] == "project-a"
    assert requests[-1].headers["X-Cloudra-Node-ID"] == "hpc-login"
    persisted = store.load_profile()
    assert persisted.node_id == "hpc-login"
    assert persisted.workspace_id == "project-a"
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


@pytest.mark.asyncio
async def test_local_backend_applies_dag_mutation():
    class Service:
        def dag_apply_user_mutation(
            self, conversation_id, operations, base_revisions, rationale=""
        ):
            return {
                "conversation_id": conversation_id,
                "accepted": True,
                "operations": operations,
                "base_revisions": base_revisions,
                "rationale": rationale,
            }

    backend = LocalCloudraBackend(Service())
    result = await backend.apply_dag_mutation(
        "conv",
        [{"op": "update_node", "graph": "process", "data": {"node_id": "w1", "changes": {"priority": 5}}}],
        {"process": 0, "delivery": 0},
        "manual edit",
    )
    assert result["accepted"] is True
    assert result["rationale"] == "manual edit"


@pytest.mark.asyncio
async def test_remote_backend_applies_dag_mutation(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/dag/mutations"):
            seen["json"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"accepted": True})
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

    result = await backend.apply_dag_mutation(
        "conv",
        [{"op": "add_link", "graph": "process", "data": {"link_id": "l1"}}],
        {"process": 2, "delivery": 1},
        "link work to mechanism",
    )
    assert result == {"accepted": True}
    assert seen["json"]["base_revisions"] == {"process": 2, "delivery": 1}
    assert seen["json"]["rationale"] == "link work to mechanism"

    def not_found(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "DAG bundle 不存在"})

    client_missing = httpx.AsyncClient(
        transport=httpx.MockTransport(not_found),
        base_url="https://cloudra.test",
    )
    backend_missing = RemoteCloudraBackend(
        ServerProfile(server_url="https://cloudra.test"),
        RemoteStateStore(tmp_path / "state2.json"),
        client=client_missing,
    )
    assert (
        await backend_missing.apply_dag_mutation(
            "conv", [], {"process": 0, "delivery": 0}
        )
        is None
    )
    await client.aclose()
    await client_missing.aclose()
