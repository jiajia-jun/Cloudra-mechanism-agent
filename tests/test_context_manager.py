import asyncio
from unittest.mock import patch

import pytest

from cloudra.context_manager import ContextManager
from cloudra.config import get_config
from cloudra.token_estimator import TokenEstimator


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
def mock_llm(monkeypatch):
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
        assert "工具结果缺失" in synthetic[0]["content"]

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
        await context_manager.append({"role": "assistant", "content": "调用工具", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "bashtools", "arguments": "{}"}},
        ]})
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
        await cm.replace([{"role": "user", "content": "hi"}])
        messages = await cm.build_messages(
            identity_messages=[{"role": "system", "content": long_prompt}]
        )
        assert messages[0]["content"] == long_prompt


class TestHistoryCompression:
    """LLM 历史压缩路径（_compress_to_budget / _summarize_history）钉板测试。

    LLMClient 全部 mock，钉住：
    1. 触发条件：估算总 token > max_context_tokens 才触发。
    2. 替换方式：system 消息 + 梗概消息 + 最近 4 个 assistant 回合原样保留。
    3. 兜底：LLM 失败 / 缺配置 / 梗概仍超预算 时保留原始消息不压缩。
    """

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
        """超预算时：历史被梗概替换，system 与最近 4 个回合保留。"""
        mock_cls, create = mock_llm
        await self._fill_history(context_manager)

        msgs = await context_manager.build_messages(max_context_tokens=1000)

        # LLM 被调用一次；除 temperature=1 外不覆盖服务商默认生成参数。
        assert create.call_count == 1
        kwargs = create.call_args.kwargs
        assert kwargs["model"] == "fake-model"
        assert kwargs["temperature"] == 1.0
        assert "max_tokens" not in kwargs
        # 梗概输入只包含历史（含初始 query），不包含保留的最近轮次。
        # 保留窗口以第 4 条 assistant 为锚点截断，该轮对应的 user 消息
        # （"最近问题 6"）被划入历史而非保留区。
        summary_prompt = kwargs["messages"][1]["content"]
        assert kwargs["messages"][0] == {"role": "system", "content": "你是一个专门压缩对话历史的助手。"}
        assert "历史问题 0" in summary_prompt
        assert "初始问题" in summary_prompt
        assert "最近问题 6" in summary_prompt
        assert "最近问题 7" not in summary_prompt

        # 结构：原 system prompt + 梗概 system 消息 + 保留尾部（7 条，
        # 从第 4 条 assistant "最近回复 6" 开始，其 user 消息不在其中）
        assert len(msgs) == 9
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "你是一个测试助手。"
        assert msgs[1]["role"] == "system"
        assert msgs[1]["content"].startswith("[上下文压缩提示]")
        assert "压缩梗概" in msgs[1]["content"]
        # 历史不再出现，保留区完整
        contents = [str(m.get("content", "")) for m in msgs]
        assert not any("历史问题 0" in c for c in contents)
        assert not any("最近问题 6" in c for c in contents)
        assert any("最近回复 6" in c for c in contents)
        assert any("最近回复 9" in c for c in contents)

    @pytest.mark.asyncio
    async def test_persistent_compaction_caps_oversized_summary_input(
        self, context_manager, mock_llm
    ):
        """巨型原始工具结果不会让摘要请求自身超窗并永久失效。"""
        _, create = mock_llm
        await context_manager.append(
            {"role": "tool", "content": "BEGIN-" + "x" * 60_000 + "-END"}
        )
        for index in range(5):
            await context_manager.append(
                {"role": "assistant", "content": f"近期回复 {index}"}
            )
            await context_manager.append(
                {"role": "user", "content": f"近期问题 {index}"}
            )

        assert await context_manager._compress_persistent() is True
        summary_prompt = create.call_args.kwargs["messages"][1]["content"]
        assert "BEGIN-" in summary_prompt
        assert "-END" not in summary_prompt
        assert "内容过长已截断" in summary_prompt

    @pytest.mark.asyncio
    async def test_oversized_history_uses_hierarchical_summary(
        self, context_manager, mock_llm, monkeypatch
    ):
        """摘要输入自身超过 FOLLOWER 半窗时分块并最终归并为一条。"""
        _, create = mock_llm
        monkeypatch.setattr(get_config().follower, "context_window", 32_000)
        history = [
            {"role": "tool", "content": f"块 {index}: " + "中" * 30_000}
            for index in range(4)
        ]
        summary = await context_manager._summarize_history(history)
        assert summary == "压缩梗概"
        assert create.call_count > 1
        for call in create.call_args_list:
            prompt = call.kwargs["messages"][1]["content"]
            assert TokenEstimator.estimate_text(prompt) < 20_000

    @pytest.mark.asyncio
    async def test_summary_chunks_use_bounded_parallelism_and_report_progress(
        self, context_manager, mock_llm, monkeypatch
    ):
        """同层摘要并发执行但不超过上限，并报告可展示的进度。"""
        from types import SimpleNamespace

        _, create = mock_llm
        monkeypatch.setattr(get_config().follower, "context_window", 16_000)
        active = 0
        peak = 0
        progress = []

        async def slow_summary(**kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="分段梗概"))]
            )

        create.side_effect = slow_summary
        context_manager._on_compaction_progress = progress.append
        history = [
            {"role": "tool", "content": f"块 {index}: " + "中" * 20_000}
            for index in range(6)
        ]

        assert await context_manager._summarize_history(history) == "分段梗概"
        assert 1 < peak <= 3
        assert progress[0]["stage"] == "started"
        assert any(item["stage"] == "progress" for item in progress)
        assert progress[-1]["stage"] == "completed"

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

        # 持久化压缩与 render-time 压缩各尝试一次梗概，均失败后保留原文
        assert create.call_count == 2
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
        """梗概替换后仍超预算（预算极端小）时的行为。

        现状：持久化压缩已成功写回存储（历史被梗概替换、不重复摘要），
        render-time 兜底对压缩后的消息不再进一步删除，原样返回——
        即使仍超预算。这与旧的"保留完整原文"不同：持久化压缩落地后
        历史已被梗概替代，压缩状态保留给后续轮次使用。
        """
        _, create = mock_llm
        await self._fill_history(context_manager)

        msgs = await context_manager.build_messages(max_context_tokens=10)

        assert create.call_count == 1  # 只做一次持久化梗概
        contents = [str(m.get("content", "")) for m in msgs]
        assert any("[上下文压缩提示]" in c for c in contents)
        assert not any("历史问题 0" in c for c in contents)
        # 持久化：存储中的上下文也已是梗概形态
        stored = await context_manager.load()
        stored_contents = [str(m.get("content", "")) for m in stored]
        assert any("[上下文压缩提示]" in c for c in stored_contents)
        assert not any("历史问题 0" in c for c in stored_contents)

    @pytest.mark.asyncio
    async def test_openai_client_cached_across_calls(self, context_manager, mock_llm):
        """压缩用 LLMClient 按实例缓存，多次梗概只构造一次。"""
        mock_cls, create = mock_llm
        history = [{"role": "user", "content": "hi"}]

        await context_manager._summarize_history(history)
        await context_manager._summarize_history(history)

        assert mock_cls.call_count == 1
        assert create.call_count == 2


