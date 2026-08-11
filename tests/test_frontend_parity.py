"""前端对齐 CLI 功能的 API 测试：config、logs、sessions 聚合、按 Session 的 YOLO。"""

import httpx
import pytest

from cloudra.infra.config import get_config
from cloudra.services.api import create_app
from cloudra.services.service import SessionRecord


class _Record:
    session_id = "a-0_run_1"

    def to_dict(self):
        return {"session_id": self.session_id, "state": "queued"}


def _session_record(session_id, state="completed", created_at="2026-01-01T00:00:00+00:00"):
    return SessionRecord(
        session_id=session_id,
        agent_id="a-0",
        agent_type="coordinator",
        parent_session_id=None,
        query="q",
        state=state,
        result=None,
        error=None,
        pid=None,
        worker_id=None,
        created_at=created_at,
        started_at=None,
        heartbeat_at=None,
        finished_at=None,
        exit_code=None,
    )


class FakeService:
    def __init__(self):
        self.submitted = []
        self.conversations = []
        self.sessions_by_conv = {}
        self.session_runner = self._SessionRunner(self)

    class _SessionRunner:
        def __init__(self, outer):
            self.outer = outer

        def get(self, conversation_id, session_id):
            return None

        def list(self, conversation_id):
            return self.outer.sessions_by_conv.get(conversation_id, [])

        def cancel(self, conversation_id, session_id):
            return None

    def create_conversation(self):
        return type("Conversation", (), {"id": "conv_1", "state": "active"})()

    def submit_session(
        self,
        query,
        conversation_id=None,
        working_directory=None,
        yolo=False,
        orchestration_mode="standard",
    ):
        mode_value = getattr(orchestration_mode, "value", str(orchestration_mode))
        self.submitted.append({
            "query": query,
            "conversation_id": conversation_id,
            "yolo": yolo,
            "orchestration_mode": mode_value,
        })
        return conversation_id, _Record()

    def list_conversations(self):
        return self.conversations

    def get_conversation_messages(self, conversation_id):
        return []

    async def list_pending_approvals(self):
        return []

    async def decide_approval(self, *args, **kwargs):
        return False


def _client(service):
    transport = httpx.ASGITransport(app=create_app(service))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


class TestYoloFlag:
    @pytest.mark.asyncio
    async def test_session_create_passes_yolo(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        service = FakeService()
        async with _client(service) as client:
            await client.post("/api/conversations/conv_1/sessions", json={"query": "hi", "yolo": True})
            await client.post("/api/conversations/conv_1/sessions", json={"query": "hi"})
        assert service.submitted[0]["yolo"] is True
        assert service.submitted[1]["yolo"] is False

    def test_session_level_yolo_contextvar(self, monkeypatch):
        from cloudra.infra.yolo_guard import is_yolo_enabled, set_session_yolo

        monkeypatch.delenv("CLOUDRA_YOLO_MODE", raising=False)
        assert not is_yolo_enabled()
        token = set_session_yolo(True)
        assert is_yolo_enabled()
        token.var.reset(token)
        assert not is_yolo_enabled()
        # 环境变量回落（CLI 进程级路径）不受影响
        monkeypatch.setenv("CLOUDRA_YOLO_MODE", "true")
        assert is_yolo_enabled()

    def test_submit_session_threads_yolo(self, monkeypatch):
        """SessionRunner.submit 应把 yolo 参数原样传给 _execute 协程。"""
        import asyncio

        from cloudra.services.service import SessionRunner

        class _FakeConn:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, *args):
                return self

            def commit(self):
                pass

        class _FakeDB:
            def __init__(self, *args):
                pass

            def init(self):
                return self

            def connect(self):
                return _FakeConn()

        monkeypatch.setattr("cloudra.services.service.ConversationDB", _FakeDB)
        captured = {}

        runner = SessionRunner.__new__(SessionRunner)
        runner._running = {}
        runner._emit = lambda *args, **kwargs: None
        runner.get = lambda *args: None

        async def fake_execute(
            query,
            conversation_id,
            session_id,
            working_directory=None,
            yolo=False,
            orchestration_mode="standard",
            orchestration_config=None,
        ):
            captured["yolo"] = yolo

        runner._execute = fake_execute

        async def run():
            runner.submit("q", "conv_yolo", yolo=True)
            await asyncio.gather(*runner._running.values())

        asyncio.run(run())
        assert captured["yolo"] is True


