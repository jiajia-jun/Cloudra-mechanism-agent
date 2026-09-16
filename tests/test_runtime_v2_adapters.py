"""Adapter tests: old LLM/tool registry bridges into runtime_v2 protocols."""

from __future__ import annotations

import asyncio
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


class _EmptyStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def _recording_client(sent: dict):
    class FakeClient:
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            sent.update(kwargs)
            return _EmptyStream()

    return FakeClient()


def _js_agent(protocol, *, current_run=None):
    return SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(
            model="m",
            base_url="https://api.example/",
            api_key="sk-x",
            invocation_protocol=protocol,
        ),
        current_run=current_run,
    )


@pytest.mark.asyncio
async def test_js_mode_projects_js_exec_and_does_not_append_instructions():
    """Task 2 新契约：adapter 不再把 JS instructions 追加到请求尾部；
    它由 LegacyContextPrefix 在上下文初始化时安装一次（见
    test_js_instructions_installed_once_via_context_prefix）。"""
    from cloudra.runtime_v2.schemas import InvocationProtocol

    sent: dict = {}
    provider = LegacyLLMProvider(client_factory=lambda settings: _recording_client(sent))
    agent = _js_agent(InvocationProtocol.JAVASCRIPT)
    messages = [{"role": "user", "content": "hi"}]
    await provider.complete(agent, messages, ["echo", "stop"])
    names = [s["function"]["name"] for s in sent["tools"]]
    assert names == ["js_exec", "stop"]  # business tools are guest-only
    assert sent["parallel_tool_calls"] is False
    assert all(
        "JavaScript invocation protocol" not in str(m.get("content"))
        for m in sent["messages"]
    )
    # The caller's message list is not mutated.
    assert messages == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_js_instructions_installed_once_via_context_prefix(tmp_path):
    """JS 调用协议是静态前缀的一部分：install 恰好安装一次，refresh 不重发。"""
    from cloudra.runtime_v2.schemas import InvocationProtocol

    agent = SimpleNamespace(
        id="as_js_prefix",
        role_id="coordinator",
        project_id="prj_js_prefix",
        current_run=None,
        settings=RuntimeSettings(
            model="m",
            base_url="https://api.example/",
            api_key="sk-x",
            invocation_protocol=InvocationProtocol.JAVASCRIPT,
            clean_context=True,
        ),
    )
    prefix = LegacyPromptProvider().begin_context(
        agent=agent, workspace_dir=str(tmp_path), tool_names=["echo", "stop"]
    )
    installed = await prefix.install()
    js_messages = [
        m for m in installed if "JavaScript invocation protocol" in str(m.get("content"))
    ]
    assert len(js_messages) == 1
    assert "ToolResponse" in js_messages[0]["content"]
    assert "declare const tools" in js_messages[0]["content"]
    assert prefix.matches(installed)
    assert not prefix.matches([{"role": "user", "content": "unrelated"}])
    # 动态源无变化：refresh 静默，JS instructions 不重复发送。
    assert await prefix.refresh() == []


@pytest.mark.asyncio
async def test_clean_context_provider_disables_implicit_project_sources(monkeypatch):
    captured = {}

    class FakeAssembly:
        identity_messages = ({"role": "system", "content": "task skill"},)
        observation_messages = ()
        observation_sources = ()
        prompt_revision = "sha256:fake"
        capability_revision = "sha256:fakecaps"

    class FakeAssembler:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def assemble(self, **kwargs):
            return FakeAssembly()

    import cloudra.runtime.prompt_assembler as prompt_module
    monkeypatch.setattr(prompt_module, "PromptAssembler", FakeAssembler)
    agent = _js_agent("traditional")
    agent.id = "agent"
    agent.project_id = "project"
    agent.settings.clean_context = True
    prefix = LegacyPromptProvider().begin_context(agent=agent, workspace_dir=None, tool_names=[])
    messages = await prefix.install()
    assert messages[0]["content"] == "task skill"
    assert captured["include_memory"] is False
    assert captured["include_agents_md"] is False


@pytest.mark.asyncio
async def test_traditional_mode_has_no_js_surface():
    sent: dict = {}
    provider = LegacyLLMProvider(client_factory=lambda settings: _recording_client(sent))
    agent = _js_agent("traditional")
    messages = [{"role": "user", "content": "hi"}]
    await provider.complete(agent, messages, ["stop"])
    names = [s["function"]["name"] for s in sent["tools"]]
    assert names == ["stop"]
    assert "parallel_tool_calls" not in sent
    assert all(
        not (m.get("role") == "system" and "JavaScript invocation protocol" in str(m.get("content")))
        for m in sent["messages"]
    )


