import asyncio
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
from cloudra.device.registry import (
    DEVICE_TOOLS,
    DeviceToolContext,
    DeviceToolError,
    DeviceToolSpec,
    capability_manifest,
    capability_revision,
)
from cloudra.device.runtime import DeviceRuntime, DeviceStateStore
from cloudra.infra.config import get_config, reload_config
from cloudra.infra.native_bridge import NativeBridgeError
from cloudra.persistence.database import ConversationDB
from cloudra.services import session_store
from cloudra.services.api import create_app
from cloudra.services.backends import (
    BackendUnavailable,
    RemoteCloudraBackend,
    RemoteStateStore,
    ServerProfile,
)
from cloudra.services.device_broker import (
    DeviceAuthenticationError,
    DeviceBroker,
    DeviceInvocationConflict,
    DeviceInvocationError,
    PairingError,
)
from cloudra.services.service import CloudraService
from cloudra.tools.DeviceTool.device_tools import (
    DeviceTextEdit,
    DeviceWorkspaceApplyPatch,
    DeviceWorkspaceApplyPatchInput,
    DeviceWorkspaceRead,
    DeviceWorkspaceReadInput,
)


def test_device_identity_is_scoped_per_server_profile(tmp_path):
    store = DeviceStateStore(tmp_path / "device-state.json")
    store.save_identity("legacy-device", "Legacy")
    assert store.identity("server-a")["device_id"] == "legacy-device"

    store.save_identity("device-a", "Server A", "server-a")
    assert store.identity("server-a")["device_id"] == "device-a"
    assert store.identity("server-b") == {}
    store.save_identity("device-b", "Server B", "server-b")
    assert store.identity("server-a")["device_id"] == "device-a"
    assert store.identity("server-b")["device_id"] == "device-b"
    store.remove_identity("server-a")
    assert store.identity("server-a") == {}
    assert store.identity("server-b")["device_id"] == "device-b"


@pytest.fixture
def device_environment(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    workspace = tmp_path / "phone-workspace"
    workspace.mkdir()
    monkeypatch.setenv("CLOUDRA_DATA_DIR", str(data_dir))
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "server-token")
    reload_config()
    config = get_config()
    config.data_dir = data_dir
    config.workspace_dir = tmp_path / "server-workspace"
    config.workspace_dir.mkdir()
    return data_dir, workspace


def _pair(broker: DeviceBroker) -> dict:
    pairing = broker.start_pairing(ttl_seconds=60)
    return broker.complete_pairing(
        pairing_id=pairing["pairing_id"],
        pairing_secret=pairing["pairing_secret"],
        display_name="Test Phone",
        client_version="phase4-test",
        capabilities=capability_manifest(),
        capability_revision=capability_revision(),
        workspace_revision=3,
        config_revision=2,
    )


def test_pairing_is_one_time_hashed_and_revocable(device_environment):
    data_dir, _ = device_environment
    broker = DeviceBroker(data_dir)
    pairing = broker.start_pairing(ttl_seconds=60)
    credential = broker.complete_pairing(
        pairing_id=pairing["pairing_id"],
        pairing_secret=pairing["pairing_secret"],
        display_name="Test Phone",
        client_version="phase4-test",
        capabilities=capability_manifest(),
        capability_revision=capability_revision(),
        workspace_revision=3,
        config_revision=2,
    )

    with pytest.raises(PairingError, match="已使用"):
        broker.complete_pairing(
            pairing_id=pairing["pairing_id"],
            pairing_secret=pairing["pairing_secret"],
            display_name="Replay",
            client_version="phase4-test",
            capabilities=capability_manifest(),
            capability_revision=capability_revision(),
            workspace_revision=3,
            config_revision=2,
        )

    raw_database = broker.path.read_bytes()
    assert credential["device_token"].encode() not in raw_database
    authenticated = broker.authenticate(credential["device_token"])
    assert authenticated["device_id"] == credential["device_id"]
    assert authenticated["state"] == "online"
    assert broker.revoke(credential["device_id"]) is True
    with pytest.raises(DeviceAuthenticationError, match="撤销"):
        broker.authenticate(credential["device_token"])


