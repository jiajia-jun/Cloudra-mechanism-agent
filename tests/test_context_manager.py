from unittest.mock import patch

import pytest

from cloudra.context_manager import ContextManager


@pytest.fixture
def context_manager(tmp_path):
    """提供一个使用临时目录的 ContextManager 实例。"""
    cm = ContextManager(
        agent_id="test-agent",
        conversation_id="test-conv",
        prompt="你是一个测试助手。",
        query="初始问题",
    )
    cm.context_file = str(tmp_path / "context.json")
    return cm


@pytest.fixture
def make_image(tmp_path):
    """工厂：创建指定名称的占位 PNG 文件，返回其绝对路径。"""
    def _make(name: str) -> str:
        path = tmp_path / name
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return str(path)
    return _make


class TestContextManagerRender:
    """测试 ContextManager 的消息渲染与视觉历史窗口。"""

    @pytest.mark.asyncio
    async def test_vision_encoding(self, context_manager, make_image):
        """视觉开启时，图片应被编码为 base64 data URL。"""
        img_path = make_image("test.png")
        await context_manager.append({
            "role": "user",
            "content": "看图",
            "image_path": img_path,
        })

        msgs = await context_manager.build_messages(supports_vision=True)
        last = msgs[-1]
        assert last["role"] == "user"
        assert isinstance(last["content"], list)
        image_part = last["content"][1]
        assert image_part["type"] == "image_url"
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")

    @pytest.mark.asyncio
    async def test_vision_fallback(self, context_manager, make_image):
        """视觉关闭时，图片应降级为文本占位符。"""
        img_path = make_image("test.png")
        await context_manager.append({
            "role": "user",
            "content": "看图",
            "image_path": img_path,
        })

        msgs = await context_manager.build_messages(supports_vision=False)
        last = msgs[-1]
        assert isinstance(last["content"], str)
        assert "当前模型不支持视觉" in last["content"]

    @pytest.mark.asyncio
    async def test_no_duplicate_system_prompt(self, context_manager, make_image):
        """system prompt 不应重复出现。"""
        img_path = make_image("test.png")
        await context_manager.append({
            "role": "user",
            "content": "看图",
            "image_path": img_path,
        })

        msgs = await context_manager.build_messages(supports_vision=True)
        roles = [m["role"] for m in msgs]
        assert roles.count("system") == 1

    @pytest.mark.asyncio
    async def test_vision_history_window(self, context_manager, make_image):
        """只有最近 N 轮用户消息中的图片保留多模态，更早的降级为文本。"""
        # 构造 7 轮 user/assistant 对话，每轮 user 带一张图
        for i in range(1, 8):
            img_path = make_image(f"img{i}.png")
            await context_manager.append({
                "role": "user",
                "content": f"第{i}张图",
                "image_path": img_path,
            })
            await context_manager.append({
                "role": "assistant",
                "content": f"这是第{i}张图的回复",
            })

        msgs = await context_manager.build_messages(
            supports_vision=True, vision_history_limit=5
        )

        image_urls = [
            part["image_url"]["url"]
            for msg in msgs
            if isinstance(msg.get("content"), list)
            for part in msg["content"]
            if part.get("type") == "image_url"
        ]
        text_placeholders = [
            part["text"]
            for msg in msgs
            if isinstance(msg.get("content"), list)
            for part in msg["content"]
            if part.get("type") == "text" and part.get("text", "").startswith("[图片:")
        ]

        assert len(image_urls) == 5
        assert len(text_placeholders) == 2

    @pytest.mark.asyncio
    async def test_missing_image(self, context_manager):
        """图片路径不存在时，应降级为缺失提示。"""
        await context_manager.append({
            "role": "user",
            "content": "看图",
            "image_path": "/nonexistent/image.png",
        })

        msgs = await context_manager.build_messages(supports_vision=True)
        last = msgs[-1]
        text_parts = [p["text"] for p in last["content"] if p.get("type") == "text"]
        assert any("图片缺失" in t for t in text_parts)

    @pytest.mark.asyncio
    async def test_token_compression(self, context_manager, monkeypatch):
        """当历史消息超过 token 预算时，用 LLM 梗概替换历史，保留最近 10 轮。"""

        # 构造 12 轮较早对话 + 2 轮最近对话
        for i in range(12):
            await context_manager.append({
                "role": "user",
                "content": f"历史问题 {i}: " + "这是历史消息。" * 30,
            })
            await context_manager.append({
                "role": "assistant",
                "content": f"历史回复 {i}: " + "这是历史回复。" * 30,
            })

        for i in range(2):
            await context_manager.append({
                "role": "user",
                "content": f"最近问题 {i}: " + "这是最近消息。" * 10,
            })
            await context_manager.append({
                "role": "assistant",
                "content": f"最近回复 {i}: " + "这是最近回复。" * 10,
            })

        # 预算足够保留最近 10 轮但不够保留完整历史
        with patch.object(context_manager, "_summarize_history", side_effect=RuntimeError("mock failure")):
            msgs = await context_manager.build_messages(
                supports_vision=True,
                max_context_tokens=3000,
            )

        # 由于梗概生成失败，应回退到原始消息
        # 这个测试主要验证：不删除历史、不兜底、最近 10 轮保留
        assert any(m.get("role") == "system" for m in msgs)
        assistant_contents = [
            str(m.get("content", "")) for m in msgs if m.get("role") == "assistant"
        ]
        assert any("最近回复 1" in c for c in assistant_contents)
        assert any("历史回复 0" in c for c in assistant_contents)


