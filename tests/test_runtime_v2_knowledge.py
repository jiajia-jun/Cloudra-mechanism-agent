"""Knowledge provider plugin interface: registry, ranking, hub embedding."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.knowledge import (
    KnowledgeEntry,
    clear_knowledge_providers,
    register_knowledge_provider,
    search_library,
)
from cloudra.runtime_v2.policies.base import ToolCall
from cloudra.runtime_v2.schemas import Command


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_knowledge_providers()
    yield
    clear_knowledge_providers()


class SyncProvider:
    name = "sync-graph"

    def search(self, query, *, limit=5):
        return [
            KnowledgeEntry(
                title="literature hint",
                content="textbook mechanism",
                evidence_level="L0",
                source="doi:10.x",
            ),
            KnowledgeEntry(
                title="verified TS",
                content="IRC confirmed",
                evidence_level="L1",
                score=0.9,
            ),
            {"title": "loose guess", "content": "unverified", "evidence_level": "L2"},
        ]


class AsyncProvider:
    name = "async-graph"

    async def search(self, query, *, limit=5):
        return [
            {
                "title": "refuted claim",
                "content": "disproved step",
                "evidence_level": "L1",
                "falsified": True,
            }
        ]


class BrokenProvider:
    name = "broken"

    def search(self, query, *, limit=5):
        raise RuntimeError("graph store down")


@pytest.mark.asyncio
async def test_search_merges_ranks_and_normalizes():
    register_knowledge_provider(SyncProvider())
    register_knowledge_provider(AsyncProvider())
    hits, errors = await search_library("anything", limit=10)
    assert errors == {}
    # L1 (verified) first, then L0 literature, then L2 hypothesis; the
    # falsified L1 sinks below the clean L1 within its level.
    assert [(h["evidence_level"], h["title"]) for h in hits] == [
        ("L1", "verified TS"),
        ("L1", "refuted claim"),
        ("L0", "literature hint"),
        ("L2", "loose guess"),
    ]
    falsified = next(h for h in hits if h["title"] == "refuted claim")
    assert falsified["falsified"] is True
    assert all(h["provider"] in {"sync-graph", "async-graph"} for h in hits)


@pytest.mark.asyncio
async def test_broken_provider_is_skipped():
    register_knowledge_provider(BrokenProvider())
    register_knowledge_provider(SyncProvider())
    hits, errors = await search_library("anything", limit=10)
    assert errors == {'broken': 'graph store down'}
    assert hits and all(h["provider"] == "sync-graph" for h in hits)


@pytest.mark.asyncio
async def test_limit_caps_merged_hits():
    register_knowledge_provider(SyncProvider())
    register_knowledge_provider(AsyncProvider())
    hits, errors = await search_library("anything", limit=2)
    assert errors == {}
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_empty_registry_returns_empty():
    assert await search_library("anything") == ([], {})


def test_library_render_keeps_complete_source_and_paragraphs():
    from cloudra.runtime_v2.knowledge import render_library_hits

    content = "完整正文\n\n" + "知识内容" * 100 + "\n\n末尾适用条件"
    rendered = render_library_hits([{"title": "来源稿", "content": content, "source": "kb:10"}])
    assert content in rendered


async def _setup_core():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "lib"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    return core, result.data


@pytest.mark.asyncio
async def test_hub_search_includes_library_hits():
    from cloudra.runtime_v2.hub_bridge import handle_hub_tool

    core, agent = await _setup_core()
    register_knowledge_provider(SyncProvider())
    result = await handle_hub_tool(
        core, agent, ToolCall(id="tc1", name="agent_hub", arguments={"action": "search", "keyword": "TS"})
    )
    assert result.is_success
    library = result.data["library"]
    assert [h["title"] for h in library][:2] == ["verified TS", "literature hint"]
    assert "Library hits" in result.summary
    assert "[L1]" in result.summary and "provider: sync-graph" in result.summary


@pytest.mark.asyncio
async def test_hub_search_without_providers_unchanged():
    from cloudra.runtime_v2.hub_bridge import handle_hub_tool

    core, agent = await _setup_core()
    result = await handle_hub_tool(
        core, agent, ToolCall(id="tc1", name="agent_hub", arguments={"action": "search", "keyword": "x"})
    )
    assert result.is_success
    assert result.data["library"] == []
    assert "Library" not in result.summary


@pytest.mark.asyncio
@pytest.mark.parametrize('healthy', [False, True])
async def test_hub_search_reports_provider_failure_without_losing_other_hits(healthy):
    from cloudra.runtime_v2.hub_bridge import handle_hub_tool

    core, agent = await _setup_core()
    register_knowledge_provider(BrokenProvider())
    if healthy:
        register_knowledge_provider(SyncProvider())
    result = await handle_hub_tool(
        core, agent, ToolCall(id='source-failure', name='agent_hub',
                             arguments={'action': 'search', 'keyword': 'TS'})
    )
    assert result.is_success
    assert result.data['sources_status']['library'] == ('partial' if healthy else 'unavailable')
    assert result.data['library_errors'] == {'broken': 'graph store down'}
    assert bool(result.data['library']) is healthy
    assert 'graph store down' in result.summary
    await core.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_success", [True, False])
async def test_compute_tool_results_do_not_search_or_inject_library(is_success):
    from cloudra.runtime_v2.notices import NoticeManager
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.policies.base import ToolResult
    from cloudra.runtime_v2.schemas import AgentCapabilities, InvocationProtocol, PermissionSet
    from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

    core, agent = await _setup_core()
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    queries = []

    class RecordingProvider:
        name = "recording-kb"

        def search(self, query, *, limit=5):
            queries.append(query)
            return [KnowledgeEntry(title="SCF guidance", content="library-only hint", score=0.9)]

    call = ToolCall(id="compute-result", name="log_parser", arguments={"log_path": "/tmp/TS1.log"})
    result = ToolResult(is_success=is_success, summary="Convergence failure L502" if not is_success else "parsed")

    class ToolCallingLLM:
        async def complete(self, agent, messages, tools, **kwargs):
            return LLMResponse(tool_calls=[call])

    class ComputeTools:
        async def execute(self, agent, requested):
            assert requested == call
            return result

    register_knowledge_provider(RecordingProvider())
    notices = NoticeManager()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(core),
        llm=ToolCallingLLM(),
        tools=ComputeTools(),
        notices=notices,
    )
    outcome = await pipeline.run_turn(
        agent=agent,
        run_id="compute-without-retrieval",
        settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["log_parser"]),
        inbox_messages=[],
    )

    assert outcome.tool_exchanges == ((call, result),)
    assert queries == []
    changes = notices.snapshot()["changes"].get(agent.id, [])
    assert all(change["kind"] != "push" for change in changes)

    from cloudra.runtime_v2.hub_bridge import handle_hub_tool

    search_result = await handle_hub_tool(
        core, agent, ToolCall(id="search", name="agent_hub", arguments={"action": "search", "keyword": "SCF"})
    )
    assert queries == ["SCF"]
    assert search_result.data["library"][0]["content"] == "library-only hint"


@pytest.mark.asyncio
@pytest.mark.parametrize("role_id", ["coordinator", "supervisor"])
async def test_javascript_hub_search_delivers_large_source_directly(role_id):
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.schemas import AgentCapabilities, InvocationProtocol, PermissionSet
    from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline

    core, agent = await _setup_core()
    if role_id == "supervisor":
        agent = (await CommandBus(core).execute(Command(
            type="agent.spawn", target={"project_id": agent.project_id},
            payload={"role_id": "supervisor"},
        ))).data
    agent.settings.invocation_protocol = InvocationProtocol.JAVASCRIPT
    body = "完整知识正文\n\n" * 12000 + "最后一段适用条件"

    class LongSourceProvider:
        name = "long-source"

        def search(self, query, *, limit=5):
            return [KnowledgeEntry(title="完整来源", content=body, source="kb:long")]

    call = ToolCall(id="large-search", name="agent_hub", arguments={"action": "search", "keyword": "SCF"})

    class SearchLLM:
        async def complete(self, agent, messages, tools, **kwargs):
            return LLMResponse(tool_calls=[call])

    register_knowledge_provider(LongSourceProvider())
    pipeline = TurnPipeline(
        event_log=core.event_log, stages=default_stages(core),
        llm=SearchLLM(), tools=LegacyToolExecutor(core),
    )
    outcome = await pipeline.run_turn(
        agent=agent, run_id="large-source", settings=agent.settings,
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=["agent_hub"]),
        inbox_messages=[],
    )

    assert len(outcome.tool_exchanges) == 1
    actual_call, result = outcome.tool_exchanges[0]
    assert actual_call == call
    assert result.is_success, result.summary
    assert result.data["library"][0]["content"] == body
    await AgentRunner(core, pipeline)._commit_turn_output(agent, "large-source", outcome)
    model_content = next(
        message["content"] for message in core.contexts.current_messages(agent.id)
        if message.get("tool_call_id") == call.id
    )
    assert len(model_content.encode("utf-8")) > 65536
    # Supervisor serializes its restricted result as JSON; both projections
    # must retain the complete source, including the final paragraph.
    if role_id == "supervisor":
        import json

        assert json.loads(model_content)["library"][0]["content"] == body
    else:
        assert body in model_content


@pytest.mark.asyncio
async def test_direct_hub_keeps_supervisor_action_permissions():
    from cloudra.runtime_v2.adapters import LegacyToolExecutor

    core, coordinator = await _setup_core()
    supervisor = (await CommandBus(core).execute(Command(
        type="agent.spawn", target={"project_id": coordinator.project_id},
        payload={"role_id": "supervisor"},
    ))).data
    result = await LegacyToolExecutor(core).execute(
        supervisor, ToolCall(id="denied-hub", name="agent_hub", arguments={"action": "delete"}),
    )
    assert not result.is_success
    assert "permission denied" in result.data["message"]