class TestOrchestrationMode:
    @pytest.mark.asyncio
    async def test_api_passes_explicit_mode_and_defaults_to_standard(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        service = FakeService()
        async with _client(service) as client:
            guided = await client.post(
                "/api/conversations/conv_1/sessions",
                json={"query": "mechanism", "orchestration_mode": "dag_guided"},
            )
            ordinary = await client.post(
                "/api/conversations/conv_1/sessions",
                json={"query": "ordinary"},
            )
        assert guided.status_code == 202
        assert ordinary.status_code == 202
        assert service.submitted[0]["orchestration_mode"] == "dag_guided"
        assert service.submitted[1]["orchestration_mode"] == "standard"

    @pytest.mark.asyncio
    async def test_api_rejects_unknown_orchestration_mode(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        async with _client(FakeService()) as client:
            response = await client.post(
                "/api/conversations/conv_1/sessions",
                json={"query": "mechanism", "orchestration_mode": "on"},
            )
        assert response.status_code == 422


class TestConfigApi:
    @pytest.mark.asyncio
    async def test_get_config_masks_keys(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        cfg = get_config()
        monkeypatch.setattr(cfg.coordinator, "key", "sk-real-secret-value")
        async with _client(FakeService()) as client:
            response = await client.get("/api/config")
        assert response.status_code == 200
        body = response.json()
        assert body["llm"]["coordinator"]["key"] == "***"
        assert "sk-real-secret-value" not in response.text

    @pytest.mark.asyncio
    async def test_set_config_value(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        cfg = get_config()
        monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
        monkeypatch.setattr(cfg.coordinator, "model", "orig-model")
        monkeypatch.setattr(cfg.coordinator, "supports_vision", False)
        async with _client(FakeService()) as client:
            response = await client.post(
                "/api/config/set", json={"key": "coordinator.model", "value": "new-model"}
            )
            assert response.status_code == 200
            assert cfg.coordinator.model == "new-model"
            # 布尔 coercion
            response = await client.post(
                "/api/config/set", json={"key": "coordinator.supports_vision", "value": "true"}
            )
            assert response.status_code == 200
            assert cfg.coordinator.supports_vision is True
            # 非法布尔
            response = await client.post(
                "/api/config/set", json={"key": "coordinator.supports_vision", "value": "maybe"}
            )
            assert response.status_code == 422
            # 未知 key
            response = await client.post("/api/config/set", json={"key": "nope", "value": "x"})
            assert response.status_code == 422
        # 落盘文件应包含新模型名
        assert "new-model" in (tmp_path / "config.yaml").read_text(encoding="utf-8")

    def test_set_config_value_fallback_resolution(self, tmp_path, monkeypatch):
        """与 CLI 一致的三级回退：裸 key 依次尝试原样 → coordinator. → follower.。"""
        from cloudra.infra.config import set_config_value

        cfg = get_config()
        monkeypatch.setattr(cfg, "config_file", tmp_path / "config.yaml")
        monkeypatch.setattr(cfg.coordinator, "url", "https://orig-coord/")
        monkeypatch.setattr(cfg.follower, "url", "https://orig-follower/")
        set_config_value("url", "https://new/")
        # coordinator.url 先于 follower.url 命中
        assert cfg.coordinator.url == "https://new/"
        assert cfg.follower.url == "https://orig-follower/"
        with pytest.raises(ValueError):
            set_config_value("nonexistent_key", "x")


@pytest.mark.asyncio
class TestLogsApi:
    async def test_logs_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        cfg = get_config()
        monkeypatch.setattr(cfg, "data_dir", tmp_path)
        log_dir = tmp_path / "conversations" / "conv_log" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "a-0").write_text("第一行\n第二行", encoding="utf-8")
        async with _client(FakeService()) as client:
            response = await client.get("/api/conversations/conv_log/logs")
        assert response.status_code == 200
        logs = response.json()
        assert len(logs) == 1
        assert logs[0]["name"] == "a-0"
        assert "第一行" in logs[0]["content"]
        assert logs[0]["truncated"] is False

    async def test_logs_missing_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        monkeypatch.setattr(get_config(), "data_dir", tmp_path)
        async with _client(FakeService()) as client:
            response = await client.get("/api/conversations/conv_none/logs")
        assert response.status_code == 200
        assert response.json() == []

    async def test_logs_rejects_bad_id(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        monkeypatch.setattr(get_config(), "data_dir", tmp_path)
        async with _client(FakeService()) as client:
            response = await client.get("/api/conversations/bad%20id!/logs")
        assert response.status_code == 422


@pytest.mark.asyncio
class TestSessionsAggregate:
    async def test_aggregates_and_filters(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        service = FakeService()
        service.conversations = [{"id": "conv_1"}, {"id": "conv_2"}]
        service.sessions_by_conv = {
            "conv_1": [_session_record("s-old", "completed", "2026-01-01T00:00:00+00:00")],
            "conv_2": [_session_record("s-new", "running", "2026-01-02T00:00:00+00:00")],
        }
        async with _client(service) as client:
            response = await client.get("/api/sessions")
            assert response.status_code == 200
            rows = response.json()
            assert [row["session_id"] for row in rows] == ["s-new", "s-old"]
            assert rows[0]["conversation_id"] == "conv_2"
            response = await client.get("/api/sessions", params={"state": "running"})
            rows = response.json()
            assert len(rows) == 1 and rows[0]["session_id"] == "s-new"

    async def test_skips_invalid_conversation_ids(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        service = FakeService()
        service.conversations = [{"id": "bad id!"}, {"id": "conv_ok"}]
        service.sessions_by_conv = {"conv_ok": [_session_record("s-1")]}
        async with _client(service) as client:
            response = await client.get("/api/sessions")
        assert response.status_code == 200
        assert [row["session_id"] for row in response.json()] == ["s-1"]


@pytest.mark.asyncio
class TestDagUserMutationApi:
    """用户经 API 编辑 DAG：POST /api/conversations/{id}/dag/mutations。"""

    async def test_mutation_request_is_forwarded_and_returned(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        service = FakeService()
        captured = {}

        def fake_apply(conversation_id, operations, base_revisions, rationale=""):
            captured.update(
                conversation_id=conversation_id,
                operations=operations,
                base_revisions=base_revisions,
                rationale=rationale,
            )
            return {
                "accepted": True,
                "revisions": {"process": 1, "delivery": 0},
                "rejection_code": None,
            }

        service.dag_apply_user_mutation = fake_apply
        operations = [
            {
                "op": "update_node",
                "graph": "process",
                "data": {"node_id": "w1", "changes": {"status": "skipped", "reason": "用户跳过"}},
            }
        ]
        async with _client(service) as client:
            response = await client.post(
                "/api/conversations/conv_1/dag/mutations",
                json={
                    "operations": operations,
                    "base_revisions": {"process": 0, "delivery": 0},
                    "rationale": "manual skip",
                },
            )
        assert response.status_code == 200
        assert response.json()["accepted"] is True
        assert captured["operations"] == operations
        assert captured["base_revisions"] == {"process": 0, "delivery": 0}
        assert captured["rationale"] == "manual skip"

    async def test_mutation_returns_404_without_bundle(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        service = FakeService()
        service.dag_apply_user_mutation = lambda *args, **kwargs: None
        async with _client(service) as client:
            response = await client.post(
                "/api/conversations/conv_none/dag/mutations",
                json={
                    "operations": [],
                    "base_revisions": {"process": 0, "delivery": 0},
                },
            )
        assert response.status_code == 404

    async def test_mutation_validation_error_is_422(self, monkeypatch):
        monkeypatch.delenv("CLOUDRA_API_TOKEN", raising=False)
        service = FakeService()

        def fake_apply(*args, **kwargs):
            raise ValueError("invalid_operation: bad op")

        service.dag_apply_user_mutation = fake_apply
        async with _client(service) as client:
            response = await client.post(
                "/api/conversations/conv_1/dag/mutations",
                json={
                    "operations": [{"op": "nope"}],
                    "base_revisions": {"process": 0, "delivery": 0},
                },
            )
        assert response.status_code == 422
