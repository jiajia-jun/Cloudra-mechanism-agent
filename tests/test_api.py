import json

import httpx
import pytest

from cloudra.api import create_app
from cloudra.config import get_config


class _Record:
    session_id = "a-0_run_1"

    def to_dict(self):
        return {"session_id": self.session_id, "state": "queued"}


class _Command:
    command_id = "cmd_test_12345678"
    state = "applied"

    def to_dict(self):
        return {"command_id": self.command_id, "state": self.state}


class _SessionRunner:
    def get(self, conversation_id, session_id):
        return None

    def list(self, conversation_id):
        return []

    def cancel(self, conversation_id, session_id):
        return None

    def events(self, conversation_id, session_id, after_id=0):
        return []


class FakeService:
    def __init__(self):
        self.session_runner = _SessionRunner()
        self.last_submit = None
        self.last_command_id = None
        self.last_append = None
        self.pending_interactions = []
        self.pending_approvals = []
        self.last_approval = None
        self.last_route = None

    def create_conversation(self):
        return type("Conversation", (), {"id": "conv_1", "state": "active"})()

    def submit_session(self, query, conversation_id=None, working_directory=None, yolo=False):
        self.last_submit = {
            "query": query,
            "conversation_id": conversation_id,
            "working_directory": working_directory,
            "yolo": yolo,
        }
        return conversation_id, _Record()

    def submit_session_command(
        self,
        *,
        command_id,
        query,
        conversation_id,
        working_directory=None,
        node_id="node-local",
        workspace_id="default",
    ):
        self.last_command_id = command_id
        self.last_submit = {
            "query": query,
            "conversation_id": conversation_id,
            "working_directory": working_directory,
            "yolo": False,
        }
        self.last_route = (node_id, workspace_id)
        command = _Command()
        command.command_id = command_id
        return command, _Record()

    async def cancel_session_command(self, **kwargs):
        return _Command(), None

    async def append_session_message_command(self, **kwargs):
        self.last_append = kwargs
        return _Command(), _Record()

    def list_pending_interactions(self, conversation_id, session_id=None):
        return self.pending_interactions

    async def respond_interaction_command(self, **kwargs):
        self.last_command_id = kwargs["command_id"]
        interaction = type(
            "Interaction",
            (),
            {
                "to_dict": lambda self: {
                    "interaction_id": kwargs["interaction_id"],
                    "state": "answered",
                    "response": kwargs["response"],
                }
            },
        )()
        return _Command(), interaction

    def list_conversations(self):
        return []

    def get_conversation_messages(self, conversation_id):
        return []

    async def list_pending_approvals(self):
        return []

    async def decide_approval(self, *args, **kwargs):
        return False

    def list_pending_approvals_for_conversation(self, conversation_id):
        return self.pending_approvals

    async def decide_approval_command(self, **kwargs):
        self.last_command_id = kwargs["command_id"]
        self.last_approval = kwargs
        return _Command(), {
            "approval_id": kwargs["approval_id"],
            "conversation_id": kwargs["conversation_id"],
            "state": kwargs["decision"],
            "denial_reason": kwargs["denial_reason"],
        }


@pytest.mark.asyncio
async def test_health_is_public(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "secret")
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_operations_status_is_protected_and_contains_no_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "secret-token")
    monkeypatch.setenv("CLOUDRA_MIN_FREE_BYTES", "0")
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/api/operations/status")
        response = await client.get(
            "/api/operations/status",
            headers={"Authorization": "Bearer secret-token"},
        )
    assert denied.status_code == 401
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "secret-token" not in response.text


