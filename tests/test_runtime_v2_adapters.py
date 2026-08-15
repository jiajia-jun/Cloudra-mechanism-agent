"""Adapter tests: old LLM/tool registry bridges into runtime_v2 protocols."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.adapters import (
    LegacyLLMProvider,
    LegacyToolExecutor,
    _parse_tool_calls,
    legacy_tool_schemas,
)
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command, RuntimeSettings


def test_legacy_tool_schemas_filters_by_name():
    schemas = legacy_tool_schemas(["stop"])
    names = [s["function"]["name"] for s in schemas]
    assert names == ["stop"]
    assert legacy_tool_schemas(["*"]) != []


def test_parse_tool_calls_handles_json_args():
    raw = SimpleNamespace(
        message=SimpleNamespace(
            tool_calls=[
                SimpleNamespace(
                    id="tc1",
                    function=SimpleNamespace(name="stop", arguments='{"reason": "done"}'),
                )
            ]
        )
    )
    calls = _parse_tool_calls(raw)
    assert calls[0].name == "stop"
    assert calls[0].arguments == {"reason": "done"}


@pytest.mark.asyncio
async def test_legacy_llm_provider_builds_request_and_parses_response():
    sent = {}

    class FakeClient:
        last_usage = {"prompt_tokens": 11, "completion_tokens": 2}

        async def create_with_retry(self, **kwargs):
            sent.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id="tc1",
                                    function=SimpleNamespace(name="stop", arguments='{"reason":"done"}'),
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ]
            )

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    agent = SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(model="deepseek-v4", base_url="https://api.example/", api_key="sk-x"),
    )
    response = await provider.complete(agent, [{"role": "user", "content": "hi"}], ["stop"])
    assert sent["model"] == "deepseek-v4"
    assert sent["tools"][0]["function"]["name"] == "stop"
    assert response.tool_calls[0].name == "stop"
    assert response.usage["prompt_tokens"] == 11


@pytest.mark.asyncio
async def test_legacy_tool_executor_runs_stop_tool():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "go"},
        )
    )
    agent = result.data
    executor = LegacyToolExecutor(core)
    from cloudra.runtime_v2.policies.base import ToolCall

    output = await executor.execute(agent, ToolCall(id="tc1", name="stop", arguments={"reason": "done"}))
    assert output.is_success is True
    assert "Task stopped" in output.summary


@pytest.mark.asyncio
async def test_legacy_tool_executor_reports_unknown_tool():
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "p"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator", "query": "go"},
        )
    )
    from cloudra.runtime_v2.policies.base import ToolCall

    output = await LegacyToolExecutor(core).execute(
        result.data, ToolCall(id="tc1", name="does_not_exist", arguments={})
    )
    assert output.is_success is False
    assert "unknown tool" in output.summary