@pytest.mark.asyncio
async def test_js_mode_retries_without_parallel_flag_for_old_gateway():
    from cloudra.runtime_v2.schemas import InvocationProtocol

    calls: list[dict] = []

    class LegacyGateway:
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            calls.append(dict(kwargs))
            if "parallel_tool_calls" in kwargs:
                raise TypeError("unexpected keyword argument 'parallel_tool_calls'")
            return _EmptyStream()

    provider = LegacyLLMProvider(client_factory=lambda settings: LegacyGateway())
    await provider.complete(_js_agent(InvocationProtocol.JAVASCRIPT), [{"role": "user", "content": "hi"}], ["echo"])
    assert "parallel_tool_calls" in calls[0]
    assert "parallel_tool_calls" not in calls[1]


@pytest.mark.asyncio
async def test_run_frozen_protocol_survives_mid_run_settings_change():
    from cloudra.runtime_v2.schemas import InvocationProtocol

    sent: dict = {}
    provider = LegacyLLMProvider(client_factory=lambda settings: _recording_client(sent))
    # The active run froze javascript; the settings slot already moved on.
    agent = _js_agent(
        InvocationProtocol.TRADITIONAL,
        current_run=SimpleNamespace(invocation_protocol=InvocationProtocol.JAVASCRIPT),
    )
    await provider.complete(agent, [{"role": "user", "content": "hi"}], ["echo"])
    names = [s["function"]["name"] for s in sent["tools"]]
    assert names == ["js_exec"]
    assert legacy_tool_schemas(["*"]) != []


@pytest.mark.asyncio
async def test_reasoning_effort_sent_when_set():
    sent: dict = {}
    provider = LegacyLLMProvider(client_factory=lambda settings: _recording_client(sent))
    agent = _js_agent("traditional")
    agent.settings.reasoning_effort = "high"
    await provider.complete(agent, [{"role": "user", "content": "hi"}], ["stop"])
    assert sent["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_reasoning_effort_omitted_when_unset():
    sent: dict = {}
    provider = LegacyLLMProvider(client_factory=lambda settings: _recording_client(sent))
    await provider.complete(_js_agent("traditional"), [{"role": "user", "content": "hi"}], ["stop"])
    assert "reasoning_effort" not in sent


def test_legacy_default_settings_reasoning_effort_fallback(monkeypatch):
    """reasoning_effort 回落规则与其他字段一致：agent 未设时取全局 config
    对应槽位（coordinator 角色用 coordinator 槽，其余用 follower 槽），
    agent 显式设置优先。"""
    from cloudra.infra.config import get_config
    from cloudra.runtime_v2.adapters import legacy_default_settings

    cfg = get_config()
    monkeypatch.setattr(cfg.coordinator, "reasoning_effort", "low")
    monkeypatch.setattr(cfg.follower, "reasoning_effort", "minimal")

    coordinator = SimpleNamespace(role_id="coordinator", settings=RuntimeSettings(model="m"))
    assert legacy_default_settings(coordinator).reasoning_effort == "low"

    follower = SimpleNamespace(role_id="researcher", settings=RuntimeSettings(model="m"))
    assert legacy_default_settings(follower).reasoning_effort == "minimal"

    explicit = SimpleNamespace(
        role_id="coordinator", settings=RuntimeSettings(model="m", reasoning_effort="high")
    )
    assert legacy_default_settings(explicit).reasoning_effort == "high"


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


def test_to_api_message_supports_reasoning_alias():
    out = _to_api_message({"role": "assistant", "content": "hi", "reasoning": "step by step"})
    assert out["reasoning_content"] == "step by step"


@pytest.mark.asyncio
async def test_deepseek_thinking_mode_backfills_missing_reasoning_content():
    """DeepSeek 思考模式要求历史里每条 assistant 消息都回传
    reasoning_content；压缩摘要等 harness 生成的 assistant 消息没有思考
    内容，缺一条即 400，回填单个空格（空串同样被拒）。"""
    sent: dict = {}
    provider = LegacyLLMProvider(client_factory=lambda settings: _recording_client(sent))
    agent = _js_agent("traditional")
    agent.settings.base_url = "https://api.deepseek.com"
    agent.settings.native_search = "off"  # 避免走 Responses 传输，聚焦 chat 路径
    agent.settings.reasoning_effort = "low"
    await provider.complete(
        agent,
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "[Context compact] summary"},
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "kept",
                "tool_calls": [{"id": "tc1", "name": "echo", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "tc1", "content": "ok"},
        ],
        ["stop"],
    )
    assistants = [m for m in sent["messages"] if m["role"] == "assistant"]
    assert assistants[0]["reasoning_content"] == " "
    assert assistants[1]["reasoning_content"] == "kept"