def test_device_invocation_lease_ack_result_and_replay(device_environment):
    data_dir, _ = device_environment
    broker = DeviceBroker(data_dir)
    credential = _pair(broker)
    invocation = broker.create_invocation(
        conversation_id="conv_device",
        session_id="a-0_run_device",
        tool_name="device.workspace.read",
        arguments={"path": "note.txt"},
    )
    assert invocation["expected_workspace_revision"] == 3

    leased = broker.lease(credential["device_id"])
    assert len(leased) == 1
    call = leased[0]
    assert call["state"] == "leased"
    acknowledged = broker.acknowledge(
        credential["device_id"],
        call["tool_call_id"],
        call["lease_id"],
    )
    assert acknowledged["state"] == "acknowledged"
    running = broker.mark_running(
        credential["device_id"],
        call["tool_call_id"],
        call["lease_id"],
    )
    assert running["state"] == "running"
    payload = {"content": "hello", "workspace_revision": 3}
    first = broker.finish(
        credential["device_id"],
        call["tool_call_id"],
        status="succeeded",
        result=payload,
    )
    replay = broker.finish(
        credential["device_id"],
        call["tool_call_id"],
        status="succeeded",
        result=payload,
    )
    assert first == replay
    assert replay["result"] == payload
    assert broker.lease(credential["device_id"]) == []
    with pytest.raises(DeviceInvocationConflict, match="不同"):
        broker.finish(
            credential["device_id"],
            call["tool_call_id"],
            status="failed",
            error="different",
        )


def test_expired_lease_requeues_but_expired_call_does_not(
    device_environment,
):
    data_dir, _ = device_environment
    broker = DeviceBroker(data_dir)
    credential = _pair(broker)
    invocation = broker.create_invocation(
        conversation_id="conv_lease",
        session_id="a-0_run_lease",
        tool_name="device.config.get",
        arguments={},
    )
    first = broker.lease(credential["device_id"])[0]
    with broker._connect() as con:
        con.execute(
            """UPDATE device_tool_invocations
            SET lease_expires_at=? WHERE tool_call_id=?""",
            (
                (
                    datetime.now(timezone.utc) - timedelta(seconds=1)
                ).isoformat(),
                invocation["tool_call_id"],
            ),
        )
        con.commit()
    second = broker.lease(credential["device_id"])[0]
    assert first["lease_id"] != second["lease_id"]

    with broker._connect() as con:
        con.execute(
            """UPDATE device_tool_invocations SET expires_at=?
            WHERE tool_call_id=?""",
            (
                (
                    datetime.now(timezone.utc) - timedelta(seconds=1)
                ).isoformat(),
                invocation["tool_call_id"],
            ),
        )
        con.commit()
    assert broker.lease(credential["device_id"]) == []
    assert broker.get_invocation(invocation["tool_call_id"])["state"] == (
        "expired"
    )


def test_offline_device_disappears_from_capabilities_and_hello_restores_it(
    device_environment,
):
    data_dir, _ = device_environment
    broker = DeviceBroker(data_dir)
    credential = _pair(broker)
    stale = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
    ).isoformat()
    with broker._connect() as con:
        con.execute(
            "UPDATE devices SET last_seen_at=? WHERE device_id=?",
            (stale, credential["device_id"]),
        )
        con.commit()

    assert broker.list_devices()[0]["state"] == "offline"
    assert broker.available_tool_names() == set()
    with pytest.raises(DeviceInvocationError, match="离线"):
        broker.select_device(
            "device.workspace.read",
            credential["device_id"],
        )

    restored = broker.hello(
        credential["device_id"],
        display_name="Test Phone",
        client_version="phase4-test",
        capabilities=capability_manifest(),
        capability_revision=capability_revision(),
        workspace_revision=3,
        config_revision=2,
    )
    assert restored["state"] == "online"
    assert "device.workspace.read" in broker.available_tool_names()