@pytest.mark.asyncio
async def test_runtime_diagnostics_reports_explicit_registries(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/runtime/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["server_version"]
    assert payload["runtime_profile"] in {"server", "android"}
    assert payload["tools"]["revision"].startswith("sha256:")
    assert "text_reader" in payload["tools"]["names"]
    assert payload["subagents"]["revision"].startswith("sha256:")
    assert "a-1" in payload["subagents"]["agent_ids"]


@pytest.mark.asyncio
async def test_session_diagnostics_returns_latest_llm_request(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    service = FakeService()
    service.session_runner.get = lambda _conversation_id, _session_id: _Record()
    service.session_runner.events = lambda _conversation_id, _session_id: [
        {"id": 1, "event_type": "phase", "data": {"phase": "thinking"}},
        {
            "id": 2,
            "event_type": "llm_request_diagnostics",
            "data": {
                "trace_id": "llm_test",
                "prompt_revision": "sha256:prompt",
                "capability_revision": "sha256:tools",
                "tool_names": ["text_reader"],
            },
        },
    ]
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/conversations/conv_1/sessions/a-0_run_1/diagnostics"
        )

    assert response.status_code == 200
    latest = response.json()["latest_request"]
    assert latest["trace_id"] == "llm_test"
    assert latest["tool_names"] == ["text_reader"]


@pytest.mark.asyncio
async def test_session_endpoint_requires_token(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "secret")
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        path = "/api/conversations/conv_1/sessions"
        assert (await client.post(path, json={"query": "hello"})).status_code == 401
        response = await client.post(
            path,
            json={"query": "hello"},
            headers={"Authorization": "Bearer secret"},
        )
    assert response.status_code == 202
    assert response.json()["session_id"] == "a-0_run_1"


@pytest.mark.asyncio
async def test_session_input_is_validated(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/conversations/conv_1/sessions",
            json={"query": ""},
        )
    assert response.status_code == 422


def _v1_headers(token: str | None = None, protocol: str = "1") -> dict[str, str]:
    headers = {
        "X-Cloudra-Protocol-Version": protocol,
        "X-Cloudra-Client-Version": "android-test",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@pytest.mark.asyncio
async def test_v1_profile_uses_basic_token_and_reports_versions(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "remote-secret")
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.get("/api/v1/profile", headers=_v1_headers())
        response = await client.get(
            "/api/v1/profile",
            headers=_v1_headers("remote-secret"),
        )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    payload = response.json()
    assert payload["protocol"] == "cloudra-control"
    assert payload["protocol_version"] == 1
    assert payload["server_version"]
    assert payload["client_version"] == "android-test"


@pytest.mark.asyncio
async def test_v1_rejects_incompatible_protocol(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/profile",
            headers=_v1_headers(protocol="99"),
        )

    assert response.status_code == 426
    assert response.headers["X-Cloudra-Protocol-Version"] == "1"


@pytest.mark.asyncio
async def test_v1_rejects_requests_routed_to_a_different_node(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDRA_NODE_ID", "node-local")
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/api/v1/profile",
            headers={**_v1_headers(), "X-Cloudra-Node-ID": "node-other"},
        )

    assert response.status_code == 409
    assert "unknown node" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_v1_session_creation_uses_server_workspace(monkeypatch, tmp_path):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    from cloudra.config import get_config

    monkeypatch.setattr(get_config(), "workspace_dir", tmp_path)
    service = FakeService()
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/conversations/conv_1/sessions",
            headers={
                **_v1_headers(),
                "Idempotency-Key": "cmd_create_api_12345678",
            },
            json={"query": "服务器执行", "workspace_id": "default"},
        )

    assert response.status_code == 202
    assert service.last_submit == {
        "query": "服务器执行",
        "conversation_id": "conv_1",
        "working_directory": str(tmp_path.resolve()),
        "yolo": False,
    }
    assert service.last_command_id == "cmd_create_api_12345678"
    assert service.last_route == ("node-local", "default")
    assert response.json()["command"]["state"] == "applied"


@pytest.mark.asyncio
async def test_v1_session_creation_routes_configured_node_workspace(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    workspace = tmp_path / "project-a"
    workspace.mkdir()
    registry_file = tmp_path / "nodes.json"
    registry_file.write_text(
        json.dumps(
            {
                "default_node_id": "login-a",
                "nodes": [
                    {
                        "node_id": "login-a",
                        "display_name": "HPC Login",
                        "workspaces": [
                            {
                                "workspace_id": "project-a",
                                "path": str(workspace),
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLOUDRA_NODE_REGISTRY_FILE", str(registry_file))
    service = FakeService()
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        nodes = await client.get("/api/v1/nodes", headers=_v1_headers())
        workspaces = await client.get(
            "/api/v1/workspaces",
            headers={**_v1_headers(), "X-Cloudra-Node-ID": "login-a"},
        )
        response = await client.post(
            "/api/v1/conversations/conv_1/sessions",
            headers={
                **_v1_headers(),
                "X-Cloudra-Node-ID": "login-a",
                "Idempotency-Key": "cmd_hpc_api_12345678",
            },
            json={"query": "运行计算", "workspace_id": "project-a"},
        )

    assert nodes.json()[0]["node_id"] == "login-a"
    assert workspaces.json()[0]["workspace_id"] == "project-a"
    assert response.status_code == 202
    assert service.last_submit["working_directory"] == str(workspace.resolve())
    assert service.last_route == ("login-a", "project-a")


@pytest.mark.asyncio
async def test_v1_message_and_interaction_commands(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    service = FakeService()
    service.pending_interactions = [
        {
            "interaction_id": "int_api_12345678",
            "session_id": "a-0_run_1",
            "prompt": "请选择方法",
            "state": "pending",
        }
    ]
    transport = httpx.ASGITransport(app=create_app(service))
    headers = {
        **_v1_headers(),
        "Idempotency-Key": "cmd_append_api_12345678",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        appended = await client.post(
            "/api/v1/sessions/a-0_run_1/messages",
            params={"conversation_id": "conv_1"},
            headers=headers,
            json={"content": "补充溶剂效应"},
        )
        pending = await client.get(
            "/api/v1/interactions",
            params={"conversation_id": "conv_1"},
            headers=_v1_headers(),
        )
        answered = await client.post(
            "/api/v1/interactions/int_api_12345678/response",
            params={"conversation_id": "conv_1"},
            headers={
                **_v1_headers(),
                "Idempotency-Key": "cmd_answer_api_12345678",
            },
            json={"response": "使用 SMD"},
        )

    assert appended.status_code == 202
    assert service.last_append["content"] == "补充溶剂效应"
    assert (
        service.last_append["command_id"]
        == "cmd_append_api_12345678"
    )
    assert pending.status_code == 200
    assert pending.json()[0]["interaction_id"] == "int_api_12345678"
    assert answered.status_code == 200
    assert answered.json()["response"] == "使用 SMD"
    assert service.last_command_id == "cmd_answer_api_12345678"


@pytest.mark.asyncio
async def test_v1_approval_decision_is_audited_command(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    service = FakeService()
    service.pending_approvals = [
        {
            "approval_id": 7,
            "conversation_id": "conv_1",
            "tool_name": "bashtools",
            "normalized_arguments": {"command": "rm output.tmp"},
            "risk_summary": "执行危险终端命令",
            "state": "pending",
        }
    ]
    transport = httpx.ASGITransport(app=create_app(service))
    headers = {
        **_v1_headers(),
        "Idempotency-Key": "cmd_approval_api_12345678",
    }
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        pending = await client.get(
            "/api/v1/approvals",
            params={"conversation_id": "conv_1"},
            headers=_v1_headers(),
        )
        decided = await client.post(
            "/api/v1/approvals/7/decision",
            params={"conversation_id": "conv_1"},
            headers=headers,
            json={
                "decision": "denied",
                "denial_reason": "路径过宽",
            },
        )

    assert pending.status_code == 200
    assert pending.json()[0]["tool_name"] == "bashtools"
    assert decided.status_code == 200
    assert decided.json()["state"] == "denied"
    assert decided.json()["command"]["state"] == "applied"
    assert service.last_approval == {
        "command_id": "cmd_approval_api_12345678",
        "conversation_id": "conv_1",
        "approval_id": 7,
        "decision": "denied",
        "denial_reason": "路径过宽",
    }


@pytest.mark.asyncio
async def test_v1_event_cursor_returns_only_newer_events(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    service = FakeService()
    rows = [
        {
            "id": 7,
            "event_type": "llm_chunk",
            "data": {"delta": "旧"},
            "created_at": "2026-07-29T00:00:00+00:00",
        },
        {
            "id": 8,
            "event_type": "tool_started",
            "data": {"tool": "text_reader"},
            "created_at": "2026-07-29T00:00:01+00:00",
        },
        {
            "id": 9,
            "event_type": "completed",
            "data": {"result": "完成"},
            "created_at": "2026-07-29T00:00:02+00:00",
        },
    ]
    service.session_runner.events = (
        lambda _conversation_id, _session_id, after_id=0: [
            row for row in rows if row["id"] > after_id
        ]
    )
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/conversations/conv_1/sessions/a-0_run_1/events",
            params={"after_cursor": 7},
            headers=_v1_headers(),
        )

    assert response.status_code == 200
    payload = response.json()
    assert [event["cursor"] for event in payload["events"]] == [8, 9]
    assert payload["events"][0]["type"] == "tool.started"
    assert payload["events"][1]["payload"]["event_type"] == "completed"
    assert payload["next_cursor"] == 9


@pytest.mark.asyncio
async def test_v1_sse_replays_terminal_event_and_closes(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    service = FakeService()
    terminal = {
        "id": 12,
        "event_type": "completed",
        "data": {"result": "离线期间完成"},
        "created_at": "2026-07-29T00:00:02+00:00",
    }
    service.session_runner.events = (
        lambda _conversation_id, _session_id, after_id=0: (
            [terminal] if after_id < terminal["id"] else []
        )
    )
    service.session_runner.get = lambda _conversation_id, _session_id: type(
        "Completed",
        (),
        {"state": "completed"},
    )()
    transport = httpx.ASGITransport(app=create_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            (
                "/api/v1/conversations/conv_1/sessions/"
                "a-0_run_1/events/stream"
            ),
            headers=_v1_headers(),
        )

    assert response.status_code == 200
    assert "id: 12" in response.text
    data_line = next(
        line for line in response.text.splitlines() if line.startswith("data:")
    )
    envelope = json.loads(data_line.removeprefix("data:").strip())
    assert envelope["cursor"] == 12
    assert envelope["payload"]["data"]["state"] == "completed"
    assert envelope["payload"]["data"]["result"] == "离线期间完成"
