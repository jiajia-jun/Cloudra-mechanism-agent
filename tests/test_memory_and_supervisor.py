import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from cloudra.core.supervisor import Supervisor
from cloudra.persistence.case_bank import CaseBank
from cloudra.persistence.context_manager import SUPERVISOR_ADVICE_MARKER, ContextManager
from cloudra.persistence.memory import MemoryManager


# ---------------------------------------------------------------------------
# MemoryManager tests
# ---------------------------------------------------------------------------
@pytest.fixture
def memory_manager(tmp_path, monkeypatch):
    """提供一个使用临时目录的 MemoryManager 实例。"""
    cfg = MagicMock()
    cfg.data_dir = tmp_path
    monkeypatch.setattr("cloudra.persistence.memory.get_config", lambda: cfg)
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
    async def test_advice_inserted_after_query(self, context_manager):
        await context_manager.set_supervisor_advice("先查文献再计算。")
        context = await context_manager.load()
        assert context[0]["role"] == "user"
        assert context[0]["content"] == "初始问题"
        assert context[1]["role"] == "system"
        assert context[1]["content"].startswith(SUPERVISOR_ADVICE_MARKER)
        assert "先查文献再计算" in context[1]["content"]

    async def test_advice_replaces_existing(self, context_manager):
        await context_manager.set_supervisor_advice("旧建议")
        await context_manager.set_supervisor_advice("新建议")
        context = await context_manager.load()
        # 应仍只有一条 supervisor advice，且紧跟初始 query。
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
    return Supervisor(model="dummy", base_url="http://dummy", api_key="dummy")


class TestSupervisor:
    def test_has_no_periodic_review_or_free_text_api(self, supervisor):
        assert not hasattr(supervisor, "should_review")
        assert not hasattr(supervisor, "review")
        assert not hasattr(supervisor, "format_advice")

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
    monkeypatch.setattr("cloudra.persistence.case_bank.get_config", lambda: cfg)
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
        from cloudra.core.agent import Coordinator
        from cloudra.tools.Writetool.update_memory import UpdateMemory

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        monkeypatch.setattr("cloudra.persistence.memory.get_config", lambda: cfg)

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
        from cloudra.core.agent import Coordinator

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        monkeypatch.setattr("cloudra.persistence.memory.get_config", lambda: cfg)

        agent = Coordinator(query="test", conversation_id="test-conv")
        tool_names = {t.tool_name for t in agent.get_available_tools()}
        assert "update_memory" in tool_names


# ---------------------------------------------------------------------------
# Coordinator memory loading test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestCoordinatorMemoryLoading:
    async def test_coordinator_request_prompt_includes_memory(self, tmp_path, monkeypatch):
        """Coordinator 每次请求时读取 MEMORY.md 并注入身份层。"""
        from cloudra.core.agent import Coordinator

        cfg = MagicMock()
        cfg.data_dir = tmp_path
        cfg.config_file = tmp_path / "config.toml"
        monkeypatch.setattr("cloudra.persistence.memory.get_config", lambda: cfg)
        monkeypatch.setattr("cloudra.runtime.prompt_assembler.get_config", lambda: cfg)

        # 预写入记忆
        manager = MemoryManager(conversation_id="test-conv")
        manager.memory_path = tmp_path / "memory" / "MEMORY.md"
        await manager.append_lesson("VASP 磁性体系必须设置 ISPIN=2。", source="test")

        agent = Coordinator(
            query="test",
            conversation_id="test-conv",
            working_directory=str(tmp_path),
        )
        agent._tools_schema_cache = []
        messages = await agent._build_messages()
        identity = messages[0]["content"]
        assert "长期记忆" in identity
        assert "ISPIN=2" in identity
        assert any(
            source["kind"] == "memory"
            for source in agent._last_prompt_assembly.diagnostics()["prompt_sources"]
        )


# ---------------------------------------------------------------------------
# Memory compression fallback test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestMemoryCompressionFallback:
    async def test_fallback_compress_respects_limit(self, tmp_path, monkeypatch):
        """未配置 LLM 时，压缩应退化为保留最近内容，且不超出限制。"""
        cfg = MagicMock()
        cfg.data_dir = tmp_path
        monkeypatch.setattr("cloudra.persistence.memory.get_config", lambda: cfg)

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
    def test_standard_has_no_supervisor_or_legacy_review_hook(self, tmp_path, monkeypatch):
        from cloudra.core.agent import Follower
        from cloudra.core.react import reAct
        from cloudra.persistence.database import ConversationDB

        conv_id = "test-react"
        db_path = str(tmp_path / "test.db")
        db = ConversationDB.from_path(db_path)
        db.init()
        monkeypatch.setattr("cloudra.core.react.get_database_path", lambda _conv_id: db_path)

        agent = Follower(
            id="a-test",
            name="tester",
            prompt="测试",
            query="测试问题",
            conversation_id=conv_id,
        )
        react = reAct(agent)
        assert react.supervisor is None
        assert not hasattr(react, "_should_use_supervisor")
        assert not hasattr(react, "_supervisor_review")

    def test_supervisor_instance_created(self, tmp_path, monkeypatch):
        """Only DAG-guided reAct creates the graph Supervisor."""
        from cloudra.core.agent import Follower
        from cloudra.core.react import reAct
        from cloudra.persistence.database import ConversationDB

        conv_id = "test-react"
        db_path = str(tmp_path / "test.db")
        db = ConversationDB.from_path(db_path)
        db.init()
        monkeypatch.setattr("cloudra.core.react.get_database_path", lambda _conv_id: db_path)

        agent = Follower(
            id="a-test",
            name="tester",
            prompt="测试",
            query="测试问题",
            conversation_id=conv_id,
            orchestration_mode="dag_guided",
        )
        react = reAct(agent)
        assert react.supervisor is not None
        assert not hasattr(react.supervisor, "interval")


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
