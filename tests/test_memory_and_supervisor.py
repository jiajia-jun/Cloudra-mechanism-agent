import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from cloudra.case_bank import CaseBank
from cloudra.context_manager import SUPERVISOR_ADVICE_MARKER, ContextManager
from cloudra.memory import MemoryManager
from cloudra.supervisor import Supervisor


# ---------------------------------------------------------------------------
# MemoryManager tests
# ---------------------------------------------------------------------------
@pytest.fixture
def memory_manager(tmp_path, monkeypatch):
    """提供一个使用临时目录的 MemoryManager 实例。"""
    cfg = MagicMock()
    cfg.data_dir = tmp_path
    monkeypatch.setattr("cloudra.memory.get_config", lambda: cfg)
    return MemoryManager(word_limit=50, compressed_word_limit=30)


@pytest.mark.asyncio
class TestMemoryManager:
    async def test_append_lesson_creates_file(self, memory_manager):
        result = await memory_manager.append_lesson("测试经验", source="test", skill_name="dft")
        assert "已记录经验" in result
        assert memory_manager.memory_path.exists()
        content = memory_manager.load()
        assert "测试经验" in content
        assert "dft" in content
        assert "test" in content

    async def test_word_count(self, memory_manager):
        text = "这是十三个汉字"
        count = memory_manager._count_words(text)
        assert count == 7

    async def test_compression_triggered(self, memory_manager):
        # 触发压缩：写入超过 50 字的内容
        with patch.object(memory_manager, "_llm_compress", new=AsyncMock(return_value="压缩后的核心原则。")):
            await memory_manager.append_lesson("这是一条非常长的经验教训，" * 10, source="test")
            # 再次追加确保超过阈值
            result = await memory_manager.append_lesson("另一条非常长的经验教训，" * 10, source="test")
            assert "触发记忆压缩" in result
            # 归档文件应存在
            assert memory_manager.memory_path.with_suffix(".archive.md").exists()


# ---------------------------------------------------------------------------
# ContextManager supervisor advice tests
# ---------------------------------------------------------------------------
@pytest.fixture
def context_manager(tmp_path):
    cm = ContextManager(
        agent_id="test-agent",
        conversation_id="test-conv",
        prompt="你是一个测试助手。",
        query="初始问题",
    )
    cm.context_file = str(tmp_path / "context.json")
    return cm


@pytest.mark.asyncio
class TestSupervisorAdviceInsertion:
    async def test_advice_inserted_at_index_2(self, context_manager):
        await context_manager.set_supervisor_advice("先查文献再计算。")
        context = await context_manager.load()
        assert context[0]["role"] == "system"
        assert "你是一个测试助手" in context[0]["content"]
        assert context[1]["role"] == "user"
        assert context[1]["content"] == "初始问题"
        assert context[2]["role"] == "system"
        assert context[2]["content"].startswith(SUPERVISOR_ADVICE_MARKER)
        assert "先查文献再计算" in context[2]["content"]

    async def test_advice_replaces_existing(self, context_manager):
        await context_manager.set_supervisor_advice("旧建议")
        await context_manager.set_supervisor_advice("新建议")
        context = await context_manager.load()
        # 应仍只有一条 supervisor advice，且位于索引 2
        advice_msgs = [
            m for m in context
            if m["role"] == "system" and str(m.get("content", "")).startswith(SUPERVISOR_ADVICE_MARKER)
        ]
        assert len(advice_msgs) == 1
        assert "新建议" in advice_msgs[0]["content"]
        assert "旧建议" not in advice_msgs[0]["content"]


# ---------------------------------------------------------------------------
# Supervisor tests
# ---------------------------------------------------------------------------
@pytest.fixture
def supervisor():
    return Supervisor(model="dummy", base_url="http://dummy", api_key="dummy", interval=5)


class TestSupervisor:
    def test_should_review_every_n_steps(self, supervisor):
        assert not supervisor.should_review(0)
        assert not supervisor.should_review(1)
        assert not supervisor.should_review(4)
        assert supervisor.should_review(5)
        assert supervisor.should_review(10)
        assert not supervisor.should_review(11)

    def test_retrieve_relevant_cases_with_bytes_embedding(self, supervisor):
        vec_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        vec_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        query_vec = np.array([0.9, 0.1, 0.0], dtype=np.float32)

        cases = [
            {"id": 1, "task_summary": "case a", "embedding": vec_a.tobytes()},
            {"id": 2, "task_summary": "case b", "embedding": vec_b.tobytes()},
        ]
        results = supervisor.retrieve_relevant_cases(query_vec, cases, k=1)
        assert len(results) == 1
        assert results[0]["id"] == 1

    def test_retrieve_ignores_missing_embedding(self, supervisor):
        query_vec = np.array([1.0, 0.0], dtype=np.float32)
        cases = [
            {"id": 1, "task_summary": "no embedding"},
            {"id": 2, "task_summary": "valid", "embedding": [1.0, 0.0]},
        ]
        results = supervisor.retrieve_relevant_cases(query_vec, cases, k=3)
        assert len(results) == 1
        assert results[0]["id"] == 2