def test_device_workspace_tools_enforce_authorized_root(device_environment):
    _, workspace = device_environment
    context = DeviceToolContext(
        workspace=workspace,
        workspace_revision=5,
        config_revision=2,
        device_id="dev_test",
        display_name="Phone",
    )
    (workspace / "safe.txt").write_text("hello", encoding="utf-8")
    result = DEVICE_TOOLS["device.workspace.read"].handler(
        {"path": "safe.txt"},
        context,
    )
    assert result["content"] == "hello"
    assert result["workspace_revision"] == 5

    outside = workspace.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(DeviceToolError, match="越界"):
        DEVICE_TOOLS["device.workspace.read"].handler(
            {"path": "../outside.txt"},
            context,
        )

    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("当前平台不允许创建符号链接")
    with pytest.raises(DeviceToolError, match="符号链接"):
        DEVICE_TOOLS["device.workspace.read"].handler(
            {"path": "link.txt"},
            context,
        )


@pytest.mark.asyncio
async def test_api_runtime_executes_read_and_keeps_device_token_memory_only(
    device_environment,
):
    data_dir, workspace = device_environment
    service = CloudraService()
    transport = httpx.ASGITransport(app=create_app(service))
    client = httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    state_store = DeviceStateStore(data_dir / "device-state.json")
    runtime = DeviceRuntime(backend, state_store, workspace)
    credential = await runtime.pair()
    await runtime.announce()
    (workspace / "phone.txt").write_text("from-phone", encoding="utf-8")

    invocation = service.device_broker.create_invocation(
        conversation_id="conv_api_device",
        session_id="a-0_run_api_device",
        tool_name="device.workspace.read",
        arguments={"path": "phone.txt"},
    )
    assert await runtime.run_once() == 1
    completed = service.device_broker.get_invocation(
        invocation["tool_call_id"]
    )

    assert completed["state"] == "succeeded"
    assert completed["result"]["content"] == "from-phone"
    assert credential["device_id"] in state_store.path.read_text(
        encoding="utf-8"
    )
    assert "devtok_" not in state_store.path.read_text(encoding="utf-8")
    devices = (
        await backend._request("GET", "/api/v1/devices")
    ).json()
    assert devices[0]["state"] == "online"
    unauthorized = await client.post(
        f"/api/v1/devices/{credential['device_id']}/heartbeat",
        headers={
            "Authorization": "Bearer server-token",
            "X-Cloudra-Protocol-Version": "1",
        },
        json={"workspace_revision": 1, "config_revision": 1},
    )
    assert unauthorized.status_code == 401
    await client.aclose()


@pytest.mark.asyncio
async def test_runtime_outbox_prevents_duplicate_local_execution(
    device_environment,
    monkeypatch,
):
    data_dir, workspace = device_environment
    service = CloudraService()
    transport = httpx.ASGITransport(app=create_app(service))
    client = httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
    )
    await runtime.pair()
    await runtime.announce()
    executions = 0

    def counted_handler(arguments, context):
        nonlocal executions
        executions += 1
        return {
            "content": "once",
            "workspace_revision": context.workspace_revision,
        }

    original_spec = DEVICE_TOOLS["device.workspace.read"]
    monkeypatch.setitem(
        DEVICE_TOOLS,
        "device.workspace.read",
        DeviceToolSpec(
            name=original_spec.name,
            description=original_spec.description,
            risk=original_spec.risk,
            requires_approval=original_spec.requires_approval,
            handler=counted_handler,
        ),
    )
    invocation = service.device_broker.create_invocation(
        conversation_id="conv_outbox",
        session_id="a-0_run_outbox",
        tool_name="device.workspace.read",
        arguments={"path": "ignored"},
    )
    original_submit = backend.device_tool_result
    attempts = 0

    async def lose_first_result(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise BackendUnavailable("simulated response loss")
        return await original_submit(*args, **kwargs)

    monkeypatch.setattr(backend, "device_tool_result", lose_first_result)
    with pytest.raises(BackendUnavailable, match="response loss"):
        await runtime.run_once()
    assert executions == 1
    assert runtime.state_store.outbox()

    assert await runtime.run_once() == 0
    assert executions == 1
    assert runtime.state_store.outbox() == {}
    assert service.device_broker.get_invocation(
        invocation["tool_call_id"]
    )["state"] == "succeeded"
    await client.aclose()


@pytest.mark.asyncio
async def test_server_proxy_waits_for_device_then_restores_session(
    device_environment,
):
    data_dir, workspace = device_environment
    service = CloudraService()
    transport = httpx.ASGITransport(app=create_app(service))
    client = httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
    )
    await runtime.pair()
    await runtime.announce()
    (workspace / "proxy.txt").write_text("proxy-result", encoding="utf-8")

    conversation_id = "conv_proxy"
    session_id = "a-0_run_proxy"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="读取手机",
    )
    session_store.update_session_fields(db, session_id, {"state": "running"})
    tool = DeviceWorkspaceRead(
        subagent=SimpleNamespace(conversation_id=conversation_id)
    )
    session = Session(session_id, str(data_dir / "session.json"))
    task = asyncio.create_task(
        tool.tool_call(
            DeviceWorkspaceReadInput(path="proxy.txt"),
            session,
        )
    )
    for _ in range(40):
        if service.session_runner.get(
            conversation_id,
            session_id,
        ).state == "waiting_for_device":
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("Session 没有进入 waiting_for_device")

    assert await runtime.run_once() == 1
    result = await asyncio.wait_for(task, timeout=3)
    assert result.is_success is True
    assert result.content == "proxy-result"
    assert service.session_runner.get(
        conversation_id,
        session_id,
    ).state == "running"
    event_types = [
        event["event_type"]
        for event in service.session_runner.events(
            conversation_id,
            session_id,
        )
    ]
    assert "waiting_for_device" in event_types
    await client.aclose()