class TestManualCompaction:
    """手动压缩 ``ContextManager.compact`` 钉板测试。"""

    @pytest.mark.asyncio
    async def test_compact_summarizes_history_and_keeps_tail(self, context_manager, mock_llm):
        """保留最近 N 条消息，历史生成梗概并持久化。"""
        _, create = mock_llm
        # 初始上下文已含 1 条 user 消息
        for i in range(6):
            await context_manager.append({"role": "user", "content": f"问题 {i}"})
            await context_manager.append({"role": "assistant", "content": f"回复 {i}"})

        result = await context_manager.compact(keep_recent=4)

        assert result["compressed"] is True
        assert result["original_count"] == 13  # 1 + 6*2
        assert result["new_count"] == 5          # 梗概 + 4 条保留
        assert result["summary_length"] == len("压缩梗概")
        create.assert_called_once()

        context = await context_manager.load()
        assert len(context) == 5
        assert context[0]["role"] == "system"
        assert context[0]["content"].startswith("[上下文压缩提示]")
        assert "压缩梗概" in context[0]["content"]
        assert context[-1]["content"] == "回复 5"
        assert context[-2]["content"] == "问题 5"

    @pytest.mark.asyncio
    async def test_compact_skips_when_below_keep_threshold(self, context_manager, mock_llm):
        """消息数未超过保留窗口时不调用 LLM。"""
        _, create = mock_llm
        await context_manager.append({"role": "user", "content": "你好"})

        result = await context_manager.compact(keep_recent=4)

        assert result["compressed"] is False
        assert result["original_count"] == 2
        assert result["new_count"] == 2
        create.assert_not_called()

    @pytest.mark.asyncio
    async def test_compact_invalid_keep_recent(self, context_manager):
        """keep_recent < 1 时抛出 ValueError。"""
        with pytest.raises(ValueError):
            await context_manager.compact(keep_recent=0)

    @pytest.mark.asyncio
    async def test_compact_propagates_summary_failure(self, context_manager, mock_llm):
        """梗概生成失败时向上抛出异常，不修改上下文。"""
        _, create = mock_llm
        create.side_effect = RuntimeError("LLM 不可用")
        for i in range(4):
            await context_manager.append({"role": "user", "content": f"问题 {i}"})
            await context_manager.append({"role": "assistant", "content": f"回复 {i}"})

        with pytest.raises(RuntimeError, match="LLM 不可用"):
            await context_manager.compact(keep_recent=2)

        # 原始上下文未被修改
        context = await context_manager.load()
        assert len(context) == 9
        assert context[-1]["content"] == "回复 3"


