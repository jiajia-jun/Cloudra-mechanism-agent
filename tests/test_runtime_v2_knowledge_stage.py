"""KnowledgeStage: 计算工具返回后自动检索 chem-kb 并 push 一次性提示。"""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.knowledge import (
    KnowledgeEntry,
    clear_knowledge_providers,
    register_knowledge_provider,
)
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
from cloudra.runtime_v2.policies.knowledge_stage import (
    KnowledgeStage,
    build_knowledge_query,
    is_compute_tool,
)
from cloudra.runtime_v2.schemas import AgentCapabilities, AgentSession, PermissionSet, RuntimeSettings


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_knowledge_providers()
    yield
    clear_knowledge_providers()


class _FakeProvider:
    name = "fake-kb"

    def search(self, query, *, limit=5):
        return [
            KnowledgeEntry(
                title="SCF convergence fix",
                content="switch to quadratically convergent SCF",
                evidence_level="L0",
                source="kb:1",
                score=0.9,  # v13：成功路径要求 top 分过阈值才注入
            )
        ]


class _LowScoreProvider:
    """成功但低置信：模拟"查询与库毫无关系，向量通道硬凑的近邻"。"""

    name = "low-score-kb"

    def search(self, query, *, limit=5):
        return [
            KnowledgeEntry(
                title="weak match",
                content="barely related",
                evidence_level="L0",
                source="kb:2",
                score=0.31,
            )
        ]


def _ctx(notices=None) -> PipelineContext:
    agent = AgentSession(
        id="as1",
        project_id="prj",
        role_id="coordinator",
        display_name="c",
        settings=RuntimeSettings(),
    )
    return PipelineContext(
        agent=agent,
        run_id="r1",
        settings_snapshot=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["*"]),
        inbox_messages=[],
        emit=lambda *a, **k: None,
        notices=notices,
    )


def test_is_compute_tool_semantics():
    assert is_compute_tool("submit_compute_job")  # dag_compute_entry
    assert is_compute_tool("log_parser")  # dag_evidence_producer
    assert is_compute_tool("thermo_analysis")  # dag_evidence_producer
    assert not is_compute_tool("agent_hub")
    assert not is_compute_tool("stop")
    assert not is_compute_tool("bash")


def test_build_knowledge_query_short_and_focused():
    # v13：短参数保留，>120 字符长串与纯数字丢弃，不 dump 整个 summary
    query = build_knowledge_query(
        "submit_compute_job",
        {"input_file": "/tmp/TS1_gaussian.gjf", "nproc": "16",
         "blob": "x" * 300},
        "job submitted ok",
    )
    assert query.startswith("submit_compute_job")
    assert "/tmp/TS1_gaussian.gjf" in query
    assert "16" not in query.split("/tmp")[0]  # 纯数字参数不进查询
    assert "xxxx" not in query and "job submitted ok" not in query
    assert len(query) <= 200


def test_build_knowledge_query_keeps_error_window():
    summary = ('{"scf_energy_hartree": -231.4, "note": "x" * 40} Convergence failure '
               'after 50 cycles, L502 in link — try scf=xqc and tighter grid')
    query = build_knowledge_query("log_parser", {"log_path": "/tmp/TS1.log"}, summary)
    assert "Convergence failure" in query
    assert "L502" in query
    # 报错窗口之外的 JSON 头部不整体进查询
    assert "scf_energy_hartree" not in query
    assert len(query) <= 200


def test_build_knowledge_query_capped_at_200():
    query = build_knowledge_query("log_parser", {"p": "y" * 100}, "failed " + "z" * 500)
    assert len(query) <= 200


@pytest.mark.asyncio
async def test_compute_tool_finish_pushes_library_hits():
    register_knowledge_provider(_FakeProvider())
    stage = KnowledgeStage()
    notices = NoticeManager()
    ctx = _ctx(notices)

    await stage.after_tool(
        ctx,
        ToolCall(id="t1", name="submit_compute_job", arguments={"smiles": "CC"}),
        ToolResult(is_success=True, summary="job submitted"),
    )

    pushed = notices.collect(ctx.agent.id)
    assert len(pushed) == 1
    assert "SCF convergence fix" in pushed[0]["content"]
    assert "submit_compute_job" in pushed[0]["content"]