# ---------------------------------------------------------------------------
# CaseBank tests（全局案例库）
# ---------------------------------------------------------------------------
@pytest.fixture
def case_bank(tmp_path, monkeypatch):
    """提供一个使用临时文件的全局 CaseBank 实例。"""
    cfg = MagicMock()
    cfg.data_dir = tmp_path
    monkeypatch.setattr("cloudra.case_bank.get_config", lambda: cfg)
    return CaseBank(str(tmp_path / "case_bank.db")).init()


class TestCaseBank:
    def test_connect_closes_on_context_exit(self, case_bank):
        with case_bank.connect() as con:
            assert con.execute("SELECT 1").fetchone() == (1,)

        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            con.execute("SELECT 1")

    def test_add_and_get_case(self, case_bank):
        emb = np.array([0.1, 0.2, 0.3], dtype=np.float32).tobytes()
        case_id = case_bank.add_case(
            session_id="s-1",
            task_summary="测试任务",
            outcome="success",
            outcome_reason="参数正确",
            lesson="先检查 POTCAR",
            embedding=emb,
        )
        assert case_id > 0

        cases = case_bank.get_cases(limit=10)
        assert len(cases) == 1
        assert cases[0]["session_id"] == "s-1"
        assert cases[0]["task_summary"] == "测试任务"
        assert cases[0]["outcome"] == "success"
        assert cases[0]["embedding"] == emb

    def test_case_count(self, case_bank):
        assert case_bank.case_count() == 0
        case_bank.add_case(
            session_id="s-1",
            task_summary="任务1",
            outcome="success",
        )
        assert case_bank.case_count() == 1


# ---------------------------------------------------------------------------
# UpdateMemory tool test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestUpdateMemoryTool:
    async def test_update_memory_writes_file(self, tmp_path, monkeypatch):
        from cloudra.agent import Coordinator
        from cloudra.tools.Writetool.update_memory import UpdateMemory

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        monkeypatch.setattr("cloudra.memory.get_config", lambda: cfg)

        agent = Coordinator(query="test", conversation_id="test-conv")
        tool = UpdateMemory(subagent=agent)
        from cloudra.tools.Writetool.update_memory import UpdateMemory_input_schema

        result = await tool.tool_call(
            UpdateMemory_input_schema(
                lesson="Gaussian TS 搜索前必须做柔性扫描。",
                source="reaction-path-task",
                skill_name="dft-calculation",
            ),
            MagicMock(),
        )
        assert "已记录经验" in result.result
        manager = MemoryManager(conversation_id="test-conv")
        manager.memory_path = tmp_path / "memory" / "MEMORY.md"
        content = manager.load()
        assert "Gaussian TS" in content
        assert result.word_count > 0

    async def test_update_memory_available_to_coordinator(self, tmp_path, monkeypatch):
        """update_memory 工具必须在 Coordinator 的可用工具列表中。"""
        from cloudra.agent import Coordinator

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        monkeypatch.setattr("cloudra.memory.get_config", lambda: cfg)

        agent = Coordinator(query="test", conversation_id="test-conv")
        tool_names = {t.tool_name for t in agent.get_available_tools()}
        assert "update_memory" in tool_names


# ---------------------------------------------------------------------------
# Coordinator memory loading test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCoordinatorMemoryLoading:
    async def test_coordinator_prompt_includes_memory(self, tmp_path, monkeypatch):
        """Coordinator 初始化时，若 MEMORY.md 存在，应自动注入到身份 prompt。"""
        from cloudra.agent import Coordinator

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        monkeypatch.setattr("cloudra.memory.get_config", lambda: cfg)

        # 预写入记忆
        manager = MemoryManager(conversation_id="test-conv")
        manager.memory_path = tmp_path / "memory" / "MEMORY.md"
        await manager.append_lesson("VASP 磁性体系必须设置 ISPIN=2。", source="test")

        agent = Coordinator(query="test", conversation_id="test-conv")
        assert "长期记忆" in agent.prompt
        assert "ISPIN=2" in agent.prompt