class TestCoordinatorContextSharing:
    """回归：同一对话的多个 Coordinator 任务（session）共享一份上下文。

    规则（react.py / executor.py）：
    - Coordinator 的 agent_id 是 'a-0'，Agent.session_id 为 None
      → 上下文文件是对话级 contexts/a-0.json，跨任务延续；
    - 子 Agent 的 Agent.session_id 被赋值 → 上下文按 session 隔离，
      且任务结束即清空（react.py 中仅对非 a-0 调用 clear_context）。
    """

    def test_coordinator_context_is_conversation_scoped(self, tmp_path, monkeypatch):
        """Coordinator 实例不带 session_id，上下文文件路径不含 sessions/ 子目录。"""
        from cloudra.agent import Coordinator

        monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path))
        from cloudra.config import reload_config
        reload_config()

        agent = Coordinator(query="测试", conversation_id="conv_x")
        assert agent.id == "a-0"
        assert agent.session_id is None

        agent._init_context_manager()
        path = agent.context_manager.context_file
        assert "sessions" not in path
        assert path.endswith("a-0.json")

    @pytest.mark.asyncio
    async def test_two_sessions_share_one_context(self, tmp_path, monkeypatch):
        """任务1 写入的上下文，任务2（新 ContextManager 实例）能读到。"""
        monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path))
        from cloudra.config import reload_config
        reload_config()

        cm1 = ContextManager(
            agent_id="a-0", conversation_id="conv_share", prompt=None, query="任务1"
        )
        await cm1.append({"role": "assistant", "content": "任务1 的回答"})

        # 模拟任务2：同一对话、同一 Coordinator agent，新的 ContextManager 实例
        cm2 = ContextManager(
            agent_id="a-0", conversation_id="conv_share", prompt=None, query="任务2"
        )
        context = await cm2.load()
        contents = [m.get("content") for m in context]
        assert "任务1 的回答" in contents

    def test_subagent_context_is_session_scoped(self, tmp_path, monkeypatch):
        """子 Agent 上下文按 session 隔离：不同 session_id 是不同文件。"""
        monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path))
        from cloudra.config import reload_config
        reload_config()

        cm_a = ContextManager(
            agent_id="a-1", conversation_id="conv_iso", prompt=None, query="q",
            session_id="a-1_run_aaa",
        )
        cm_b = ContextManager(
            agent_id="a-1", conversation_id="conv_iso", prompt=None, query="q",
            session_id="a-1_run_bbb",
        )
        assert cm_a.context_file != cm_b.context_file
        assert "sessions" in cm_a.context_file