@pytest.mark.asyncio
async def test_non_compute_tool_does_not_push():
    register_knowledge_provider(_FakeProvider())
    stage = KnowledgeStage()
    notices = NoticeManager()
    ctx = _ctx(notices)

    await stage.after_tool(
        ctx,
        ToolCall(id="t1", name="agent_hub", arguments={}),
        ToolResult(is_success=True, summary="ok"),
    )

    assert notices.collect(ctx.agent.id) == []


@pytest.mark.asyncio
async def test_no_provider_no_push():
    stage = KnowledgeStage()
    notices = NoticeManager()
    ctx = _ctx(notices)

    await stage.after_tool(
        ctx,
        ToolCall(id="t1", name="log_parser", arguments={}),
        ToolResult(is_success=True, summary="ok"),
    )

    assert notices.collect(ctx.agent.id) == []


# ---------------------------------------------------------------------------
# Task 4（P1）：知识服务不可用/空结果必须降级，绝不阻断计算链路
# ---------------------------------------------------------------------------

class _FailingProvider:
    """边界替身：模拟超时/异常的知识服务。"""

    name = "failing-kb"

    def search(self, query, *, limit=5):
        raise TimeoutError("knowledge service timed out")


class _EmptyProvider:
    name = "empty-kb"

    def search(self, query, *, limit=5):
        return []


@pytest.mark.asyncio
async def test_provider_failure_degrades_without_blocking_or_disabling_stage():
    """服务超时：after_tool 不抛、不 push，也绝不放行/阻断带宽变化——
    before_tool 始终 allow（知识检索是纯拉取注入，不是门禁）。"""
    register_knowledge_provider(_FailingProvider())
    stage = KnowledgeStage()
    notices = NoticeManager()
    ctx = _ctx(notices)

    verdict = await stage.before_tool(
        ctx, ToolCall(id="t0", name="submit_compute_job", arguments={"input_file": "x.gjf"})
    )
    assert verdict.outcome == "allow"

    await stage.after_tool(
        ctx,
        ToolCall(id="t1", name="submit_compute_job", arguments={"input_file": "x.gjf"}),
        ToolResult(is_success=True, summary="job submitted"),
    )
    assert notices.collect(ctx.agent.id) == []


@pytest.mark.asyncio
async def test_empty_results_degrade_and_later_hits_still_work():
    """空结果安静降级；随后服务恢复（有命中）时同一 stage 实例照常注入——
    knowledge 段从不因一次失败被关闭。"""
    register_knowledge_provider(_EmptyProvider())
    stage = KnowledgeStage()
    notices = NoticeManager()
    ctx = _ctx(notices)

    await stage.after_tool(
        ctx,
        ToolCall(id="t1", name="log_parser", arguments={"log_path": "x.log"}),
        ToolResult(is_success=False, summary="parse failed"),
    )
    assert notices.collect(ctx.agent.id) == []

    clear_knowledge_providers()
    register_knowledge_provider(_FakeProvider())
    await stage.after_tool(
        ctx,
        ToolCall(id="t2", name="log_parser", arguments={"log_path": "y.log"}),
        ToolResult(is_success=True, summary="ok"),
    )
    pushed = notices.collect(ctx.agent.id)
    assert len(pushed) == 1 and "SCF convergence fix" in pushed[0]["content"]


# ---------------------------------------------------------------------------
# v13 注入分级：失败必注入；成功仅高分注入（压上下文噪声）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_success_with_low_score_not_pushed():
    """成功 + 低置信命中：宁可错过也不注入近似噪声。"""
    register_knowledge_provider(_LowScoreProvider())
    stage = KnowledgeStage()
    notices = NoticeManager()
    ctx = _ctx(notices)

    await stage.after_tool(
        ctx,
        ToolCall(id="t1", name="log_parser", arguments={"log_path": "x.log"}),
        ToolResult(is_success=True, summary="parsed cleanly"),
    )
    assert notices.collect(ctx.agent.id) == []


@pytest.mark.asyncio
async def test_failure_pushes_even_with_low_score():
    """失败必注入：排障价值最高，低置信也值得让 agent 看一眼。"""
    register_knowledge_provider(_LowScoreProvider())
    stage = KnowledgeStage()
    notices = NoticeManager()
    ctx = _ctx(notices)

    await stage.after_tool(
        ctx,
        ToolCall(id="t1", name="log_parser", arguments={"log_path": "x.log"}),
        ToolResult(is_success=False, summary="Error termination via Lnk1e (L502)"),
    )
    pushed = notices.collect(ctx.agent.id)
    assert len(pushed) == 1 and "weak match" in pushed[0]["content"]
