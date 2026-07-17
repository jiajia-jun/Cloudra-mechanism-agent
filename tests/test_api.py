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

    def submit_session(self, query, conversation_id=None, working_directory=None, yolo=False):
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
    # frontend/dist 是构建产物、不入库；CI 检出中不存在，这里补一个最小副本
    # 验证"dist 存在则挂载"的逻辑本身（已存在真实 dist 时直接使用，不覆盖）。
    import shutil
    from pathlib import Path

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    created = False
    if not dist.is_dir():
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
        created = True
    try:
        app = create_app(FakeService())
        assert any(getattr(route, "path", None) == "" and getattr(route, "name", None) == "frontend" for route in app.routes)
    finally:
        if created:
            shutil.rmtree(dist, ignore_errors=True)


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
