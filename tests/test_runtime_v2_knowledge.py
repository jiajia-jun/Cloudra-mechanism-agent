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
    hits = await search_library("anything", limit=10)
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
    hits = await search_library("anything", limit=10)
    assert hits and all(h["provider"] == "sync-graph" for h in hits)


@pytest.mark.asyncio
async def test_limit_caps_merged_hits():
    register_knowledge_provider(SyncProvider())
    register_knowledge_provider(AsyncProvider())
    hits = await search_library("anything", limit=2)
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_empty_registry_returns_empty():
    assert await search_library("anything") == []


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