def test_agent_only_exposes_current_online_device_capabilities(
    device_environment,
):
    data_dir, _ = device_environment
    broker = DeviceBroker(data_dir)
    agent = Coordinator(query="test", conversation_id="conv_agent_device")
    before = {entry.tool_name for entry in agent.get_available_tools()}
    before_schemas = {
        item["function"]["name"] for item in agent._get_tools_schema()
    }
    assert "bashtools" in before
    assert not any(name.startswith("device.") for name in before)
    assert not any(name.startswith("device.") for name in before_schemas)

    _pair(broker)
    after = {entry.tool_name for entry in agent.get_available_tools()}
    after_schemas = {
        item["function"]["name"] for item in agent._get_tools_schema()
    }
    assert {
        "device.workspace.list",
        "device.workspace.read",
        "device.workspace.apply_patch",
        "device.config.get",
        "device.config.patch",
    } <= after
    assert {
        "device.workspace.list",
        "device.workspace.read",
        "device.workspace.apply_patch",
        "device.config.get",
        "device.config.patch",
    } <= after_schemas


def test_stale_waiting_for_device_session_becomes_interrupted(
    device_environment,
):
    _, _workspace = device_environment
    conversation_id = "conv_stale_device"
    session_id = "a-0_run_stale_device"
    stale = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
    ).isoformat()
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="等待已离线设备",
    )
    session_store.update_session_fields(
        db,
        session_id,
        {
            "state": "waiting_for_device",
            "heartbeat_at": stale,
        },
    )
    service = CloudraService()

    assert service.session_runner.recover_stale_sessions(60) == 1
    assert service.session_runner.get(
        conversation_id,
        session_id,
    ).state == "interrupted"


@pytest.mark.asyncio
async def test_local_approval_applies_workspace_patch_and_persists_diff(
    device_environment,
):
    data_dir, workspace = device_environment
    previews = []

    async def approve(_call, preview):
        previews.append(preview)
        return True, ""

    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
        approval_handler=approve,
    )
    await runtime.pair()
    await runtime.announce()
    source = workspace / "write.txt"
    source.write_text("alpha\nbeta\n", encoding="utf-8")
    expected_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    invocation = service.device_broker.create_invocation(
        conversation_id="conv_write_device",
        session_id="a-0_run_write_device",
        tool_name="device.workspace.apply_patch",
        arguments={
            "path": "write.txt",
            "expected_sha256": expected_sha256,
            "edits": [
                {
                    "old_text": "beta",
                    "new_text": "gamma",
                    "replace_all": False,
                }
            ],
        },
    )
    assert await runtime.run_once() == 1
    completed = service.device_broker.get_invocation(
        invocation["tool_call_id"]
    )

    assert completed["state"] == "succeeded"
    assert source.read_text(encoding="utf-8") == "alpha\ngamma\n"
    assert completed["result"]["before_sha256"] == expected_sha256
    assert completed["result"]["workspace_revision"] == (
        runtime.workspace_revision
    )
    assert previews[0]["path"] == "write.txt"
    assert "-beta" in previews[0]["diff"]
    assert "+gamma" in previews[0]["diff"]
    await client.aclose()