# ---------------------------------------------------------------------------
# Memory compression fallback test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestMemoryCompressionFallback:
    async def test_fallback_compress_respects_limit(self, tmp_path, monkeypatch):
        """未配置 LLM 时，压缩应退化为保留最近内容，且不超出限制。"""
        cfg = MagicMock()
        cfg.data_dir = tmp_path
        monkeypatch.setattr("cloudra.memory.get_config", lambda: cfg)

        manager = MemoryManager(word_limit=30, compressed_word_limit=20)
        # 写入多条经验，触发压缩；此时 LLM 未配置，会走 fallback
        await manager.append_lesson("经验 A：检查基组。" * 5, source="test")
        await manager.append_lesson("经验 B：检查泛函。" * 5, source="test")

        content = manager.load()
        assert content != ""
        word_count = manager._count_words(content)
        assert word_count <= manager.compressed_word_limit


# ---------------------------------------------------------------------------
# reAct Supervisor integration tests
# ---------------------------------------------------------------------------
class TestReActSupervisorIntegration:
    def test_should_use_supervisor_default(self, tmp_path, monkeypatch):
        """普通 Agent 默认启用 Supervisor。"""
        from cloudra.agent import Follower
        from cloudra.database import ConversationDB
        from cloudra.react import reAct

        conv_id = "test-react"
        db_path = str(tmp_path / "test.db")
        db = ConversationDB.from_path(db_path)
        db.init()
        monkeypatch.setattr("cloudra.react.get_database_path", lambda _conv_id: db_path)

        agent = Follower(
            id="a-test",
            name="tester",
            prompt="测试",
            query="测试问题",
            conversation_id=conv_id,
        )
        react = reAct(agent)
        assert react._should_use_supervisor() is True

    def test_supervisor_instance_created(self, tmp_path, monkeypatch):
        """reAct 初始化时应创建 Supervisor 实例。"""
        from cloudra.agent import Follower
        from cloudra.database import ConversationDB
        from cloudra.react import reAct

        conv_id = "test-react"
        db_path = str(tmp_path / "test.db")
        db = ConversationDB.from_path(db_path)
        db.init()
        monkeypatch.setattr("cloudra.react.get_database_path", lambda _conv_id: db_path)

        agent = Follower(
            id="a-test",
            name="tester",
            prompt="测试",
            query="测试问题",
            conversation_id=conv_id,
        )
        react = reAct(agent)
        assert react.supervisor is not None
        assert react.supervisor.interval == 15


class TestSupervisorJsonTruncation:
    """thinking 模型 JSON 输出被 max_tokens 截断时的翻倍重试。

    传输层委托给 LLMClient.chat_json，因此 mock 最底层的 create，
    通过真实的 review 路径验证截断翻倍与预算参数。
    """

    @staticmethod
    def _resp(content: str, finish: str):
        import types
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content=content),
                finish_reason=finish,
            )]
        )

    @staticmethod
    def _patch_transport(supervisor, **kwargs):
        """给 supervisor 挂上真实 LLMClient，并 mock 掉最底层 create。"""
        from cloudra.llm_client import LLMClient

        client = LLMClient(api_key="dummy", base_url="http://dummy", model="dummy")
        supervisor._llm_client = client
        return patch.object(client, "create", **kwargs)

    @pytest.mark.asyncio
    async def test_truncated_json_retried_with_doubled_budget(self, supervisor):
        truncated = self._resp('{"verdict": "proceed", "reason', "length")
        full = self._resp('{"verdict": "redirect", "reasoning": "ok", "advice": ["a"]}', "stop")
        with self._patch_transport(supervisor, new=AsyncMock(side_effect=[truncated, full])) as call, \
             patch.object(supervisor, "embed_text", new=AsyncMock(return_value=np.zeros(1536))):
            review = await supervisor.review("目标", [{"role": "user", "content": "你好"}])
        assert review.verdict == "redirect"
        assert call.await_count == 2
        # 重试时 max_tokens 翻倍
        assert call.await_args_list[1].kwargs["max_tokens"] == 8192

    @pytest.mark.asyncio
    async def test_malformed_json_not_retried(self, supervisor):
        bad = self._resp("这不是 JSON", "stop")
        with self._patch_transport(supervisor, new=AsyncMock(return_value=bad)) as call, \
             patch.object(supervisor, "embed_text", new=AsyncMock(return_value=np.zeros(1536))):
            review = await supervisor.review("目标", [{"role": "user", "content": "你好"}])
        assert call.await_count == 1
        # 解析失败时退化为 proceed，不中断主流程
        assert review.verdict == "proceed"
        assert "审查失败" in review.reasoning

    @pytest.mark.asyncio
    async def test_review_uses_raised_budget(self, supervisor):
        full = self._resp('{"verdict": "pass", "reasoning": "ok", "advice": []}', "stop")
        with self._patch_transport(supervisor, new=AsyncMock(return_value=full)) as call, \
             patch.object(supervisor, "embed_text", new=AsyncMock(return_value=np.zeros(1536))):
            review = await supervisor.review("目标", [{"role": "user", "content": "你好"}])
        assert call.await_args_list[0].kwargs["max_tokens"] == 4096
        assert review.verdict == "pass"