@pytest.mark.asyncio
async def test_reasoning_backfill_scoped_to_deepseek_thinking_mode():
    # 非 DeepSeek 端点 + 思考模式：不回填。
    sent: dict = {}
    provider = LegacyLLMProvider(client_factory=lambda settings: _recording_client(sent))
    agent = _js_agent("traditional")
    agent.settings.reasoning_effort = "low"
    await provider.complete(agent, [{"role": "assistant", "content": "s"}], ["stop"])
    assert "reasoning_content" not in sent["messages"][0]
    # DeepSeek 端点但思考模式关闭：不回填。
    sent = {}
    provider = LegacyLLMProvider(client_factory=lambda settings: _recording_client(sent))
    agent = _js_agent("traditional")
    agent.settings.base_url = "https://api.deepseek.com"
    agent.settings.native_search = "off"
    await provider.complete(agent, [{"role": "assistant", "content": "s"}], ["stop"])
    assert "reasoning_content" not in sent["messages"][0]


def test_extract_delta_reasoning_compatibility():
    from cloudra.runtime_v2.adapters import _extract_delta_reasoning

    # DeepSeek style: reasoning_content attribute
    d1 = SimpleNamespace(reasoning_content="think deepseek")
    assert _extract_delta_reasoning(d1) == "think deepseek"

    # OpenRouter / vLLM style: reasoning attribute
    d2 = SimpleNamespace(reasoning="think openrouter")
    assert _extract_delta_reasoning(d2) == "think openrouter"

    # Anthropic / custom gateway: thinking attribute
    d3 = SimpleNamespace(thinking="think claude")
    assert _extract_delta_reasoning(d3) == "think claude"

    # Pydantic v2 model_extra dictionary
    d4 = SimpleNamespace(model_extra={"reasoning": "think extra"})
    assert _extract_delta_reasoning(d4) == "think extra"

    # Dict delta (requests fallback)
    d5 = {"reasoning": "think dict"}
    assert _extract_delta_reasoning(d5) == "think dict"

    # Structured reasoning list
    d6 = SimpleNamespace(reasoning=[{"text": "part1 "}, {"text": "part2"}])
    assert _extract_delta_reasoning(d6) == "part1 part2"

    # None / empty
    d7 = SimpleNamespace(content="just content")
    assert _extract_delta_reasoning(d7) is None


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
        settings=RuntimeSettings(model="deepseek-v4", base_url="https://api.example/", api_key="sk-x", invocation_protocol="traditional"),
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
async def test_legacy_llm_provider_streams_openrouter_reasoning():
    """Verify that delta.reasoning (OpenRouter style) is captured into reasoning_content."""
    def _chunk_or(content=None, reasoning=None):
        # OpenRouter sends delta.reasoning, not delta.reasoning_content
        delta = SimpleNamespace(content=content, tool_calls=None, reasoning=reasoning)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=None)])

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
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            return FakeStream(
                [
                    _chunk_or(reasoning="Thinking with "),
                    _chunk_or(reasoning="OpenRouter"),
                    _chunk_or(content="Here is the answer"),
                ]
            )

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    agent = SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(model="anthropic/claude-sonnet-5", base_url="https://openrouter.ai/api/v1", api_key="sk-or-x"),
    )
    deltas: list[tuple[str, str]] = []

    async def collect(kind: str, delta: str) -> None:
        deltas.append((kind, delta))

    response = await provider.complete(
        agent,
        [{"role": "user", "content": "hi"}],
        [],
        on_delta=collect,
    )
    assert response.content == "Here is the answer"
    assert response.reasoning == "Thinking with OpenRouter"
    assert "".join(d for kind, d in deltas if kind == "reasoning") == "Thinking with OpenRouter"
    assert "".join(d for kind, d in deltas if kind == "content") == "Here is the answer"