class TestRepairDanglingToolCalls:
    """悬挂 tool_calls 修补：被打断的会话不能让后续请求全部 400。"""

    @pytest.mark.asyncio
    async def test_dangling_tool_call_gets_synthetic_response(self, context_manager):
        await context_manager.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "text_writer", "arguments": "{}"}},
            {"id": "call_2", "type": "function", "function": {"name": "bashtools", "arguments": "{}"}},
        ]})
        # call_1 有响应，call_2 悬挂
        await context_manager.append({"role": "tool", "tool_call_id": "call_1", "content": "ok"})

        messages = await context_manager.build_messages()
        answered = {
            msg["tool_call_id"] for msg in messages if msg.get("role") == "tool"
        }
        assert "call_2" in answered
        synthetic = [m for m in messages if m.get("tool_call_id") == "call_2"]
        assert len(synthetic) == 1
        assert "打断" in synthetic[0]["content"]

        # 不变式：每个 assistant 的 tool_call 都有响应（端点 400 的充要条件）
        for msg in messages:
            if msg.get("role") == "assistant":
                for call in msg.get("tool_calls") or []:
                    assert call["id"] in answered

        # 幂等：真实响应不会被覆盖/重复补
        real = [m for m in messages if m.get("tool_call_id") == "call_1"]
        assert len(real) == 1 and real[0]["content"] == "ok"


class TestCapMessageSizes:
    """单条巨型消息（如整份 PDF 乱码文本）必须在渲染期截断，防止上下文爆炸。"""

    @pytest.mark.asyncio
    async def test_giant_tool_message_capped(self, context_manager):
        giant = "%PDF-1.3 乱码" * 20000  # ~180k 字符
        await context_manager.append({"role": "tool", "tool_call_id": "c1", "content": giant})
        await context_manager.append({"role": "user", "content": "短消息"})

        messages = await context_manager.build_messages()
        tool_msg = next(m for m in messages if m.get("role") == "tool")
        assert len(tool_msg["content"]) < 50_000
        assert "已截断" in tool_msg["content"]
        assert "原始共" in tool_msg["content"]
        user_msg = next(m for m in messages if m.get("content") == "短消息")
        assert user_msg["content"] == "短消息"

    @pytest.mark.asyncio
    async def test_system_message_not_capped(self, context_manager):
        # system 消息（身份 prompt）不受硬顶影响
        long_prompt = "长提示 " * 30000
        cm = context_manager
        await cm.replace([
            {"role": "system", "content": long_prompt},
            {"role": "user", "content": "hi"},
        ])
        messages = await cm.build_messages()
        assert messages[0]["content"] == long_prompt