class TestSupervisorAdviceSingleMarker:
    """注入上下文的 supervisor 建议必须只有一个 [Supervisor] marker。"""

    @pytest.mark.asyncio
    async def test_format_then_inject_single_marker(self, context_manager, supervisor):
        from cloudra.supervisor import SupervisorReview

        review = SupervisorReview(
            verdict="redirect",
            reasoning="方向偏离",
            advice=["先查文献", "再计算"],
        )
        advice_text = supervisor.format_advice(review)
        # format_advice 自身不带 marker（由注入方统一包装）
        assert not advice_text.startswith(SUPERVISOR_ADVICE_MARKER)

        await context_manager.set_supervisor_advice(advice_text)
        context = await context_manager.load()
        msg = context[2]["content"]
        assert msg.startswith(SUPERVISOR_ADVICE_MARKER)
        assert msg.count(SUPERVISOR_ADVICE_MARKER) == 1
        assert "方向偏离" in msg and "先查文献" in msg

        # 注入后再次渲染：消息完整出现在发给 LLM 的上下文中
        rendered = await context_manager.build_messages()
        sup_msgs = [
            m for m in rendered
            if m.get("role") == "system" and str(m.get("content", "")).startswith(SUPERVISOR_ADVICE_MARKER)
        ]
        assert len(sup_msgs) == 1


class TestSupervisorReviewEndToEnd:
    """reAct._supervisor_review：建议注入上下文（index 2、单 marker）且事件落库。"""

    @pytest.mark.asyncio
    async def test_review_injected_and_event_recorded(self, tmp_path, monkeypatch):
        import sqlite3
        from unittest.mock import AsyncMock

        from cloudra.agent import Follower
        from cloudra.database import ConversationDB
        from cloudra.react import reAct
        from cloudra.supervisor import SupervisorReview

        db_path = str(tmp_path / "t.db")
        ConversationDB.from_path(db_path).init()
        monkeypatch.setattr("cloudra.react.get_database_path", lambda _c: db_path)

        agent = Follower(id="a-sup", name="tester", prompt="测试", query="测试任务", conversation_id="sup-e2e")
        react = reAct(agent)
        agent._init_context_manager()
        agent.context_manager.context_file = str(tmp_path / "ctx.json")
        agent.context_manager.db_path = db_path
        await agent.get_context()

        react.supervisor.review = AsyncMock(return_value=SupervisorReview(
            verdict="pass", reasoning="方向正确", advice=["继续"],
        ))
        await react._supervisor_review()

        # 审查间隔已调为 15 轮
        assert react.supervisor.interval == 15

        ctx = await agent.get_context()
        assert ctx[2]["role"] == "system"
        assert ctx[2]["content"].startswith(SUPERVISOR_ADVICE_MARKER)
        assert ctx[2]["content"].count(SUPERVISOR_ADVICE_MARKER) == 1
        assert "方向正确" in ctx[2]["content"]
        # 包装层附带了"优先参考"的引导语
        assert "优先参考" in ctx[2]["content"]

        with sqlite3.connect(db_path) as con:
            row = con.execute(
                "SELECT data FROM session_events WHERE event_type='supervisor_review' AND session_id=?",
                (react.session.id,),
            ).fetchone()
        assert row is not None
        import json
        data = json.loads(row[0])
        assert data["verdict"] == "pass" and data["advice"] == ["继续"]


class TestCompressTimelineWindow:
    """Supervisor 的时间线窗口已加大：保留更多事件与更长的单条内容。"""

    def test_keeps_40_recent_events_and_long_content(self, supervisor):
        messages = []
        for i in range(60):
            messages.append({"role": "user", "content": f"第{i}条事件" + "x" * 20})
        summary = supervisor.compress_timeline(messages)
        # 最近 40 条都在（旧窗口只有 20 条）
        assert "第59条" in summary and "第20条" in summary
        assert "第19条" not in summary
        # 单条内容截断放宽到 500 字符（600 字符保留 250 对"数据"；旧逻辑 200 字符只剩 100 对）
        long_msg = [{"role": "user", "content": "数据" * 300}]  # 600 字符
        s2 = supervisor.compress_timeline(long_msg)
        assert s2.count("数据") == 250
