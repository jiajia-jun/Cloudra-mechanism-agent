"""search surface: schema, native-search mutation, executor reject of source=web."""

import pytest
from pydantic import ValidationError

from cloudra.runtime_v2.adapters import apply_native_search_to_schemas
from cloudra.tools.Searchtool.search import Search, Search_input_schema, Search_output_schema


def test_search_schema_default_source_is_web():
    schema = Search().tool_schema_json()["function"]["parameters"]
    assert schema["properties"]["source"]["default"] == "web"
    assert set(schema["properties"]["source"]["enum"]) == {"web", "arxiv", "openalex"}
    assert "mode" in schema["properties"]
    assert Search_input_schema.model_fields["source"].default == "web"


@pytest.mark.parametrize("field,hit", [
    ("results", {"title": "A result", "url": 7, "snippet": "A summary", "source": "brave"}),
    ("content", {"title": "A paper", "doi": None, "authors": "Jane Doe"}),
])
def test_search_output_rejects_malformed_hit_fields(field, hit):
    """Result items must carry usable URLs and author lists across the bridge."""
    with pytest.raises(ValidationError):
        Search_output_schema(**{field: [hit]})


@pytest.mark.parametrize("field,hit", [
    ("results", {"title": None, "url": "https://example.org", "snippet": None,
                 "source": "tavily", "published": None}),
    ("content", {"title": "A preprint", "journal_ref": None, "doi": None,
                 "abstract": "A summary", "authors": ["Jane Doe"], "categories": ["physics"],
                 "primary_category": "physics", "pdf_url": "https://arxiv.org/pdf/example",
                 "comment": None, "links": ["https://arxiv.org/abs/example"]}),
    ("content", {"title": None, "doi": None, "published_date": None, "source": "OpenAlex",
                 "abstract": "No abstract available", "authors": [None], "concepts": [None],
                 "pdf_url": None}),
])
def test_search_output_preserves_provider_fields_and_nulls(field, hit):
    output = Search_output_schema(**{field: [hit]})
    assert output.model_dump(mode="json")[field] == [hit]


def test_native_search_drops_web_from_source_not_the_tool():
    schemas = [Search().tool_schema_json(), {"type": "function", "function": {"name": "bash"}}]
    out = apply_native_search_to_schemas(schemas, native_on=True)
    names = [s["function"]["name"] for s in out]
    assert "search" in names and "bash" in names
    search = next(s for s in out if s["function"]["name"] == "search")
    enum = search["function"]["parameters"]["properties"]["source"]["enum"]
    assert set(enum) == {"arxiv", "openalex"}
    assert search["function"]["parameters"]["properties"]["source"]["default"] == "arxiv"


@pytest.mark.asyncio
async def test_executor_rejects_search_web_when_native_on(monkeypatch):
    from types import SimpleNamespace

    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies.base import ToolCall
    from cloudra.runtime_v2.schemas import Command

    ran = {"web": False}

    async def _fake_web(*_a, **_k):
        ran["web"] = True
        return {"is_success": True, "results": []}

    monkeypatch.setattr("cloudra.tools.Searchtool._web.run", _fake_web)
    monkeypatch.setattr(
        "cloudra.runtime_v2.adapters._native_search_adapter_for",
        lambda _settings: SimpleNamespace(transport="chat"),
    )
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    spawned = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "go"},
        )
    )
    output = await LegacyToolExecutor(core).execute(
        spawned.data,
        ToolCall(id="tc1", name="search", arguments={"query": "q", "source": "web"}),
    )
    assert output.is_success is False
    assert ran["web"] is False
    assert "native" in output.summary.lower() or "arxiv" in output.summary.lower()
