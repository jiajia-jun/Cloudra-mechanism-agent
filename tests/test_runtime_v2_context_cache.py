"""最终传输请求的缓存前缀连续性回归夹具 + Responses 缓存 usage 保真测试。

计划：docs/superpowers/plans/2026-09-13-harness-cache-continuity.md（Task 1/2）。

夹具捕获的是 fake client 实际收到的线缆请求（messages/tools 全字段
deepcopy，不丢 role、工具参数、reasoning 或图像字段），对每对相邻请求断言：

    current["messages"][:len(previous["messages"])] == previous["messages"]
    current.get("tools") == previous.get("tools")

Task 2 后：静态协议（身份/技能/工具协议/JS instructions）在上下文初始化时
安装一次；MEMORY.md、AGENTS.md、工作区观察是带来源的动态快照，跨轮变化
只以追加消息出现在尾部。Task 3 后：pin/push 通知按「未应用变更按顺序追加」
真实进入 history，消费游标由 context.appended 事件承载，LLM 重试
逐字节重发同一批已准备请求。Task 4 后：上下文是 session 级事件溯源投影
（context.prefix_installed/appended/compacted），跨 run、跨重启连续——
全部前缀场景为绿。Task 1 记录的旧版基线（各场景首处分歧位置与完整计数）在
docs/superpowers/reports/2026-09-13-harness-cache-baseline.json。

usage 保真测试（缺字段 / 0 值 / 流式末块）自 Task 1 起为绿。
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.adapters import LegacyLLMProvider, LegacyPromptProvider
from cloudra.runtime_v2.agent_runner import AgentRunner
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies import default_stages
from cloudra.runtime_v2.policies.base import ToolCall, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    Command,
    InvocationProtocol,
    PermissionSet,
)
from cloudra.runtime_v2.turn_pipeline import TurnPipeline
from tests.notice_support import commit_notices

# ---------------------------------------------------------------------------
# 固定场景输入（基线记录的事实源；改动必须同步重生成 baseline JSON）
# ---------------------------------------------------------------------------

FIXTURE_MODEL = "cache-fixture-model"
FIXTURE_BASE_URL = "https://api.example/"
FIXTURE_QUERY = "solve it"
FIXTURE_REMINDER = "[Reminder] check the gaussian log"
FIXTURE_WORKSPACE_FILE = "result.txt"
FIXTURE_MEMORY_TEXT = "# Memory\n\n- Keep the cache prefix stable across turns.\n"
FIXTURE_PIN = "[Task goal] keep the cache prefix stable"
FIXTURE_PUSH = "one-shot: first turn only"
FIXTURE_AGENTS_V1 = "# Project rules\n\n- Rule v1: keep responses terse.\n"
FIXTURE_AGENTS_V2 = "# Project rules\n\n- Rule v2: always cite evidence paths.\n"

_SCENARIO_CADENCE = {
    "two_tool_rounds": "单 run 内 3 次连续 LLM 调用：echo 工具轮、echo 工具轮、stop 收尾",
    "pin_push": "管线级 2 次调用：第 1 轮尾部带 pin+push，第 2 轮 pin 重放、push 已排空",
    "workspace_change": "单 run 2 次调用：第 1 轮工具调用期间写入 result.txt，第 2 轮重渲工作区快照",
    "memory_update": "单 run 2 次调用：第 1 轮工具调用期间写入 MEMORY.md，第 2 轮追加记忆快照",
    "agents_md_update": "单 run 2 次调用：工作区 AGENTS.md 预置 v1，第 1 轮期间改写为 v2",
    "schedule_rewake": "run1 stop  succeeded 后投递 [Reminder] 唤醒 run2；跨 run 各 1 次调用",
    "js_instructions_tail": "管线级 2 次调用（javascript 协议）：JS instructions 初始化时安装一次",
}


# ---------------------------------------------------------------------------
# 捕获线缆请求的 fake client 与流式响应脚本
# ---------------------------------------------------------------------------


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


class _ToolCallDelta:
    """完整（非分片）tool_call delta chunk（model_dump 产出 wire dict 形态）。"""

    def __init__(self, name, arguments, index=0):
        self.index = index
        self.id = f"tc_{index}"
        self.function = SimpleNamespace(name=name, arguments=arguments)

    def model_dump(self, exclude_none=True, **_kwargs):
        return {
            "index": self.index,
            "id": self.id,
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


def _chunk(content=None, reasoning=None, tool_calls=None, finish_reason=None):
    delta = SimpleNamespace(
        content=content, reasoning_content=reasoning, tool_calls=tool_calls
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)]
    )


def _text_reply(text):
    return [_chunk(content=text, finish_reason="stop")]


def _tool_reply(name, arguments, *, reasoning=None):
    chunks = []
    if reasoning:
        chunks.append(_chunk(reasoning=reasoning))
    chunks.append(
        _chunk(
            tool_calls=[_ToolCallDelta(name, json.dumps(arguments, ensure_ascii=False))],
            finish_reason="tool_calls",
        )
    )
    return chunks


class _ScriptedClient:
    """捕获实际发送的线缆请求（全字段 deepcopy），按脚本逐次返回流式响应。

    接口对齐 LLMClient 在 LegacyLLMProvider 路径上被用到的面：
    create_with_retry(**kwargs) / last_usage / aclose()。
    脚本条目可以是 Exception（捕获请求后抛出，模拟瞬时失败）或 ``_HANG``
    （返回永不结束的流，模拟取消窗口）。
    """

    def __init__(self, capture: list[dict], script: list, hooks: dict) -> None:
        self._capture = capture
        self._script = script
        self._hooks = hooks
        # fake 传输不提供 provider 缓存统计：基线里记 unavailable，不记 0。
        self.last_usage: dict = {}

    async def create_with_retry(self, **kwargs):
        call_index = len(self._capture)
        self._capture.append(copy.deepcopy(kwargs))
        hook = self._hooks.get(call_index)
        if hook is not None:
            hook()
        assert self._script, "no scripted LLM response left"
        reply = self._script.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if reply is _HANG:
            return _HangingStream()
        return _FakeStream(reply)

    async def create_responses_with_retry(self, **kwargs):
        raise AssertionError("fixture must stay on the chat transport (native_search=off)")

    async def aclose(self) -> None:
        pass


_HANG = object()


class _HangingStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()
        raise StopAsyncIteration


class _EchoTools:
    async def execute(self, agent, call: ToolCall, **_kwargs) -> ToolResult:
        return ToolResult(is_success=True, summary=f"echo:{call.arguments.get('x')}", data={})


def _freeze_settings(agent) -> None:
    """钉住模型/协议/端点：协议变化属于另一边界，本夹具不比。"""
    agent.settings.model = FIXTURE_MODEL
    agent.settings.base_url = FIXTURE_BASE_URL
    agent.settings.api_key = "sk-cache-fixture"
    agent.settings.native_search = "off"


async def _new_runner_core(script, hooks, *, retry_backoff=(2.0, 4.0)):
    """真实 RuntimeCore + 生产同款 wiring（LegacyPromptProvider/LegacyLLMProvider）。"""
    capture: list[dict] = []
    core = RuntimeCore(strict_events=True)
    provider = LegacyLLMProvider(
        client_factory=lambda settings: _ScriptedClient(capture, script, hooks)
    )
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=provider,
        tools=_EchoTools(),
        prompt_provider=LegacyPromptProvider(),
        notices=core.notices,
    )
    core.runner = AgentRunner(
        core, pipeline, retry_backoff=retry_backoff
    )
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "cache fixture"}))
    project = next(iter(core.projects.values()))
    return core, bus, project, capture


async def _spawn_agent(core, bus, project, *, query=FIXTURE_QUERY):
    payload = {"role_id": "coordinator"}
    if query is not None:
        payload["query"] = query
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload=payload,
        )
    )
    agent = result.data
    # ScriptedLLM 直接发业务工具调用，固定传统协议；默认 javascript 协议
    # 只放 js_exec + 直接控制类（JS 尾部追加由管线级场景单独覆盖）。
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    _freeze_settings(agent)
    return agent


async def _wait_state(agent, state: str, timeout: float = 10.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


async def _wait_background_drained(runner, session_id: str, timeout: float = 10.0):
    """等 run 收尾 finalize（写 context tree）完成，保证跨 run seed 确定。"""
    deadline = asyncio.get_running_loop().time() + timeout
    while runner._background.get(session_id):
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("finalize background task did not drain")
        await asyncio.sleep(0.01)


def _pipeline_agent(protocol, *, agent_id: str) -> AgentSession:
    agent = AgentSession(
        id=agent_id,
        project_id="prj_cache_pipe",
        role_id="coordinator",
        display_name="cache-fixture",
    )
    agent.settings.invocation_protocol = protocol
    _freeze_settings(agent)
    return agent


def _pipeline(script, *, notices=None):
    capture: list[dict] = []
    pipeline = TurnPipeline(
        event_log=EventLog(strict=True),
        stages=[],
        llm=LegacyLLMProvider(
            client_factory=lambda settings: _ScriptedClient(capture, script, {})
        ),
        tools=_EchoTools(),
        notices=notices,
    )
    return pipeline, capture


def _begin_prefix(agent) -> object:
    """管线级场景显式持有 per-run 上下文前缀 owner（runner 在生产中持有）。"""
    return LegacyPromptProvider().begin_context(
        agent=agent, workspace_dir=None, tool_names=["echo", "stop"]
    )


_PIPE_CAPS = AgentCapabilities(permissions=PermissionSet(), tools=["echo", "stop"])


# ---------------------------------------------------------------------------
# 前缀断言
# ---------------------------------------------------------------------------


def _first_divergence(previous: dict, current: dict) -> int | None:
    """current 以 previous 的 messages 为完整前缀时返回 None，否则返回首个分歧下标。"""
    prev_messages = previous["messages"]
    cur_messages = current["messages"]
    common = min(len(prev_messages), len(cur_messages))
    for index in range(common):
        if prev_messages[index] != cur_messages[index]:
            return index
    if len(prev_messages) > len(cur_messages):
        return common
    return None


def _role_at(request: dict, index: int) -> str:
    messages = request["messages"]
    if index >= len(messages):
        return "<end>"
    return str(messages[index].get("role"))


def _assert_prefix_continuity(capture: list[dict], *, scenario: str) -> None:
    for index in range(1, len(capture)):
        previous, current = capture[index - 1], capture[index]
        assert current.get("tools") == previous.get("tools"), (
            f"[{scenario}] request {index - 1}->{index}: tools protocol changed"
        )
        divergence = _first_divergence(previous, current)
        assert divergence is None, (
            f"[{scenario}] request {index - 1}->{index}: prefix rewritten at "
            f"message index {divergence} "
            f"(previous role={_role_at(previous, divergence)}, "
            f"current role={_role_at(current, divergence)}); "
            f"previous messages={len(previous['messages'])}, "
            f"current messages={len(current['messages'])}"
        )


# ---------------------------------------------------------------------------
# 场景实现（测试与基线生成共用同一入口）
# ---------------------------------------------------------------------------


async def _scenario_two_tool_rounds() -> list[dict]:
    script = [
        _tool_reply("echo", {"x": 1}),
        _tool_reply("echo", {"x": 2}),
        _text_reply("done"),
    ]
    core, bus, project, capture = await _new_runner_core(script, {})
    agent = await _spawn_agent(core, bus, project)
    await _wait_state(agent, "succeeded")
    assert len(capture) == 3
    return capture


async def _scenario_pin_push() -> list[dict]:
    script = [
        _tool_reply("echo", {"x": 1}, reasoning="need the echo first"),
        _text_reply("done"),
    ]
    notices = NoticeManager()
    pipeline, capture = _pipeline(script, notices=notices)
    agent = _pipeline_agent(InvocationProtocol.TRADITIONAL, agent_id="as_cache_pin")
    prefix = _begin_prefix(agent)
    notices.pin(agent.id, "goal", FIXTURE_PIN)
    notices.push(agent.id, FIXTURE_PUSH)
    await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=_PIPE_CAPS,
        inbox_messages=[{"content": "hi"}],
        history=[],
        notices=notices,
        context_prefix=prefix,
    )
    # 与 AgentRunner 相同：install/refresh 产出的消息持久化进 history
    # （drain 恰好一次），通知批次在写进 history 后 confirm（推进消费游标）。
    # history 条目为内部形态（arguments 结构化 dict、reasoning_content
    # 保留），adapter 负责转线缆格式。
    install, appends = prefix.drain_pending()
    notice_messages = commit_notices(notices, agent.id)
    assert [m["content"] for m in notice_messages] == [FIXTURE_PIN, FIXTURE_PUSH]
    history = [
        *install,
        *appends,
        {"role": "user", "content": "hi"},
        *notice_messages,
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "need the echo first",
            "tool_calls": [{"id": "tc_0", "name": "echo", "arguments": {"x": 1}}],
        },
        {"role": "tool", "tool_call_id": "tc_0", "content": "echo:1"},
    ]
    await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=_PIPE_CAPS,
        inbox_messages=[],
        history=history,
        notices=notices,
        context_prefix=prefix,
    )
    assert len(capture) == 2
    return capture


async def _scenario_workspace_change() -> list[dict]:
    hooks = {}
    script = [_tool_reply("echo", {"x": 1}), _text_reply("done")]
    core, bus, project, capture = await _new_runner_core(script, hooks)
    workspace = Path(project.workspace_dir)

    def write_result():
        (workspace / FIXTURE_WORKSPACE_FILE).write_text(
            "intermediate result\n", encoding="utf-8"
        )

    hooks[0] = write_result
    agent = await _spawn_agent(core, bus, project)
    await _wait_state(agent, "succeeded")
    assert len(capture) == 2
    return capture


async def _scenario_memory_update() -> list[dict]:
    from cloudra.infra.config import get_config
    from cloudra.persistence.paths import memory_path

    hooks = {}
    script = [_tool_reply("echo", {"x": 1}), _text_reply("done")]
    core, bus, project, capture = await _new_runner_core(script, hooks)

    def write_memory():
        path = memory_path(data_dir=get_config().data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(FIXTURE_MEMORY_TEXT, encoding="utf-8")

    hooks[0] = write_memory
    agent = await _spawn_agent(core, bus, project)
    await _wait_state(agent, "succeeded")
    assert len(capture) == 2
    return capture


async def _scenario_agents_md_update() -> list[dict]:
    hooks = {}
    script = [_tool_reply("echo", {"x": 1}), _text_reply("done")]
    core, bus, project, capture = await _new_runner_core(script, hooks)
    workspace = Path(project.workspace_dir)
    (workspace / "AGENTS.md").write_text(FIXTURE_AGENTS_V1, encoding="utf-8")

    def rewrite_agents_md():
        (workspace / "AGENTS.md").write_text(FIXTURE_AGENTS_V2, encoding="utf-8")

    hooks[0] = rewrite_agents_md
    agent = await _spawn_agent(core, bus, project)
    await _wait_state(agent, "succeeded")
    assert len(capture) == 2
    return capture


async def _scenario_schedule_rewake() -> list[dict]:
    script = [_text_reply("first done"), _text_reply("reminder done")]
    core, bus, project, capture = await _new_runner_core(script, {})
    agent = await _spawn_agent(core, bus, project)
    await _wait_state(agent, "succeeded")
    await _wait_background_drained(core.runner, agent.id)

    # Task 5 起 schedule stop 不再触发 compact，无需桩摘要器。
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": FIXTURE_REMINDER},
        )
    )
    await _wait_state(agent, "succeeded")
    assert len(capture) == 2
    return capture


async def _scenario_js_instructions_tail() -> list[dict]:
    script = [_text_reply("first"), _text_reply("second")]
    pipeline, capture = _pipeline(script)
    agent = _pipeline_agent(InvocationProtocol.JAVASCRIPT, agent_id="as_cache_js")
    prefix = _begin_prefix(agent)
    await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=_PIPE_CAPS,
        inbox_messages=[{"content": "hi"}],
        history=[],
        context_prefix=prefix,
    )
    install, appends = prefix.drain_pending()
    history = [
        *install,
        *appends,
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "first"},
    ]
    await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=agent.settings,
        capabilities=_PIPE_CAPS,
        inbox_messages=[],
        history=history,
        context_prefix=prefix,
    )
    assert len(capture) == 2
    return capture


# ---------------------------------------------------------------------------
# 前缀连续性回归（Task 2 后：仅 notices 重放/排空与跨 run 重建保持测红，
# 分别由 Task 3 / Task 4 转绿）
# ---------------------------------------------------------------------------


def _serialized(kwargs: dict) -> str:
    return json.dumps(kwargs["messages"], ensure_ascii=False, default=str)


@pytest.mark.asyncio
async def test_prefix_continuity_two_tool_rounds():
    capture = await _scenario_two_tool_rounds()
    _assert_prefix_continuity(capture, scenario="two_tool_rounds")


@pytest.mark.asyncio
async def test_prefix_continuity_pin_push():
    capture = await _scenario_pin_push()
    _assert_prefix_continuity(capture, scenario="pin_push")


@pytest.mark.asyncio
async def test_prefix_continuity_workspace_change():
    capture = await _scenario_workspace_change()
    _assert_prefix_continuity(capture, scenario="workspace_change")
    # 旧消息逐字节保持；新的工作区观察只出现在尾部，且描述当前观察状态。
    assert "result.txt" not in _serialized(capture[0])
    tail = capture[1]["messages"][-1]
    assert tail["role"] == "system"
    assert tail["content"].startswith("[Workspace observation — update]")
    assert "result.txt" in tail["content"]


@pytest.mark.asyncio
async def test_prefix_continuity_memory_update():
    capture = await _scenario_memory_update()
    _assert_prefix_continuity(capture, scenario="memory_update")
    # 记忆快照不并入 identity（前缀首条消息不含记忆文本），只追加在尾部。
    assert "Keep the cache prefix stable" not in capture[0]["messages"][0]["content"]
    tail = capture[1]["messages"][-1]
    assert tail["content"].startswith("[Long-term memory — snapshot of MEMORY.md]")
    assert "Keep the cache prefix stable" in tail["content"]


@pytest.mark.asyncio
async def test_prefix_continuity_agents_md_update():
    capture = await _scenario_agents_md_update()
    _assert_prefix_continuity(capture, scenario="agents_md_update")
    # AGENTS.md v1 快照保持原位逐字节不变；v2 只以替代关系消息出现在尾部，
    # 用户指令权威不被冻结前缀吞掉。
    first = capture[0]["messages"]
    v1_positions = [
        index for index, message in enumerate(first) if "Rule v1" in str(message.get("content"))
    ]
    assert len(v1_positions) == 1
    assert capture[1]["messages"][v1_positions[0]] == first[v1_positions[0]]
    assert "Rule v2" not in _serialized(capture[0])
    # AGENTS.md 改写同时改变工作区观察，尾部还可能有一条 workspace 更新；
    # 按标签定位 agents_md 更新消息，不断言它是最后一条。
    agents_updates = [
        message
        for message in capture[1]["messages"]
        if str(message.get("content") or "").startswith(
            "[Updated user instructions — AGENTS.md changed]"
        )
    ]
    assert len(agents_updates) == 1
    assert "Rule v2" in agents_updates[0]["content"]
    assert "Rule v1" not in agents_updates[0]["content"]
    assert capture[1]["messages"].index(agents_updates[0]) > v1_positions[0]


@pytest.mark.asyncio
async def test_prefix_continuity_schedule_rewake():
    capture = await _scenario_schedule_rewake()
    _assert_prefix_continuity(capture, scenario="schedule_rewake")


@pytest.mark.asyncio
async def test_prefix_continuity_js_instructions_tail():
    capture = await _scenario_js_instructions_tail()
    _assert_prefix_continuity(capture, scenario="js_instructions_tail")
    for kwargs in capture:
        js_messages = [
            message
            for message in kwargs["messages"]
            if "JavaScript invocation protocol" in str(message.get("content"))
        ]
        # JS instructions 恰好一条，且固定在前缀位置（不再是请求尾部追加）。
        assert len(js_messages) == 1
        assert kwargs["messages"].index(js_messages[0]) == 1


@pytest.mark.asyncio
async def test_static_prefix_and_js_instructions_stable_three_turns():
    """静态提示与 JS instructions 连续三轮逐字节一致；install 恰好一次。"""
    script = [_text_reply("one"), _text_reply("two"), _text_reply("three")]
    pipeline, capture = _pipeline(script)
    agent = _pipeline_agent(InvocationProtocol.JAVASCRIPT, agent_id="as_cache_js3")
    prefix = _begin_prefix(agent)
    history: list[dict] = []
    for index, text in enumerate(("one", "two", "three")):
        await pipeline.run_turn(
            agent=agent,
            run_id="run1",
            settings=agent.settings,
            capabilities=_PIPE_CAPS,
            inbox_messages=[{"content": f"question {index}"}],
            history=history,
            context_prefix=prefix,
        )
        install, appends = prefix.drain_pending()
        if index == 0:
            assert install, "first turn must install the static prefix"
        else:
            assert not install, "static prefix must be installed exactly once"
        assert not appends, "no dynamic source changed; refresh must stay silent"
        history = [
            *install,
            *history,
            {"role": "user", "content": f"question {index}"},
            {"role": "assistant", "content": text},
        ]
    assert len(capture) == 3
    _assert_prefix_continuity(capture, scenario="js_three_turns")
    # 身份与 JS instructions 两条静态消息在三轮请求中逐字节一致。
    for kwargs in capture[1:]:
        assert kwargs["messages"][:2] == capture[0]["messages"][:2]
    assert "JavaScript invocation protocol" in str(capture[0]["messages"][1].get("content"))


@pytest.mark.asyncio
async def test_retry_reuses_identical_prepared_request():
    """LLM 瞬时失败后的重试逐字节重发同一请求：准备好的批次固定——
    前缀不重渲出不同内容、通知不重新 drain（无 status_code 的
    RuntimeError 属可重试错误，走 runner 的 in-place retry）。"""
    script = [RuntimeError("simulated transient network failure"), _text_reply("done")]
    core, bus, project, capture = await _new_runner_core(
        script, {}, retry_backoff=(0.01,)
    )
    # spawn 不带 query（queued）：先把通知就位再发消息开跑，消除竞态。
    # pin 用 "review" 键：GoalStage 在每轮 before_llm 对 "goal" 键有
    # 读不到文件即 unpin 的正常语义，不能占用它。
    agent = await _spawn_agent(core, bus, project, query=None)
    core.notices.pin(agent.id, "review", FIXTURE_PIN)
    core.notices.push(agent.id, FIXTURE_PUSH)
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "start"},
        )
    )
    await _wait_state(agent, "succeeded")
    assert len(capture) == 2
    assert capture[0] == capture[1]
    assert capture[0]["messages"][-2]["content"] == FIXTURE_PIN
    assert capture[0]["messages"][-1]["content"] == FIXTURE_PUSH
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "run.retry" in types
    # 重试复用已提交输入，消费游标与正文只落一次。
    consumed = [
        event for event in core.event_log.query_session(agent.id)
        if event.type == "context.appended" and "notices_through" in event.data
    ]
    assert len(consumed) == 1
    assert [m["content"] for m in consumed[0].data["messages"]][-2:] == [
        FIXTURE_PIN, FIXTURE_PUSH
    ]


@pytest.mark.asyncio
async def test_cancel_never_confirms_notice_consumption():
    """run_turn 在 LLM 流期间被取消：通知批次保持 pending 不确认，
    下次 collect 原样重发（取消不提前确认消费，不丢消息）。"""
    notices = NoticeManager()
    pipeline, capture = _pipeline([_HANG])
    agent = _pipeline_agent(InvocationProtocol.TRADITIONAL, agent_id="as_cache_cancel")
    prefix = _begin_prefix(agent)
    notices.push(agent.id, FIXTURE_PUSH)
    task = asyncio.create_task(
        pipeline.run_turn(
            agent=agent,
            run_id="run1",
            settings=agent.settings,
            capabilities=_PIPE_CAPS,
            inbox_messages=[{"content": "hi"}],
            history=[],
            notices=notices,
            context_prefix=prefix,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # 请求确实发出且尾部带着这条 push。
    assert len(capture) == 1
    assert capture[0]["messages"][-1]["content"] == FIXTURE_PUSH
    # 未 confirm：同一批原样保留；confirm 后才推进游标、不再重发。
    assert [m["content"] for m in notices.collect_batch(agent.id, fresh=False)] == [
        FIXTURE_PUSH
    ]
    confirmed = commit_notices(notices, agent.id)
    assert [m["content"] for m in confirmed] == [FIXTURE_PUSH]
    assert notices.collect_batch(agent.id, fresh=False) == []


# ---------------------------------------------------------------------------
# 缓存 usage 保真（Task 1 修复后为绿）
# ---------------------------------------------------------------------------


def test_responses_usage_preserves_cache_details():
    from cloudra.infra.llm_client import _translate_responses_usage

    usage = _translate_responses_usage(
        {
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 50,
                "total_tokens": 1050,
                "input_tokens_details": {"cached_tokens": 896},
                "output_tokens_details": {"reasoning_tokens": 20},
            }
        }
    )
    assert usage["prompt_tokens"] == 1000
    assert usage["completion_tokens"] == 50
    assert usage["total_tokens"] == 1050
    assert usage["prompt_tokens_details"]["cached_tokens"] == 896
    assert usage["completion_tokens_details"]["reasoning_tokens"] == 20


def test_responses_usage_missing_cache_details_stays_absent():
    """缺失不补 0：「provider 未报告」绝不能与「报告为 0」混淆。"""
    from cloudra.infra.llm_client import _translate_responses_usage

    usage = _translate_responses_usage(
        {"usage": {"input_tokens": 10, "output_tokens": 5}}
    )
    assert usage["prompt_tokens"] == 10
    assert usage["total_tokens"] == 15
    assert "prompt_tokens_details" not in usage
    assert "completion_tokens_details" not in usage


def test_responses_usage_zero_cached_tokens_preserved():
    from cloudra.infra.llm_client import _translate_responses_usage

    usage = _translate_responses_usage(
        {
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "input_tokens_details": {"cached_tokens": 0},
            }
        }
    )
    assert usage["prompt_tokens_details"]["cached_tokens"] == 0


def _sse_response(payload: str):
    class _SSEResponse:
        def iter_content(self, chunk_size=1024):
            yield payload.encode("utf-8")

    return _SSEResponse()


def test_responses_stream_final_chunk_preserves_cache_details():
    """流式末块 response.completed 的 usage 走同一翻译路径，缓存细项不丢。"""
    from cloudra.infra.llm_client import _responses_stream_events

    payload = (
        'data: {"type": "response.output_text.delta", "delta": "hi"}\n\n'
        'data: {"type": "response.completed", "response": {"id": "resp_1", '
        '"status": "completed", "output": [{"type": "message", "content": '
        '[{"type": "output_text", "text": "hi"}]}], "usage": {"input_tokens": 120, '
        '"output_tokens": 7, "input_tokens_details": {"cached_tokens": 96}, '
        '"output_tokens_details": {"reasoning_tokens": 0}}}}\n\n'
    )
    holder = SimpleNamespace(web_search_log=[], usage=None)
    chunks = list(_responses_stream_events(_sse_response(payload), holder))
    assert chunks[-1]["completion"]["choices"][0]["finish_reason"] == "stop"
    assert holder.usage["prompt_tokens"] == 120
    assert holder.usage["prompt_tokens_details"]["cached_tokens"] == 96
    assert holder.usage["completion_tokens_details"]["reasoning_tokens"] == 0


def test_responses_stream_final_chunk_missing_details_stays_absent():
    from cloudra.infra.llm_client import _responses_stream_events

    payload = (
        'data: {"type": "response.completed", "response": {"id": "resp_2", '
        '"status": "completed", "output": [], "usage": {"input_tokens": 12, '
        '"output_tokens": 3}}}\n\n'
    )
    holder = SimpleNamespace(web_search_log=[], usage=None)
    list(_responses_stream_events(_sse_response(payload), holder))
    assert holder.usage["prompt_tokens"] == 12
    assert "prompt_tokens_details" not in holder.usage


# ---------------------------------------------------------------------------
# 请求指纹诊断（只含哈希/计数，不含原文）
# ---------------------------------------------------------------------------


def test_request_fingerprint_contains_no_content():
    from cloudra.infra.llm_client import request_fingerprint

    kwargs = {
        "messages": [{"role": "user", "content": "secret content"}],
        "tools": [{"type": "function", "function": {"name": "stop"}}],
    }
    fingerprint = request_fingerprint(kwargs)
    assert fingerprint["message_count"] == 1
    assert len(fingerprint["message_hashes"]) == 1
    serialized = json.dumps(fingerprint)
    assert "secret content" not in serialized
    assert "stop" not in serialized


def test_first_prefix_divergence():
    from cloudra.infra.llm_client import first_prefix_divergence

    assert first_prefix_divergence(["a"], ["a", "b"]) is None
    assert first_prefix_divergence(["a", "b"], ["a", "b"]) is None
    assert first_prefix_divergence(["a", "b"], ["a", "x"]) == 1
    assert first_prefix_divergence(["a", "b"], ["a"]) == 1
    assert first_prefix_divergence(["a", "b"], ["x", "b"]) == 0


# ---------------------------------------------------------------------------
# 旧版基线生成（非 pytest 入口；由维护脚本在隔离 data_dir 下调用）
# ---------------------------------------------------------------------------


def _summarize_capture(capture: list[dict]) -> dict:
    requests = []
    for kwargs in capture:
        messages = kwargs.get("messages") or []
        requests.append(
            {
                "messages": len(messages),
                "message_chars": sum(
                    len(json.dumps(message, ensure_ascii=False, default=str))
                    for message in messages
                ),
                "tools": len(kwargs.get("tools") or []),
            }
        )
    pairs = []
    for index in range(1, len(capture)):
        previous, current = capture[index - 1], capture[index]
        divergence = _first_divergence(previous, current)
        pairs.append(
            {
                "pair": [index - 1, index],
                "tools_equal": current.get("tools") == previous.get("tools"),
                "first_divergence": divergence,
                "prefix_holds": divergence is None,
            }
        )
    return {"requests": requests, "pairs": pairs}


async def collect_cache_baseline() -> dict:
    """在当前实现上运行全部场景，返回机器可读的旧版基线。

    注意：memory_update 写全局 MEMORY.md，必须最后运行（同一进程内
    data_dir 共享）；pytest 下由 conftest 逐测试隔离，顺序无关。
    """
    scenarios = {}
    for name, scenario in (
        ("two_tool_rounds", _scenario_two_tool_rounds),
        ("pin_push", _scenario_pin_push),
        ("workspace_change", _scenario_workspace_change),
        ("agents_md_update", _scenario_agents_md_update),
        ("schedule_rewake", _scenario_schedule_rewake),
        ("js_instructions_tail", _scenario_js_instructions_tail),
        ("memory_update", _scenario_memory_update),
    ):
        capture = await scenario()
        entry = _summarize_capture(capture)
        entry["cadence"] = _SCENARIO_CADENCE[name]
        scenarios[name] = entry
    return {
        "recorded_at": "2026-09-13",
        "implementation": "current code before Tasks 2-4 (harness rewrites prefixes)",
        "model": FIXTURE_MODEL,
        "base_url": FIXTURE_BASE_URL,
        "protocol": {
            "runner_scenarios": "traditional",
            "js_instructions_tail": "javascript",
        },
        "transport": "chat.completions streaming（fake client 捕获实际发送的 kwargs）",
        "usage_fields": "unavailable: fake 传输不上报 provider 缓存统计（按验收 8 记 unavailable，不记 0）",
        "fixed_inputs": {
            "query": FIXTURE_QUERY,
            "reminder": FIXTURE_REMINDER,
            "workspace_file": FIXTURE_WORKSPACE_FILE,
            "memory_text": FIXTURE_MEMORY_TEXT,
            "pin": FIXTURE_PIN,
            "push": FIXTURE_PUSH,
            "agents_md_v1": FIXTURE_AGENTS_V1,
            "agents_md_v2": FIXTURE_AGENTS_V2,
        },
        "notes": "message_chars 含临时工作区绝对路径，逐环境变化；messages/tools 计数与 first_divergence 是稳定部分。",
        "scenarios": scenarios,
    }
