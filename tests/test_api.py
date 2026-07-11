import httpx
import pytest

from cloudra.api import create_app


class _Record:
    session_id = "a-0_run_1"

    def to_dict(self):
        return {"session_id": self.session_id, "state": "queued"}


class _SessionRunner:
    def get(self, conversation_id, session_id):
        return None

    def list(self, conversation_id):
        return []

    def cancel(self, conversation_id, session_id):
        return None


class FakeService:
    def __init__(self):
        self.session_runner = _SessionRunner()

    def create_conversation(self):
        return type("Conversation", (), {"id": "conv_1", "state": "active"})()

    def submit_session(self, query, conversation_id=None):
        return conversation_id, _Record()

    def list_conversations(self):
        return []

    def get_conversation_messages(self, conversation_id):
        return []

    async def list_pending_approvals(self):
        return []

    async def decide_approval(self, *args, **kwargs):
        return False


@pytest.mark.asyncio
async def test_health_is_public(monkeypatch):
    monkeypatch.setenv("CLOUDRA_API_TOKEN", "secret")
    transport = httpx.ASGITransport(app=create_app(FakeService()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200


def test_frontend_is_mounted(monkeypatch):
    monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
    app = create_app(FakeService())
    assert any(getattr(route, "path", None) == "" and getattr(route, "name", None) == "frontend" for route in app.routes)


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