class TestHistoryCompression:
    """LLM 历史压缩路径（_compress_to_budget / _summarize_history）钉板测试。

    LLMClient 全部 mock，钉住：
    1. 触发条件：估算总 token > max_context_tokens 才触发。
    2. 替换方式：system 消息 + 梗概消息 + 最近 10 轮（以 assistant 计数）原样保留。
    3. 兜底：LLM 失败 / 缺配置 / 梗概仍超预算 时保留原始消息不压缩。
    """

    @pytest.fixture
    def mock_llm(self, monkeypatch):
        """mock LLMClient 与 FOLLOWER 配置，返回 (LLMClient 类 mock, create mock)。"""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from cloudra.config import get_config

        follower = get_config().follower
        monkeypatch.setattr(follower, "model", "fake-model")
        monkeypatch.setattr(follower, "url", "http://fake-llm")
        monkeypatch.setattr(follower, "key", "fake-key")

        create = AsyncMock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="压缩梗概"))]
        ))
        with patch("cloudra.context_manager.LLMClient") as mock_cls:
            mock_cls.return_value.create = create
            yield mock_cls, create

    @staticmethod
    async def _fill_history(cm, long_rounds=12, recent_rounds=10):
        """填充 long_rounds 轮长历史 + recent_rounds 轮短近期对话。"""
        for i in range(long_rounds):
            await cm.append({"role": "user", "content": f"历史问题 {i}: " + "这是历史消息。" * 30})
            await cm.append({"role": "assistant", "content": f"历史回复 {i}: " + "这是历史回复。" * 30})
        for i in range(recent_rounds):
            await cm.append({"role": "user", "content": f"最近问题 {i}: 短"})
            await cm.append({"role": "assistant", "content": f"最近回复 {i}: 短"})

    @pytest.mark.asyncio
    async def test_no_compression_under_budget(self, context_manager, mock_llm):
        """总 token 不超过预算时不触发压缩，也不调用 LLM。"""
        _, create = mock_llm
        await self._fill_history(context_manager, long_rounds=1, recent_rounds=1)

        msgs = await context_manager.build_messages(max_context_tokens=100_000)

        create.assert_not_called()
        contents = [str(m.get("content", "")) for m in msgs]
        assert any("历史问题 0" in c for c in contents)

    @pytest.mark.asyncio
    async def test_compression_replaces_history_with_summary(self, context_manager, mock_llm):
        """超预算时：历史被梗概替换，system 与最近 10 轮保留。"""
        mock_cls, create = mock_llm
        await self._fill_history(context_manager)

        msgs = await context_manager.build_messages(max_context_tokens=1000)

        # LLM 被调用一次，使用 FOLLOWER 配置与固定参数
        assert create.call_count == 1
        kwargs = create.call_args.kwargs
        assert kwargs["model"] == "fake-model"
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 2000
        # 梗概输入只包含历史（含初始 query），不包含保留的最近轮次。
        # 注意边界现状：保留窗口以第 10 条 assistant 为锚点截断，该轮对应的
        # user 消息（"最近问题 0"）被划入历史而非保留区。
        summary_prompt = kwargs["messages"][1]["content"]
        assert kwargs["messages"][0] == {"role": "system", "content": "你是一个专门压缩对话历史的助手。"}
        assert "历史问题 0" in summary_prompt
        assert "初始问题" in summary_prompt
        assert "最近问题 0" in summary_prompt  # 第 10 轮的 user 消息被划入历史
        assert "最近问题 1" not in summary_prompt

        # 结构：原 system prompt + 梗概 system 消息 + 保留尾部（19 条，
        # 从第 10 条 assistant "最近回复 0" 开始，其 user 消息不在其中）
        assert len(msgs) == 21
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "你是一个测试助手。"
        assert msgs[1]["role"] == "system"
        assert msgs[1]["content"].startswith("[上下文压缩提示]")
        assert "压缩梗概" in msgs[1]["content"]
        # 历史不再出现，保留区完整
        contents = [str(m.get("content", "")) for m in msgs]
        assert not any("历史问题 0" in c for c in contents)
        assert not any("最近问题 0" in c for c in contents)
        assert any("最近回复 0" in c for c in contents)
        assert any("最近回复 9" in c for c in contents)

    @pytest.mark.asyncio
    async def test_empty_summary_uses_fallback_text(self, context_manager, mock_llm):
        """LLM 返回空梗概时，使用固定的兜底文案。"""
        from types import SimpleNamespace

        _, create = mock_llm
        create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
        )
        await self._fill_history(context_manager)

        msgs = await context_manager.build_messages(max_context_tokens=1000)

        assert "[历史消息过长，未能生成有效梗概]" in msgs[1]["content"]

    @pytest.mark.asyncio
    async def test_llm_failure_keeps_original_messages(self, context_manager, mock_llm):
        """LLM 调用抛异常时保留原始消息，不压缩、不删除。"""
        _, create = mock_llm
        create.side_effect = RuntimeError("LLM 不可用")
        await self._fill_history(context_manager)

        msgs = await context_manager.build_messages(max_context_tokens=1000)

        assert create.call_count == 1
        contents = [str(m.get("content", "")) for m in msgs]
        assert any("历史问题 0" in c for c in contents)
        assert not any("[上下文压缩提示]" in c for c in contents)

    @pytest.mark.asyncio
    async def test_missing_follower_config_keeps_original(self, context_manager, mock_llm, monkeypatch):
        """FOLLOWER 配置缺失（key 为空）时不创建 client、不压缩。"""
        mock_cls, create = mock_llm
        from cloudra.config import get_config

        monkeypatch.setattr(get_config().follower, "key", "")
        await self._fill_history(context_manager)

        msgs = await context_manager.build_messages(max_context_tokens=1000)

        mock_cls.assert_not_called()
        create.assert_not_called()
        contents = [str(m.get("content", "")) for m in msgs]
        assert any("历史问题 0" in c for c in contents)

    @pytest.mark.asyncio
    async def test_summary_still_over_budget_keeps_original(self, context_manager, mock_llm):
        """梗概替换后仍超预算时，保留完整原始消息（不进一步删除）。"""
        _, create = mock_llm
        await self._fill_history(context_manager)

        msgs = await context_manager.build_messages(max_context_tokens=10)

        assert create.call_count == 1  # 仍然尝试了梗概
        contents = [str(m.get("content", "")) for m in msgs]
        assert any("历史问题 0" in c for c in contents)
        assert not any("[上下文压缩提示]" in c for c in contents)

    @pytest.mark.asyncio
    async def test_openai_client_cached_across_calls(self, context_manager, mock_llm):
        """压缩用 LLMClient 按实例缓存，多次梗概只构造一次。"""
        mock_cls, create = mock_llm
        history = [{"role": "user", "content": "hi"}]

        await context_manager._summarize_history(history)
        await context_manager._summarize_history(history)

        assert mock_cls.call_count == 1
        assert create.call_count == 2
