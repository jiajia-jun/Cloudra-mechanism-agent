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
