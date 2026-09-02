"""Adapter tests: old LLM/tool registry bridges into runtime_v2 protocols."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.adapters import (
    LegacyLLMProvider,
    LegacyPromptProvider,
    LegacyToolExecutor,
    _parse_tool_calls,
    _to_api_message,
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


def test_to_api_message_echoes_reasoning_content():
    """Thinking-mode APIs (DeepSeek etc.) 400 if the previous assistant
    turn's reasoning_content is dropped when we send the next request."""
    out = _to_api_message(
        {
            "role": "assistant",
            "content": "checking",
            "reasoning_content": "need the file first",
            "tool_calls": [{"id": "tc1", "name": "echo", "arguments": {"x": 1}}],
        }
    )
    assert out["reasoning_content"] == "need the file first"
    assert out["tool_calls"][0]["function"]["name"] == "echo"
    assert '"x"' in out["tool_calls"][0]["function"]["arguments"]


def test_to_api_message_omits_reasoning_when_absent():
    out = _to_api_message({"role": "assistant", "content": "hi"})
    assert "reasoning_content" not in out


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
async def test_legacy_llm_provider_streams_and_parses_response():
    sent = {}

    def _chunk(content=None, tool_calls=None, finish_reason=None, reasoning=None):
        delta = SimpleNamespace(content=content, tool_calls=tool_calls, reasoning_content=reasoning)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])

    class FakeStream:
        def __init__(self, chunks):
            self._iter = iter(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    class FakeClient:
        last_usage = {"prompt_tokens": 11, "completion_tokens": 2}

        async def create_with_retry(self, **kwargs):
            sent.update(kwargs)
            return FakeStream(
                [
                    _chunk(content="Done", reasoning="thinking"),
                    _chunk(content="."),
                    _chunk(
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="tc1",
                                type="function",
                                function={"name": "stop", "arguments": '{"reason":"done"}'},
                            )
                        ],
                        finish_reason="tool_calls",
                    ),
                ]
            )

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    agent = SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(model="deepseek-v4", base_url="https://api.example/", api_key="sk-x"),
    )
    deltas: list[tuple[str, str]] = []

    async def collect(kind: str, delta: str) -> None:
        deltas.append((kind, delta))

    response = await provider.complete(
        agent,
        [{"role": "user", "content": "hi"}],
        ["stop"],
        on_delta=collect,
    )
    assert sent["model"] == "deepseek-v4"
    assert sent["stream"] is True
    assert sent["tools"][0]["function"]["name"] == "stop"
    assert response.content == "Done."
    assert response.tool_calls[0].name == "stop"
    assert response.tool_calls[0].arguments == {"reason": "done"}
    assert response.finish_reason == "tool_calls"
    assert response.usage["prompt_tokens"] == 11
    # on_delta receives the throttled stream; concatenation is lossless.
    assert "".join(d for kind, d in deltas if kind == "content") == "Done."
    assert "".join(d for kind, d in deltas if kind == "reasoning") == "thinking"


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
async def test_legacy_tool_executor_attaches_bridge_to_narrowed_tools():
    """Regression: tools narrowing `subagent: Agent` (dag_view, goal_set, …)
    rejected the duck-typed bridge at pydantic construction."""
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
        result.data, ToolCall(id="tc1", name="goal_set", arguments={"objective": "hold the line"})
    )
    assert output.is_success is True, output.summary
    assert "Goal anchor set" in output.summary


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

    retired = await LegacyToolExecutor(core).execute(
        result.data, ToolCall(id="tc2", name="text_reader", arguments={})
    )
    assert retired.is_success is False
    assert "read" in retired.summary


def _chunk(content=None, finish_reason=None):
    delta = SimpleNamespace(content=content, tool_calls=None, reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


class _FakeStream:
    def __init__(self, chunks):
        self._iter = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _deepseek_agent():
    return SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(
            model="deepseek-v4-flash", base_url="https://api.deepseek.com", api_key="sk-x"
        ),
    )


@pytest.mark.asyncio
async def test_native_search_strips_web_search_and_uses_responses_transport():
    """命中原生搜索适配器（DeepSeek）时：剔除外置 web_search 函数工具（避免
    双重搜索）、注入服务端 web_search 工具、走 /responses 传输。"""
    sent = {}

    class FakeClient:
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            raise AssertionError("native search must use the responses transport")

        async def create_responses_with_retry(self, **kwargs):
            sent.update(kwargs)
            return _FakeStream([_chunk(content="ok", finish_reason="stop")])

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    response = await provider.complete(
        _deepseek_agent(), [{"role": "user", "content": "hi"}], ["web_search", "stop"]
    )

    tool_names = [t["function"]["name"] for t in sent["tools"]]
    assert "web_search" not in tool_names
    assert "stop" in tool_names
    assert {"type": "web_search"} in sent["extra_body"]["tools"]
    assert response.content == "ok"


@pytest.mark.asyncio
async def test_no_native_adapter_keeps_web_search_tool():
    """未命中适配器时 web_search 保留、走 chat 传输。"""
    sent = {}

    class FakeClient:
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            sent.update(kwargs)
            return _FakeStream([_chunk(content="ok", finish_reason="stop")])

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    agent = SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(model="m", base_url="https://api.example/", api_key="sk-x"),
    )
    await provider.complete(agent, [{"role": "user", "content": "hi"}], ["web_search"])

    tool_names = [t["function"]["name"] for t in sent["tools"]]
    assert "web_search" in tool_names
    assert "extra_body" not in sent


@pytest.mark.asyncio
async def test_prompt_provider_marks_web_search_available_with_native_adapter(monkeypatch, tmp_path):
    """命中原生搜索适配器时 system prompt 注入「联网搜索」段（v1 行为）。"""
    captured = {}

    class FakeAssembly:
        identity_messages = [{"role": "system", "content": "id"}]
        observation_messages = []

    class FakeAssembler:
        def __init__(self, **_kwargs):
            pass

        def assemble(self, capability_names, web_search_available=False):
            captured["web_search_available"] = web_search_available
            return FakeAssembly()

    monkeypatch.setattr("cloudra.runtime.prompt_assembler.PromptAssembler", FakeAssembler)
    agent = SimpleNamespace(
        role_id="coordinator",
        project_id="p",
        id="as_x",
        settings=_deepseek_agent().settings,
    )
    messages = await LegacyPromptProvider()(agent=agent, workspace_dir=str(tmp_path), tool_names=["stop"])
    assert captured["web_search_available"] is True
    assert messages[0]["content"] == "id"