@pytest.mark.asyncio
async def test_legacy_llm_provider_captures_reasoning_from_final_message():
    """DeepSeek thinking mode may put reasoning_content on choice.message of
    the last chunk (delta empty). Missing that 400s the next tool turn."""

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
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            return FakeStream(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    content="checking",
                                    tool_calls=None,
                                    reasoning_content=None,
                                ),
                                message=None,
                                finish_reason=None,
                            )
                        ]
                    ),
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                delta=None,
                                message=SimpleNamespace(
                                    content="checking",
                                    reasoning_content="need the file first",
                                ),
                                finish_reason="stop",
                            )
                        ]
                    ),
                ]
            )

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    agent = SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(
            model="deepseek-v4-flash",
            base_url="https://api.example/",
            api_key="sk-x",
            invocation_protocol="traditional",
        ),
    )
    response = await provider.complete(
        agent, [{"role": "user", "content": "hi"}], [], on_delta=None
    )
    assert response.content == "checking"
    assert response.reasoning == "need the file first"
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_legacy_llm_provider_complete_times_out_loudly():
    """A hung provider must fail the complete() call instead of blocking the
    event loop / starving a fresh NI1 coordinator indefinitely."""

    class HungClient:
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            await asyncio.Event().wait()

    provider = LegacyLLMProvider(client_factory=lambda settings: HungClient())
    agent = SimpleNamespace(
        id="as_timeout",
        role_id="coordinator",
        settings=RuntimeSettings(
            model="deepseek-v4-flash",
            base_url="https://api.example/",
            api_key="sk-x",
            timeout=1,
            invocation_protocol="traditional",
        ),
    )
    with pytest.raises(TimeoutError, match="timed out after 1s"):
        await provider.complete(
            agent, [{"role": "user", "content": "hi"}], [], on_delta=None
        )


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


def _chunk(content=None, finish_reason=None, tool_calls=None):
    delta = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=None,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)]
    )


def _tool_call_chunk(index, name, arguments):
    """完整（非分片）tool_call delta chunk（model_dump 产出 wire dict 形态）。"""

    class _FakeToolCall:
        def __init__(self):
            self.index = index
            self.id = f"tc_{index}"
            self.function = SimpleNamespace(name=name, arguments=arguments)

        def model_dump(self, exclude_none=True):
            return {
                "index": self.index,
                "id": self.id,
                "function": {"name": name, "arguments": arguments},
            }

    return _chunk(finish_reason="tool_calls", tool_calls=[_FakeToolCall()])


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
            model="deepseek-v4-flash", base_url="https://api.deepseek.com", api_key="sk-x", invocation_protocol="traditional"
        ),
    )


@pytest.mark.asyncio
async def test_native_search_renames_search_schema_and_unwires_response():
    """DeepSeek Responses 原生搜索：发送 schema 的 search 改名 search_sources
    （服务端拒绝与 web_search 同存的 function "search"），响应侧还原为 search。"""
    sent = {}

    class FakeClient:
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            raise AssertionError("native search must use the responses transport")

        async def create_responses_with_retry(self, **kwargs):
            sent.update(kwargs)
            return _FakeStream(
                [
                    _tool_call_chunk(
                        0,
                        "search_sources",
                        '{"source": "arxiv", "query": "cope rearrangement"}',
                    ),
                    _chunk(content="ok", finish_reason="stop"),
                ]
            )

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    response = await provider.complete(
        _deepseek_agent(), [{"role": "user", "content": "hi"}], ["search", "stop"]
    )

    tool_names = [t["function"]["name"] for t in sent["tools"]]
    assert "search_sources" in tool_names
    assert "search" not in tool_names
    assert "stop" in tool_names
    search = next(t for t in sent["tools"] if t["function"]["name"] == "search_sources")
    assert set(search["function"]["parameters"]["properties"]["source"]["enum"]) == {
        "arxiv",
        "openalex",
    }
    assert search["function"]["parameters"]["properties"]["source"]["default"] == "arxiv"
    assert {"type": "web_search"} in sent["extra_body"]["tools"]

    assert response.content == "ok"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "search"
    assert response.tool_calls[0].arguments == {
        "source": "arxiv",
        "query": "cope rearrangement",
    }