class TestEmptyUserMessageGuard:
    """回归：空 user 消息不能进入 LLM 请求。

    只读用途的 ContextManager（query=""，如 TUI 状态栏的记忆指示）曾经在
    load() 时把 [{"role": "user", "content": ""}] 持久化进上下文文件，
    之后每次真实请求 position 1 都是这条空 user 消息，被严格端点以
    400 "user message must not be empty" 拒绝——表现为 agent 完全不回答。
    """

    @pytest.mark.asyncio
    async def test_readonly_load_does_not_persist_empty_user(self, tmp_path, monkeypatch):
        """query="" 的 load() 初始化为空列表，不落空 user 消息。"""
        monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path))
        from cloudra.config import reload_config
        reload_config()

        cm = ContextManager(
            agent_id="a-0", conversation_id="conv_ro", prompt=None, query=""
        )
        context = await cm.load()
        assert context == []
        from cloudra.context_manager import read_context_file
        assert read_context_file(cm.context_file) == []

    @pytest.mark.asyncio
    async def test_build_messages_drops_empty_user(self, tmp_path, monkeypatch):
        """历史里已存在的空 user 消息在请求装配时被过滤（修复存量污染文件）。"""
        monkeypatch.setenv("CLOUDRA_DATA_DIR", str(tmp_path))
        from cloudra.config import reload_config
        reload_config()

        cm = ContextManager(
            agent_id="a-0", conversation_id="conv_poison", prompt=None, query=""
        )
        # 模拟被旧版本污染的历史：空 user 在最前面
        await cm.replace([
            {"role": "user", "content": ""},
            {"role": "user", "content": "  "},
            {"role": "user", "content": "真实问题"},
            {"role": "assistant", "content": "真实回答"},
            {"role": "user", "content": [{"type": "text", "text": ""}]},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}}
            ]},
        ])
        messages = await cm.build_messages()
        user_contents = [m["content"] for m in messages if m.get("role") == "user"]
        assert "真实问题" in user_contents
        assert "" not in user_contents
        assert "  " not in user_contents
        assert [{"type": "text", "text": ""}] not in user_contents
        # 带图片部分的 user 消息保留（无视觉模型时降级为文本占位符）
        assert any("[图片:" in str(c) for c in user_contents)


def _assistant_with_tool_calls(*call_ids: str) -> dict:
    """构造一条带 tool_calls 的 assistant 消息。"""
    return {
        "role": "assistant",
        "content": "调用工具",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "bash", "arguments": "{}"},
            }
            for call_id in call_ids
        ],
    }


def _tool_result(call_id: str, content: str = "工具输出") -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _assert_tool_pairing(messages: list[dict]) -> None:
    """断言消息列表中无孤儿 tool 结果（每个 tool_call_id 都有匹配的 tool_call）。"""
    declared = {
        call["id"]
        for msg in messages
        if msg.get("role") == "assistant"
        for call in (msg.get("tool_calls") or [])
    }
    for msg in messages:
        if msg.get("role") == "tool":
            assert msg.get("tool_call_id") in declared


class TestToolPairingRepair:
    """_repair_tool_pairing：build_messages 清洗链的 tool_calls 配对兜底。

    背景：上下文压缩曾把带 tool_calls 的 assistant 梗概掉、却把它的 tool
    结果留在保留尾部，压缩后的上下文带一个无匹配 function_call 的
    function_call_output，严格端点（DeepSeek /responses）以 400 拒绝之后
    所有请求，会话永久变砖。渲染期配对清洗同时救活这类存量污染会话。
    """

    def test_orphan_tool_result_dropped(self):
        """tool_call_id 找不到匹配 assistant tool_call 的 tool 消息被丢弃。"""
        messages = [
            {"role": "system", "content": "[上下文压缩提示] 梗概"},
            _tool_result("call_orphan"),
            _assistant_with_tool_calls("call_a", "call_b"),
            _tool_result("call_a"),
            _tool_result("call_b"),
            {"role": "user", "content": "继续"},
        ]
        repaired = ContextManager._repair_tool_pairing(messages)
        assert len(repaired) == len(messages) - 1
        assert all(m.get("tool_call_id") != "call_orphan" for m in repaired)
        _assert_tool_pairing(repaired)

    def test_missing_result_gets_placeholder(self):
        """无结果的 tool_call 在其 assistant 的 tool 结果组之后补占位消息。"""
        assistant = _assistant_with_tool_calls("call_a", "call_b")
        messages = [
            {"role": "user", "content": "查一下"},
            assistant,
            _tool_result("call_a"),
            {"role": "assistant", "content": "最终回复"},
        ]
        repaired = ContextManager._repair_tool_pairing(messages)
        assert len(repaired) == len(messages) + 1
        placeholder = next(
            m for m in repaired
            if m.get("role") == "tool" and m.get("tool_call_id") == "call_b"
        )
        assert "工具结果缺失" in placeholder["content"]
        # 占位补在该 assistant（及其后连续的 tool 结果组）之后、下一条 assistant 之前
        assert repaired.index(assistant) < repaired.index(placeholder)
        assert repaired.index(placeholder) < repaired.index(messages[3])
        _assert_tool_pairing(repaired)

    def test_wellformed_pairing_untouched(self):
        """正常配对的消息列表原样不动。"""
        messages = [
            {"role": "user", "content": "查一下"},
            _assistant_with_tool_calls("call_a"),
            _tool_result("call_a"),
            {"role": "assistant", "content": "回复"},
        ]
        assert ContextManager._repair_tool_pairing(messages) == messages