@pytest.mark.asyncio
async def test_local_denial_and_approval_time_conflict_never_overwrite_user_file(
    device_environment,
):
    data_dir, workspace = device_environment
    decisions = ["deny", "mutate"]
    source = workspace / "guarded.txt"
    source.write_text("original", encoding="utf-8")

    async def decide(_call, _preview):
        action = decisions.pop(0)
        if action == "deny":
            return False, "用户不允许修改"
        source.write_text("user changed during approval", encoding="utf-8")
        return True, ""

    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
        approval_handler=decide,
    )
    await runtime.pair()
    await runtime.announce()

    def enqueue(expected_sha256: str) -> dict:
        return service.device_broker.create_invocation(
            conversation_id="conv_guard_device",
            session_id="a-0_run_guard_device",
            tool_name="device.workspace.apply_patch",
            arguments={
                "path": "guarded.txt",
                "expected_sha256": expected_sha256,
                "edits": [
                    {
                        "old_text": "original",
                        "new_text": "agent value",
                    }
                ],
            },
        )

    initial_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    denied = enqueue(initial_sha)
    assert await runtime.run_once() == 1
    assert service.device_broker.get_invocation(
        denied["tool_call_id"]
    )["state"] == "declined"
    assert source.read_text(encoding="utf-8") == "original"

    conflicted = enqueue(initial_sha)
    assert await runtime.run_once() == 1
    conflict_result = service.device_broker.get_invocation(
        conflicted["tool_call_id"]
    )
    assert conflict_result["state"] == "failed"
    assert "审批期间已变化" in conflict_result["error"]
    assert source.read_text(encoding="utf-8") == (
        "user changed during approval"
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_config_patch_records_old_values_and_refreshes_manifest(
    device_environment,
):
    data_dir, workspace = device_environment

    async def approve(_call, _preview):
        return True, ""

    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    state_store = DeviceStateStore(data_dir / "device-state.json")
    runtime = DeviceRuntime(
        backend,
        state_store,
        workspace,
        approval_handler=approve,
    )
    await runtime.pair()
    await runtime.announce()
    before_revision = runtime.config_revision
    invocation = service.device_broker.create_invocation(
        conversation_id="conv_config_device",
        session_id="a-0_run_config_device",
        tool_name="device.config.patch",
        arguments={
            "patch": {
                "display_name": "Lab Phone",
                "max_read_bytes": 65_536,
            },
            "expected_config_revision": before_revision,
        },
    )

    assert await runtime.run_once() == 1
    completed = service.device_broker.get_invocation(
        invocation["tool_call_id"]
    )
    assert completed["state"] == "succeeded"
    assert completed["result"]["old_values"] == {
        "display_name": "Cloudra Android",
        "max_read_bytes": 262_144,
    }
    assert runtime.display_name == "Lab Phone"
    assert runtime.config_revision == before_revision + 1
    raw_state = state_store._load()
    assert raw_state["config_audit"][-1]["old_values"] == (
        completed["result"]["old_values"]
    )

    assert await runtime.run_once() == 0
    server_device = service.device_broker.get_device(runtime.device_id)
    assert server_device["display_name"] == "Lab Phone"
    assert server_device["config_revision"] == runtime.config_revision
    await client.aclose()


@pytest.mark.asyncio
async def test_lost_write_result_is_replayed_without_second_write(
    device_environment,
    monkeypatch,
):
    data_dir, workspace = device_environment

    async def approve(_call, _preview):
        return True, ""

    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
        approval_handler=approve,
    )
    await runtime.pair()
    await runtime.announce()
    source = workspace / "once.txt"
    source.write_text("before", encoding="utf-8")
    invocation = service.device_broker.create_invocation(
        conversation_id="conv_once_device",
        session_id="a-0_run_once_device",
        tool_name="device.workspace.apply_patch",
        arguments={
            "path": "once.txt",
            "expected_sha256": hashlib.sha256(
                source.read_bytes()
            ).hexdigest(),
            "edits": [{"old_text": "before", "new_text": "after"}],
        },
    )
    original_submit = backend.device_tool_result
    attempts = 0

    async def lose_first_result(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise BackendUnavailable("simulated write response loss")
        return await original_submit(*args, **kwargs)

    monkeypatch.setattr(backend, "device_tool_result", lose_first_result)
    with pytest.raises(BackendUnavailable, match="response loss"):
        await runtime.run_once()
    assert source.read_text(encoding="utf-8") == "after"
    assert runtime.state_store.outbox()

    assert await runtime.run_once() == 0
    assert source.read_text(encoding="utf-8") == "after"
    assert runtime.state_store.outbox() == {}
    assert service.device_broker.get_invocation(
        invocation["tool_call_id"]
    )["state"] == "succeeded"
    await client.aclose()


@pytest.mark.asyncio
async def test_server_write_proxy_waits_for_android_local_approval(
    device_environment,
):
    data_dir, workspace = device_environment
    approval_entered = asyncio.Event()
    allow_approval = asyncio.Event()

    async def approve(_call, _preview):
        approval_entered.set()
        await allow_approval.wait()
        return True, ""

    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
        approval_handler=approve,
    )
    await runtime.pair()
    await runtime.announce()
    source = workspace / "proxy-write.txt"
    source.write_text("old value", encoding="utf-8")

    conversation_id = "conv_proxy_write"
    session_id = "a-0_run_proxy_write"
    db = ConversationDB(conversation_id).init()
    session_store.insert_queued_session(
        db,
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        query="修改手机文件",
    )
    session_store.update_session_fields(db, session_id, {"state": "running"})
    tool = DeviceWorkspaceApplyPatch(
        subagent=SimpleNamespace(conversation_id=conversation_id)
    )
    session = Session(session_id, str(data_dir / "session-write.json"))
    tool_task = asyncio.create_task(
        tool.tool_call(
            DeviceWorkspaceApplyPatchInput(
                path="proxy-write.txt",
                expected_sha256=hashlib.sha256(
                    source.read_bytes()
                ).hexdigest(),
                edits=[
                    DeviceTextEdit(
                        old_text="old value",
                        new_text="new value",
                    )
                ],
            ),
            session,
        )
    )
    for _ in range(40):
        if service.session_runner.get(
            conversation_id,
            session_id,
        ).state == "waiting_for_device":
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("写工具没有进入 waiting_for_device")

    runtime_task = asyncio.create_task(runtime.run_once())
    await asyncio.wait_for(approval_entered.wait(), timeout=3)
    with service.device_broker._connect() as con:
        state = con.execute(
            """SELECT state FROM device_tool_invocations
            WHERE conversation_id=?""",
            (conversation_id,),
        ).fetchone()[0]
    assert state == "waiting_for_local_approval"
    assert source.read_text(encoding="utf-8") == "old value"

    allow_approval.set()
    assert await asyncio.wait_for(runtime_task, timeout=3) == 1
    result = await asyncio.wait_for(tool_task, timeout=3)
    assert result.is_success is True
    assert source.read_text(encoding="utf-8") == "new value"
    event_states = [
        event["data"].get("state")
        for event in service.session_runner.events(
            conversation_id,
            session_id,
        )
        if event["event_type"] == "device_tool_state"
    ]
    assert "waiting_for_local_approval" in event_states
    await client.aclose()