def test_apply_native_search_to_schemas_rename_search_flag():
    """rename_search 仅对 DeepSeek 场景打开：普通原生搜索（openrouter 等）不改名。"""
    from cloudra.runtime_v2.adapters import (
        DEEPSEEK_WIRE_SEARCH_NAME,
        apply_native_search_to_schemas,
    )

    schema = {
        "type": "function",
        "function": {
            "name": "search",
            "parameters": {
                "properties": {
                    "source": {"enum": ["web", "arxiv", "openalex"], "default": "web"}
                }
            },
        },
    }
    renamed = apply_native_search_to_schemas([schema], native_on=True, rename_search=True)
    assert renamed[0]["function"]["name"] == DEEPSEEK_WIRE_SEARCH_NAME
    kept = apply_native_search_to_schemas([schema], native_on=True)
    assert kept[0]["function"]["name"] == "search"


@pytest.mark.asyncio
async def test_no_native_adapter_keeps_search_tool():
    """未命中适配器时 search 保留（含 source=web）、走 chat 传输。"""
    sent = {}

    class FakeClient:
        last_usage = {}

        async def create_with_retry(self, **kwargs):
            sent.update(kwargs)
            return _FakeStream([_chunk(content="ok", finish_reason="stop")])

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    agent = SimpleNamespace(
        role_id="coordinator",
        settings=RuntimeSettings(model="m", base_url="https://api.example/", api_key="sk-x", invocation_protocol="traditional"),
    )
    await provider.complete(agent, [{"role": "user", "content": "hi"}], ["search"])

    tool_names = [t["function"]["name"] for t in sent["tools"]]
    assert "search" in tool_names
    search = next(t for t in sent["tools"] if t["function"]["name"] == "search")
    assert "web" in search["function"]["parameters"]["properties"]["source"]["enum"]
    assert "extra_body" not in sent


@pytest.mark.asyncio
async def test_prompt_provider_marks_web_search_available_with_native_adapter(monkeypatch, tmp_path):
    """命中原生搜索适配器时 system prompt 注入「联网搜索」段（v1 行为）。"""
    captured = {}

    class FakeAssembly:
        identity_messages = [{"role": "system", "content": "id"}]
        observation_messages = []
        observation_sources = ()
        prompt_revision = "sha256:fake"
        capability_revision = "sha256:fakecaps"

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
        current_run=None,
        settings=_deepseek_agent().settings,
    )
    prefix = LegacyPromptProvider().begin_context(agent=agent, workspace_dir=str(tmp_path), tool_names=["stop"])
    messages = await prefix.install()
    assert captured["web_search_available"] is True
    assert messages[0]["content"] == "id"


def test_legacy_agent_bridge_falls_back_to_default_workspace():
    """存量 workspace_dir=None 的项目：bridge 构造时兜底 per-project 默认工作区，
    不再让 read/write/bash 等工具落进程 cwd（GH #24）。"""
    from pathlib import Path

    from cloudra.infra.config import get_config
    from cloudra.persistence.paths import project_workspace_dir
    from cloudra.runtime_v2.adapters import _LegacyAgentBridge

    agent = SimpleNamespace(
        id="agent-1",
        role_id="coordinator",
        project_id="prj-legacy",
        settings=SimpleNamespace(orchestration_mode=SimpleNamespace(value="standard")),
        capabilities=SimpleNamespace(
            permissions=SimpleNamespace(read=True, write=True, manage=False, script=False, destructive=False)
        ),
    )
    bridge = _LegacyAgentBridge(agent, None)
    assert bridge.working_directory == str(project_workspace_dir("prj-legacy"))
    assert Path(bridge.working_directory).parent == Path(get_config().data_dir) / "workspaces"
    explicit = _LegacyAgentBridge(agent, "/tmp/explicit-ws")
    assert explicit.working_directory == "/tmp/explicit-ws"


@pytest.mark.asyncio
async def test_usage_cache_details_pass_through_to_response():
    """LLMResponse.usage 保留 client.last_usage 的原始缓存细项（不丢
    input_tokens_details.cached_tokens），缺失也不补 0。"""

    class FakeClient:
        last_usage = {
            "prompt_tokens": 100,
            "completion_tokens": 5,
            "total_tokens": 105,
            "input_tokens_details": {"cached_tokens": 80},
        }

        async def create_with_retry(self, **kwargs):
            return _FakeStream([_chunk(content="ok", finish_reason="stop")])

    provider = LegacyLLMProvider(client_factory=lambda settings: FakeClient())
    response = await provider.complete(_js_agent("traditional"), [{"role": "user", "content": "hi"}], ["stop"])
    assert response.usage["input_tokens_details"]["cached_tokens"] == 80
    assert response.usage["prompt_tokens"] == 100
