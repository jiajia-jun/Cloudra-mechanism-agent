import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cloudra.infra.config import _reset_for_tests
from cloudra.infra.yolo_guard import (
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
        from cloudra.core.message_history import JsonlMessageHistory

        cm = JsonlMessageHistory(
            conversation_id="test-conv",
            agent_id="test-agent",
            initial_query="帮我分析数据",
            context_file=str(tmp_path / "context.json"),
        )

        agent = MagicMock()
        agent.message_history = cm
        agent.name = "explorer"
        agent.query = "帮我分析数据"
        return agent

    @pytest.mark.asyncio
    async def test_format_recent_context(self, fake_agent):
        cm = fake_agent.message_history
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
        agent.message_history = None
        return agent

    @pytest.mark.asyncio
    async def test_judge_approved(self, fake_agent, monkeypatch):
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        _reset_for_tests()

        guard = YoloGuard()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.arguments = json.dumps(
            {"approved": True, "reason": "操作合理"}
        )
        mock_response.choices[0].message.tool_calls = [mock_tool_call]

        with patch.object(guard, "_client") as mock_client:
            mock_client.return_value.create = AsyncMock(return_value=mock_response)
            approved, reason = await guard.judge(
                "text_reader",
                {"path": "/data.txt"},
                fake_agent,
                None,
            )

        assert approved is True
        assert "合理" in reason
        mock_client.return_value.create.assert_called_once()
        assert "tool_choice" not in mock_client.return_value.create.call_args.kwargs

    @pytest.mark.asyncio
    async def test_guard_prompt_is_reloaded_for_each_judgement(
        self,
        fake_agent,
        monkeypatch,
    ):
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        _reset_for_tests()

        guard = YoloGuard()
        response = MagicMock()
        tool_call = MagicMock()
        tool_call.function.arguments = json.dumps(
            {"approved": True, "reason": "放行"}
        )
        response.choices[0].message.tool_calls = [tool_call]

        with (
            patch.object(guard, "_client") as mock_client,
            patch(
                "cloudra.infra.yolo_guard._load_prompt",
                side_effect=["第一版安全策略", "第二版安全策略"],
            ),
        ):
            create = AsyncMock(return_value=response)
            mock_client.return_value.create = create
            await guard.judge("text_reader", {"path": "a"}, fake_agent, None)
            await guard.judge("text_reader", {"path": "b"}, fake_agent, None)

        first_messages = create.call_args_list[0].kwargs["messages"]
        second_messages = create.call_args_list[1].kwargs["messages"]
        assert first_messages[0]["content"] == "第一版安全策略"
        assert second_messages[0]["content"] == "第二版安全策略"

    @pytest.mark.asyncio
    async def test_judge_rejected(self, fake_agent, monkeypatch):
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        _reset_for_tests()

        guard = YoloGuard()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.arguments = json.dumps(
            {"approved": False, "reason": "超出任务范围"}
        )
        mock_response.choices[0].message.tool_calls = [mock_tool_call]

        with patch.object(guard, "_client") as mock_client:
            mock_client.return_value.create = AsyncMock(return_value=mock_response)
            approved, reason = await guard.judge(
                "bash",
                {"command": "rm -rf /"},
                fake_agent,
                None,
            )

        assert approved is False
        assert "超出任务范围" in reason

    @pytest.mark.asyncio
    async def test_judge_invalid_json(self, fake_agent, monkeypatch):
        """tool_call 参数无法解析时由 Guard 内部重试，耗尽后默认拒绝，
        且拒绝原因不向主 Agent 暴露实现细节。"""
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        _reset_for_tests()

        guard = YoloGuard()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.arguments = "这不是 JSON"
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.choices[0].message.content = ""

        with patch.object(guard, "_client") as mock_client:
            create = AsyncMock(return_value=mock_response)
            mock_client.return_value.create = create
            approved, reason = await guard.judge(
                "write",
                {"path": "/x.txt", "content": "hello"},
                fake_agent,
                None,
            )

        assert approved is False
        assert create.call_count == guard._MAX_ATTEMPTS
        assert "结构提取失败" not in reason
        assert "tool_call" not in reason
        assert "默认安全策略拒绝" in reason

    @pytest.mark.asyncio
    async def test_judge_retry_after_missing_tool_call(self, fake_agent, monkeypatch):
        """首次未返回 tool_call 时，Guard 应自行纠正模型并重试，主 Agent 无感知。"""
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        _reset_for_tests()

        guard = YoloGuard()

        bad_response = MagicMock()
        bad_response.choices[0].message.tool_calls = []
        bad_response.choices[0].message.content = "我觉得这个操作没问题"

        good_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.arguments = json.dumps({"approved": True, "reason": "放行"})
        good_response.choices[0].message.tool_calls = [mock_tool_call]

        with patch.object(guard, "_client") as mock_client:
            create = AsyncMock(side_effect=[bad_response, good_response])
            mock_client.return_value.create = create
            approved, reason = await guard.judge(
                "write",
                {"path": "/x.txt", "content": "hello"},
                fake_agent,
                None,
            )

        assert approved is True
        assert reason == "放行"
        assert create.call_count == 2
        # 第二次请求应带上纠正对话：assistant 的错误回复 + 要求重新提交的用户消息
        messages = create.call_args_list[1].kwargs["messages"]
        assert len(messages) == 4
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "我觉得这个操作没问题"
        assert messages[3]["role"] == "user"
        assert "submit_approval_decision" in messages[3]["content"]

    @pytest.mark.asyncio
    async def test_judge_fallback_chain(self, fake_agent, monkeypatch):
        """temperature=1 重试再遇 tool_choice/thinking 400 时，应继续降级到不强制 tool_choice。"""
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        _reset_for_tests()

        guard = YoloGuard()
        mock_response = MagicMock()
        mock_tool_call = MagicMock()
        mock_tool_call.function.arguments = json.dumps({"approved": True, "reason": "放行"})
        mock_response.choices[0].message.tool_calls = [mock_tool_call]

        create = AsyncMock(side_effect=[
            Exception("Error code: 400 - only 1 is allowed for temperature"),
            mock_response,
        ])
        with patch.object(guard, "_client") as mock_client:
            mock_client.return_value.create = create
            approved, reason = await guard.judge(
                "write",
                {"path": "/x.txt", "content": "hello"},
                fake_agent,
                None,
            )

        assert approved is True
        assert "放行" in reason
        assert create.call_count == 2
        assert create.call_args_list[1].kwargs["temperature"] == 1.0
        assert "tool_choice" not in create.call_args_list[1].kwargs

    @pytest.mark.asyncio
    async def test_judge_fallback_exhausted(self, fake_agent, monkeypatch):
        """全部变体都失败时返回拒绝并说明原因（安全侧失败）。"""
        monkeypatch.setenv("FOLLOWER_MODEL", "test-model")
        monkeypatch.setenv("FOLLOWER_URL", "http://localhost")
        monkeypatch.setenv("FOLLOWER_KEY", "test-key")
        _reset_for_tests()

        guard = YoloGuard()
        create = AsyncMock(side_effect=Exception("Error code: 400 - tool_choice 'specified' is incompatible with thinking enabled"))
        with patch.object(guard, "_client") as mock_client:
            mock_client.return_value.create = create
            approved, reason = await guard.judge(
                "write",
                {"path": "/x.txt", "content": "hello"},
                fake_agent,
                None,
            )

        assert approved is False
        assert "全部降级重试失败" in reason
        assert create.call_count == 2

    def test_missing_env(self, fake_agent, monkeypatch):
        monkeypatch.delenv("FOLLOWER_MODEL", raising=False)
        monkeypatch.delenv("FOLLOWER_URL", raising=False)
        monkeypatch.delenv("FOLLOWER_KEY", raising=False)

        mock_cfg = MagicMock()
        mock_cfg.follower.model = ""
        mock_cfg.follower.url = ""
        mock_cfg.follower.key = ""

        with patch("cloudra.infra.yolo_guard.get_config", return_value=mock_cfg):
            guard = YoloGuard()
            with pytest.raises(RuntimeError):
                guard._client()


class TestEnsureSafetyYoloRoute:
    """危险工具的 ensure_safety 在 YOLO 开启时走 Guard，不进人工审批。"""

    @pytest.mark.asyncio
    async def test_yolo_on_calls_guard_not_human_approval(self, monkeypatch):
        from cloudra.base.tools_class import Tool
        from cloudra.infra.yolo_guard import reset_session_yolo, set_session_yolo

        monkeypatch.delenv("CLOUDRA_YOLO_MODE", raising=False)
        tool = Tool(tool_name="bash")
        tool.subagent = MagicMock(name="explorer")
        tool.subagent.name = "explorer"
        session = MagicMock()

        judged = {}

        async def fake_judge(self, tool_name, tool_args, agent, session):
            judged["call"] = (tool_name, tool_args)
            return True, "操作合理"

        monkeypatch.setattr("cloudra.infra.yolo_guard.YoloGuard.judge", fake_judge)
        approval_called = []

        async def fake_approval(*_args, **_kwargs):
            approval_called.append(True)
            return False, "不应走到人工审批"

        monkeypatch.setattr(Tool, "request_approval", fake_approval)

        token = set_session_yolo(True)
        try:
            ok, reason = await tool.ensure_safety(
                session,
                details="【动作】: 执行危险终端命令\n【执行指令】: rm -rf /tmp/x",
                tool_args={"command": "rm -rf /tmp/x"},
            )
        finally:
            reset_session_yolo(token)

        assert ok is True
        assert reason == ""
        assert judged["call"] == ("bash", {"command": "rm -rf /tmp/x"})
        assert approval_called == []

    @pytest.mark.asyncio
    async def test_yolo_off_does_not_call_guard(self, monkeypatch):
        from cloudra.base.tools_class import Tool
        from cloudra.infra.yolo_guard import is_yolo_enabled

        monkeypatch.delenv("CLOUDRA_YOLO_MODE", raising=False)
        assert is_yolo_enabled() is False

        tool = Tool(tool_name="bash")
        tool.subagent = MagicMock()
        tool.subagent.name = "explorer"
        tool.subagent.conversation_id = "test-conv"
        session = MagicMock()
        session.id = "s-1"

        guard_called = []

        async def fake_judge(self, *_args, **_kwargs):
            guard_called.append(True)
            return True, "不应调用"

        monkeypatch.setattr("cloudra.infra.yolo_guard.YoloGuard.judge", fake_judge)

        async def fake_approval(*_args, **_kwargs):
            return True, ""

        monkeypatch.setattr(Tool, "request_approval", fake_approval)

        ok, reason = await tool.ensure_safety(
            session,
            details="【动作】: 执行危险终端命令",
            tool_args={"command": "rm file"},
        )
        assert ok is True
        assert guard_called == []