class TestTailCutAlignment:
    """压缩切口对齐 tool_calls 配对边界（_split_tail_keep_tool_pairs）。"""

    def test_cut_on_tool_result_shifts_left(self):
        """切口恰好落在 tool 结果上时左移，把配对的 assistant 拉进尾部。"""
        messages = [
            {"role": "user", "content": "旧问题"},
            _assistant_with_tool_calls("call_a"),
            _tool_result("call_a"),
            {"role": "assistant", "content": "近期回复"},
        ]
        # tail_count=2 的切口恰好落在 tool 结果上
        history, tail = ContextManager._split_tail_keep_tool_pairs(messages, 2)
        assert history == messages[:1]
        assert tail == messages[1:]
        assert tail[0]["role"] == "assistant"
        _assert_tool_pairing(tail)

    def test_orphan_dropped_when_history_exhausted(self):
        """history 耗尽仍找不到配对的 assistant 时，丢弃尾部开头的孤儿 tool。"""
        messages = [
            _tool_result("call_a"),
            _tool_result("call_b"),
            {"role": "assistant", "content": "近期回复"},
        ]
        history, tail = ContextManager._split_tail_keep_tool_pairs(messages, 3)
        assert history == []
        assert [m["role"] for m in tail] == ["assistant"]

    @pytest.mark.asyncio
    async def test_compress_persistent_cut_aligned(
        self, context_manager, mock_llm, monkeypatch
    ):
        """持久化压缩切口落在 tool 结果上时左移对齐，压缩结果无孤儿 tool。"""
        monkeypatch.setattr(
            "cloudra.context_manager.AUTO_COMPACT_KEEP_ASSISTANT", 0
        )
        await context_manager.replace(
            [
                {"role": "user", "content": f"旧问题 {i}"}
                for i in range(3)
            ]
            + [
                {"role": "assistant", "content": "旧回复"},
                _assistant_with_tool_calls("call_a"),
                _tool_result("call_a"),
            ]
        )

        assert await context_manager._compress_persistent() is True
        stored = await context_manager.load()
        _assert_tool_pairing(stored)
        # 带 tool_calls 的 assistant 与它的 tool 结果一起保留在尾部
        assert any(
            m.get("role") == "assistant" and m.get("tool_calls") for m in stored
        )
        assert any(m.get("tool_call_id") == "call_a" for m in stored)

    @pytest.mark.asyncio
    async def test_compress_to_budget_cut_aligned(
        self, context_manager, mock_llm, monkeypatch
    ):
        """render-time 压缩切口落在 tool 结果上时左移对齐，结果无孤儿 tool。"""
        monkeypatch.setattr(
            "cloudra.context_manager.RENDER_COMPACT_KEEP_ASSISTANT", 0
        )
        messages = [
            {"role": "system", "content": "身份"},
            {"role": "user", "content": "旧问题 " + "长" * 500},
            {"role": "assistant", "content": "旧回复 " + "长" * 500},
            _assistant_with_tool_calls("call_a"),
            _tool_result("call_a"),
        ]

        compressed = await context_manager._compress_to_budget(
            messages, max_context_tokens=200
        )

        _assert_tool_pairing(compressed)
        # 历史被梗概替换，tool 链完整保留在尾部
        assert any(
            str(m.get("content", "")).startswith("[上下文压缩提示]")
            for m in compressed
        )
        assert any(m.get("tool_call_id") == "call_a" for m in compressed)

    @pytest.mark.asyncio
    async def test_manual_compact_cut_aligned(self, context_manager, mock_llm):
        """手动 compact 的 keep_recent 切口落在 tool 结果上时左移对齐。"""
        await context_manager.replace([
            {"role": "user", "content": "旧问题"},
            {"role": "assistant", "content": "旧回复"},
            _assistant_with_tool_calls("call_a"),
            _tool_result("call_a"),
            {"role": "assistant", "content": "近期回复"},
        ])

        stats = await context_manager.compact(keep_recent=2)

        assert stats["compressed"] is True
        stored = await context_manager.load()
        _assert_tool_pairing(stored)
        # 切口左移：梗概 + assistant(tool_calls) + tool + 近期回复
        assert stats["new_count"] == 4
        assert stored[0]["content"].startswith("[上下文压缩提示]")
