import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloudra.config import reload_config
from cloudra.yolo_guard import (
    YoloGuard,
    _format_content,
    _format_recent_context_multimodal,
    is_yolo_enabled,
)


class TestIsYoloEnabled:
    def test_enabled_values(self, monkeypatch):
        for value in ("1", "true", "yes", "on", "TRUE", "True"):
            monkeypatch.setenv("CLOUDRA_YOLO_MODE", value)
            assert is_yolo_enabled() is True

    def test_disabled_values(self, monkeypatch):
        for value in ("0", "false", "no", "off", "", "False"):
            monkeypatch.setenv("CLOUDRA_YOLO_MODE", value)
            assert is_yolo_enabled() is False


class TestFormatContent:
    def test_text(self):
        assert _format_content("hello world") == "hello world"

    def test_list_with_text_and_image(self):
        content = [
            {"type": "text", "text": "看图"},
            {"type": "image_url", "image_url": {"url": "/path/to/img.png"}},
        ]
        result = _format_content(content)
        assert "看图" in result
        assert "[图片]" in result

    def test_dict(self):
        content = {"command": "ls -la"}
        result = _format_content(content)
        assert "ls -la" in result

    def test_truncation(self):
        long_text = "a" * 2000
        result = _format_content(long_text, max_len=100)
        assert result.endswith("...[截断]")
        assert len(result) == 100 + len("...[截断]")


class TestFormatRecentContext:
    @pytest.fixture
    def fake_agent(self, tmp_path):
        from cloudra.context_manager import ContextManager

        cm = ContextManager(
            agent_id="test-agent",
            conversation_id="test-conv",
            prompt="你是一个测试助手。",
            query="帮我分析数据",
        )
        cm.context_file = str(tmp_path / "context.json")

        agent = MagicMock()
        agent.context_manager = cm
        agent.name = "explorer"
        agent.query = "帮我分析数据"
        return agent

    @pytest.mark.asyncio
    async def test_format_recent_context(self, fake_agent):
        cm = fake_agent.context_manager
        await cm.append({"role": "user", "content": "你好"})
        await cm.append({"role": "assistant", "content": "我来帮你"})
        await cm.append({"role": "user", "content": "读取文件"})

        parts = await _format_recent_context_multimodal(fake_agent, limit=2)
        text = "".join([p.get("text", "") for p in parts if p.get("type") == "text"])
        assert "我来帮你" in text
        assert "读取文件" in text
        assert "你好" not in text  # 超过 limit 被截断


class TestYoloGuardJudge:
    @pytest.fixture
    def fake_agent(self):
        agent = MagicMock()
        agent.name = "explorer"
        agent.query = "帮我分析数据"
        agent.context_manager = None
        return agent

    @pytest.mark.asyncio
    async def test_judge_approved(self, fake_agent, monkeypatch):
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        reload_config()

        guard = YoloGuard()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.arguments = json.dumps(
            {"approved": True, "reason": "操作合理"}
        )
        mock_response.choices[0].message.tool_calls = [mock_tool_call]

        with patch.object(guard, "_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            approved, reason = await guard.judge(
                "text_reader",
                {"path": "/data.txt"},
                fake_agent,
                None,
            )

        assert approved is True
        assert "合理" in reason
        mock_client.return_value.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_judge_rejected(self, fake_agent, monkeypatch):
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        reload_config()

        guard = YoloGuard()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.arguments = json.dumps(
            {"approved": False, "reason": "超出任务范围"}
        )
        mock_response.choices[0].message.tool_calls = [mock_tool_call]

        with patch.object(guard, "_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            approved, reason = await guard.judge(
                "bashtools",
                {"command": "rm -rf /"},
                fake_agent,
                None,
            )

        assert approved is False
        assert "超出任务范围" in reason

    @pytest.mark.asyncio
    async def test_judge_invalid_json(self, fake_agent, monkeypatch):
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        reload_config()

        guard = YoloGuard()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.arguments = "这不是 JSON"
        mock_response.choices[0].message.tool_calls = [mock_tool_call]

        with patch.object(guard, "_client") as mock_client:
            mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
            approved, reason = await guard.judge(
                "text_writer",
                {"path": "/x.txt", "content": "hello"},
                fake_agent,
                None,
            )

        assert approved is False
        assert "结构提取失败" in reason

    def test_missing_env(self, fake_agent, monkeypatch):
        monkeypatch.delenv("FOLLOWER_MODEL", raising=False)
        monkeypatch.delenv("FOLLOWER_URL", raising=False)
        monkeypatch.delenv("FOLLOWER_KEY", raising=False)

        mock_cfg = MagicMock()
        mock_cfg.follower.model = ""
        mock_cfg.follower.url = ""
        mock_cfg.follower.key = ""

        with patch("cloudra.yolo_guard.get_config", return_value=mock_cfg):
            guard = YoloGuard()
            with pytest.raises(RuntimeError):
                guard._client()
