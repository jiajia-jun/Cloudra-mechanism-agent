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


def test_build_knowledge_query_includes_tool_and_summary():
    query = build_knowledge_query("log_parser", {"path": "/tmp/x.log"}, "imaginary frequency 1")
    assert query.startswith("log_parser")
    assert "/tmp/x.log" in query
    assert "imaginary frequency 1" in query


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