def test_device_state_observes_external_workspace_change_once(
    device_environment,
):
    data_dir, workspace = device_environment
    store = DeviceStateStore(data_dir / "device-state.json")
    initial_revision, _ = store.authorize_workspace(workspace)
    assert store.observe_workspace(workspace) == initial_revision

    source = workspace / "external.txt"
    source.write_text("outside the runtime", encoding="utf-8")
    changed_revision = store.observe_workspace(workspace)
    pending = store.pending_observations()

    assert changed_revision == initial_revision + 1
    assert len(pending) == 1
    assert pending[0]["event_type"] == "workspace.changed"
    assert pending[0]["payload"]["changes"] == [
        {"path": "external.txt", "change": "added"}
    ]
    assert store.observe_workspace(workspace) == changed_revision
    assert store.pending_observations() == pending


@pytest.mark.asyncio
async def test_runtime_heartbeat_durably_delivers_workspace_observation(
    device_environment,
):
    data_dir, workspace = device_environment
    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
    )
    await runtime.pair()
    await runtime.announce()
    assert await runtime.run_once() == 0
    (workspace / "changed.txt").write_text("new", encoding="utf-8")

    assert await runtime.run_once() == 0
    assert runtime.state_store.pending_observations() == []
    observations = service.device_broker.recent_observations(
        device_id=runtime.device_id,
    )
    assert len(observations) == 1
    assert observations[0]["event_type"] == "workspace.changed"
    assert observations[0]["revision"] == runtime.workspace_revision
    assert observations[0]["payload"]["changes"] == [
        {"path": "changed.txt", "change": "added"}
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_runtime_reannounces_dynamic_capability_manifest(
    device_environment,
    monkeypatch,
):
    data_dir, workspace = device_environment
    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
    )
    await runtime.pair()
    await runtime.announce()
    original = DEVICE_TOOLS["device.workspace.read"]

    monkeypatch.delitem(DEVICE_TOOLS, "device.workspace.read")
    assert await runtime.run_once() == 0
    without_read = service.device_broker.get_device(runtime.device_id)
    assert "device.workspace.read" not in {
        item["name"] for item in without_read["capabilities"]
    }
    agent = Coordinator(
        query="test",
        conversation_id="conv_dynamic_device",
    )
    assert "device.workspace.read" not in {
        entry.tool_name for entry in agent.get_available_tools()
    }

    monkeypatch.setitem(DEVICE_TOOLS, "device.workspace.read", original)
    assert await runtime.run_once() == 0
    restored = service.device_broker.get_device(runtime.device_id)
    assert "device.workspace.read" in {
        item["name"] for item in restored["capabilities"]
    }
    assert "device.workspace.read" in {
        entry.tool_name for entry in agent.get_available_tools()
    }
    await client.aclose()


@pytest.mark.asyncio
async def test_device_environment_event_is_observation_not_identity(
    device_environment,
):
    data_dir, server_workspace = device_environment
    broker = DeviceBroker(data_dir)
    credential = _pair(broker)
    agent = Coordinator(
        query="继续旧会话",
        conversation_id="conv_device_observation",
        working_directory=str(server_workspace),
    )

    await agent._build_request_kwargs()
    first = agent.get_runtime_diagnostics()
    observation = {
        "observation_id": "obs_1234567890abcdef",
        "event_type": "workspace.changed",
        "revision": 4,
        "payload": {
            "changes": [{"path": "note.txt", "change": "modified"}],
            "truncated": False,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    broker.heartbeat(
        credential["device_id"],
        workspace_revision=4,
        config_revision=2,
        observations=[observation],
    )
    request = await agent._build_request_kwargs()
    second = agent.get_runtime_diagnostics()

    assert second["prompt_revision"] == first["prompt_revision"]
    assert second["environment_revisions"]["devices"] != (
        first["environment_revisions"]["devices"]
    )
    assert "workspace.changed" in request["messages"][-1]["content"]
    assert "note.txt" in request["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_native_document_tools_use_bundled_bridge_and_local_approval(
    device_environment,
):
    data_dir, workspace = device_environment
    previews: list[dict] = []

    async def approve(_call, preview):
        previews.append(preview)
        return True, ""

    class FakeNative:
        def __init__(self):
            self.calls = []

        async def execute(self, action, arguments):
            self.calls.append((action, arguments))
            if action == "documents.list":
                return {
                    "status": "ok",
                    "path": ".",
                    "entries": [{"name": "note.txt", "kind": "file"}],
                }
            if action == "documents.write":
                return {
                    "status": "applied",
                    "path": arguments["path"],
                    "before_sha256": arguments["expected_sha256"],
                    "after_sha256": hashlib.sha256(
                        base64.b64decode(arguments["content"])
                    ).hexdigest(),
                    "size": 7,
                }
            raise AssertionError(action)

    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    native = FakeNative()
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
        approval_handler=approve,
        native_bridge=native,
    )
    await runtime.pair()
    await runtime.announce()

    listed = service.device_broker.create_invocation(
        conversation_id="conv_native_docs",
        session_id="a-0_native_docs",
        tool_name="device.documents.list",
        arguments={"path": ".", "max_entries": 20},
    )
    assert await runtime.run_once() == 1
    assert service.device_broker.get_invocation(
        listed["tool_call_id"]
    )["result"]["entries"][0]["name"] == "note.txt"

    content = base64.b64encode(b"changed").decode("ascii")
    before = hashlib.sha256(b"before").hexdigest()
    written = service.device_broker.create_invocation(
        conversation_id="conv_native_docs",
        session_id="a-0_native_docs",
        tool_name="device.documents.write",
        arguments={
            "path": "note.txt",
            "expected_sha256": before,
            "content": content,
        },
    )
    assert await runtime.run_once() == 1
    completed = service.device_broker.get_invocation(
        written["tool_call_id"]
    )
    assert completed["state"] == "succeeded"
    assert completed["result"]["status"] == "applied"
    assert previews[0]["before_sha256"] == before
    assert previews[0]["after_sha256"] == hashlib.sha256(
        b"changed"
    ).hexdigest()
    assert [call[0] for call in native.calls] == [
        "documents.list",
        "documents.write",
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_native_permission_denial_is_structured_and_not_success(
    device_environment,
):
    data_dir, workspace = device_environment

    async def approve(_call, _preview):
        return True, ""

    class DeniedNative:
        async def execute(self, action, arguments):
            raise NativeBridgeError(
                "permission_denied",
                "通知或文档权限未授予",
                {"status": "permission_denied"},
            )

    service = CloudraService()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://test",
    )
    backend = RemoteCloudraBackend(
        ServerProfile(
            server_url="http://test",
            token="server-token",
            allow_insecure_http=True,
        ),
        RemoteStateStore(data_dir / "remote-state.json"),
        client=client,
    )
    runtime = DeviceRuntime(
        backend,
        DeviceStateStore(data_dir / "device-state.json"),
        workspace,
        approval_handler=approve,
        native_bridge=DeniedNative(),
    )
    await runtime.pair()
    await runtime.announce()
    invocation = service.device_broker.create_invocation(
        conversation_id="conv_native_denied",
        session_id="a-0_native_denied",
        tool_name="device.file.pick",
        arguments={"mime_type": "text/plain", "max_bytes": 1024},
    )

    assert await runtime.run_once() == 1
    completed = service.device_broker.get_invocation(
        invocation["tool_call_id"]
    )
    assert completed["state"] == "failed"
    assert completed["result"]["native_status"] == "permission_denied"
    assert "权限未授予" in completed["error"]
    await client.aclose()


def test_device_runtime_enabled_flag_is_non_secret_and_durable(tmp_path):
    store = DeviceStateStore(tmp_path / "device-state.json")
    assert store.runtime_enabled() is False
    store.set_runtime_enabled(True)
    assert DeviceStateStore(store.path).runtime_enabled() is True
    raw = store.path.read_text(encoding="utf-8")
    assert '"runtime_enabled": true' in raw
    assert "token" not in raw.lower()


def test_acknowledged_device_result_keeps_only_idempotency_tombstone(
    tmp_path,
):
    store = DeviceStateStore(tmp_path / "device-state.json")
    secret_content = base64.b64encode(
        b"sensitive camera or selected-file bytes"
    ).decode("ascii")
    payload = {
        "status": "succeeded",
        "result": {
            "status": "ok",
            "content": secret_content,
            "encoding": "base64",
        },
        "error": "",
    }

    store.record_completed("dtc_sensitive", payload)
    assert store.completed("dtc_sensitive") == payload
    assert secret_content in store.path.read_text(encoding="utf-8")

    store.mark_sent("dtc_sensitive")

    raw = store.path.read_text(encoding="utf-8")
    assert secret_content not in raw
    assert store.outbox() == {}
    replay = store.completed("dtc_sensitive")
    assert replay["status"] == "failed"
    assert replay["result"]["native_status"] == "duplicate_after_ack"
