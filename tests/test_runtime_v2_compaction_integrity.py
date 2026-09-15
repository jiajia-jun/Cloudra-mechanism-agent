"""Compact 完整性（Task 5，计划 2026-09-13-harness-cache-continuity）：

统一全轮次压缩、逐字用户原文（指令区）、结构化摘要校验、按容量分段、
拒替换条件与版本守卫。fake summarizer 证明输入覆盖与原文保留；
字段齐全不等于语义完整——语义质量由人工/真实模型另行检查。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from cloudra.runtime_v2.compaction import (
    COMPACT_SUMMARY_CONTRACT,
    CompactSummaryError,
    compact_context,
    context_over_budget,
    parse_compact_summary,
    render_compact_summary,
    segment_trajectory,
    usable_prompt_chars,
)


def _summary_payload(**overrides) -> dict:
    payload = {
        "objective": {"text": "solve the mechanism task", "sources": []},
        "active_requests": [{"text": "deliver the barrier", "sources": []}],
        "corrections": [],
        "constraints": [],
        "pending": [],
        "completed": [],
        "failed_attempts": [],
        "evidence": [],
        "next_actions": [],
    }
    payload.update(overrides)
    return payload


def _summary_json(**overrides) -> str:
    return json.dumps(_summary_payload(**overrides), ensure_ascii=False)


class RecordingSummarizer:
    """记录每次摘要调用的输入；可脚本化每次的返回/异常。

    兼容两种调用形态：compact_context 直调 ``summarize(messages)`` 与
    runner 默认链路的 ``summarize_with_agent_settings(agent, messages)``。
    """

    def __init__(self, responses: list | None = None) -> None:
        self.calls: list[list[dict]] = []
        self._responses = list(responses) if responses is not None else None

    async def __call__(self, *args, **_kwargs):
        messages = args[-1]
        self.calls.append(list(messages))
        if self._responses is not None:
            reply = self._responses.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return _summary_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_recent, expected_tail", [(0, 0), (1, 3), (2, 3), (3, 3)])
async def test_single_user_run_compacts_completed_tools_with_paired_recent_tail(
    keep_recent, expected_tail
):
    instruction = {"role": "user", "content": "finish the entire task", "message_id": "u1"}
    messages = [instruction]
    for index in range(12):
        messages.extend([
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": f"a{index}", "name": "bash", "arguments": {}},
                {"id": f"b{index}", "name": "bash", "arguments": {}},
            ]},
            {"role": "tool", "tool_call_id": f"a{index}", "content": "old log " * 500},
            {"role": "tool", "tool_call_id": f"b{index}", "content": "other log " * 500},
        ])
    summarizer = RecordingSummarizer()
    result, stats = await compact_context(
        messages, head=[], notices=[], keep_recent=keep_recent,
        summarize=summarizer, context_window=200_000, max_output=32_768,
    )
    assert stats["compacted"] is True
    assert result[0] == instruction
    assert stats["tail_messages"] == expected_tail
    assert len(result) == 2 + expected_tail
    if expected_tail:
        assert result[-expected_tail:] == messages[-expected_tail:]
    assert "old log " * 500 in summarizer.calls[0][-1]["content"]


def _context_window_for(budget_chars: int) -> tuple[int, int]:
    """反推一个可用容量约为 budget_chars 的 (context_window, max_output)。"""
    window = int(budget_chars / 4 / 0.85) + 100
    return window, 0


def _trajectory_context() -> list[dict]:
    """三轮用户目标与纠正 + 两轮 reminder + 大轨迹 + 末尾关键约束。"""
    big_tool_output = "log line\n" * 2000  # >12,000 字符的执行轨迹
    big_constraint = "关键约束：" + "不得静默丢弃任何开放事项。" * 300  # >4,000 字符用户消息
    return [
        {"role": "user", "content": "compute the aldol barrier", "message_id": "msg-u1"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "name": "bash", "arguments": {"cmd": "run"}}]},
        {"role": "tool", "tool_call_id": "t1", "content": big_tool_output},
        {"role": "assistant", "content": "first pass done"},
        {"role": "user", "content": "correction: use xtb, not gaussian", "message_id": "msg-u2"},
        {"role": "assistant", "content": "switched to xtb"},
        {"role": "user", "content": "[Reminder] poll the job", "message_id": "msg-r1"},
        {"role": "assistant", "content": "still running"},
        {"role": "user", "content": "[Reminder] poll the job again", "message_id": "msg-r2"},
        {"role": "assistant", "content": "still running"},
        {"role": "user", "content": "second correction: report barriers in kcal/mol", "message_id": "msg-u3"},
        {"role": "assistant", "content": "will report in kcal/mol"},
        {"role": "user", "content": big_constraint, "message_id": "msg-u4"},
        # 最近工具调用按 keep_recent 保留，调用与响应不可拆散
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t2", "name": "bash", "arguments": {"cmd": "tail"}}]},
        {"role": "tool", "tool_call_id": "t2", "content": "job done, barrier 5.0"},
    ]


@pytest.mark.asyncio
async def test_all_rounds_enter_summary_input_and_instructions_stay_verbatim():
    """三轮目标与纠正、两轮 reminder、>12,000 字符轨迹、末尾关键约束全部
    进入摘要输入；用户消息（>4,000 字符）逐字保留在指令区且按 message_id
    保身份；活动工具尾部原样完整。"""
    messages = _trajectory_context()
    summarizer = RecordingSummarizer()
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        keep_recent=2,
        summarize=summarizer,
        context_window=200_000,
        max_output=32_768,
    )
    assert stats["compacted"] is True
    assert summarizer.calls, "summarizer never called"
    summary_input = "\n".join(
        str(m.get("content")) for call in summarizer.calls for m in call
    )
    # 轨迹逐字进输入：无截断（旧 _serialize 的 2,000/12,000 上限已删除）
    assert "log line\n" * 2000 in summary_input
    # 末尾关键约束（>4,000 字符的用户消息）完整进入摘要输入
    assert "关键约束：" + "不得静默丢弃任何开放事项。" * 300 in summary_input
    # 指令区：四条用户消息逐字、按 message_id 保身份
    instructions = [m for m in new_context if m.get("role") == "user"]
    assert [m.get("message_id") for m in instructions] == [
        "msg-u1",
        "msg-u2",
        "msg-r1",
        "msg-r2",
        "msg-u3",
        "msg-u4",
    ]
    for original in messages:
        if original.get("role") == "user":
            assert original in instructions
    # 活动尾部完整保留在最后
    assert new_context[-2]["tool_calls"] == [{"id": "t2", "name": "bash", "arguments": {"cmd": "tail"}}]
    assert new_context[-1] == {"role": "tool", "tool_call_id": "t2", "content": "job done, barrier 5.0"}
    # 摘要消息是 assistant 的 [Context compact] handoff
    handoff = new_context[len(instructions)]
    assert handoff["role"] == "assistant"
    assert handoff["content"].startswith("[Context compact]")
    assert "solve the mechanism task" in handoff["content"]
    assert stats["instruction_messages"] == 6
    assert stats["tail_messages"] == 2


@pytest.mark.asyncio
async def test_single_overlong_message_fully_covered_by_segmentation():
    """单条超长消息跨段切块：每段不超预算、全文无丢失、覆盖记录完整，
    多段成功后还有一次汇总调用。"""
    long_line = "x" * 100 + "\n"
    big = long_line * 300  # ~30,000 字符的单条消息
    messages = [
        {"role": "assistant", "content": "first pass"},
        {"role": "tool", "tool_call_id": "t1", "content": big},
        {"role": "assistant", "content": "working"},
        {"role": "user", "content": "next step"},
        {"role": "assistant", "content": "on it"},
    ]
    window, output = _context_window_for(8_000)
    budget = usable_prompt_chars(window, output)
    summarizer = RecordingSummarizer()
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        keep_recent=0,
        summarize=summarizer,
        context_window=window,
        max_output=output,
    )
    assert stats["compacted"] is True
    # keep_recent=0 时，包括最后一条 assistant 在内的全部轨迹进入摘要
    covered = sorted(
        index for seg in stats["segments"] for index in seg["message_indexes"]
    )
    assert set(covered) == {0, 1, 2, 3, 4}
    segment_calls = summarizer.calls[: len(stats["segments"])]
    # 多段 → 段数 + 一次 merge 调用
    assert len(stats["segments"]) >= 2
    assert len(summarizer.calls) == len(stats["segments"]) + 1
    # 每段不超预算（续接标记开销留出 200 字符）
    for seg, call in zip(stats["segments"], segment_calls):
        assert seg["chars"] <= budget + 200
        assert len(str(call[-1]["content"])) == seg["chars"]
    # 全文无丢失：段拼接包含原消息首尾与几乎所有行（切块边界至多断行）
    joined = "\n".join(str(call[-1]["content"]) for call in segment_calls)
    assert big[:500] in joined and big[-500:] in joined
    assert joined.count("x" * 100) >= 290


@pytest.mark.asyncio
async def test_user_message_over_4000_chars_never_truncated():
    big = "要求：" + "保留全部上下文。" * 600  # >4,000 字符
    messages = [
        {"role": "user", "content": big, "message_id": "msg-big"},
        {"role": "assistant", "content": "working"},
    ]
    summarizer = RecordingSummarizer()
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        keep_recent=0,
        summarize=summarizer,
        context_window=200_000,
        max_output=32_768,
    )
    assert stats["compacted"] is True
    instructions = [m for m in new_context if m.get("role") == "user"]
    assert instructions[0]["content"] == big  # 逐字，无截断标记
    assert instructions[0]["message_id"] == "msg-big"
    assert big in "\n".join(
        str(m.get("content")) for call in summarizer.calls for m in call
    )


# ---------------------------------------------------------------------------
# 拒替换条件：一律保留原上下文
# ---------------------------------------------------------------------------


async def _refusal(messages, summarizer, **kwargs):
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        keep_recent=0,
        summarize=summarizer,
        context_window=kwargs.pop("context_window", 200_000),
        max_output=kwargs.pop("max_output", 32_768),
    )
    assert stats["compacted"] is False
    assert new_context is messages  # 原上下文原样返回
    return stats


@pytest.mark.asyncio
async def test_empty_summary_output_refused():
    messages = _trajectory_context()
    stats = await _refusal(messages, RecordingSummarizer([""]))
    assert stats["reason"] == "summary_invalid"
    assert "empty" in stats["error"]


@pytest.mark.asyncio
async def test_structural_validation_error_refused():
    messages = _trajectory_context()
    stats = await _refusal(messages, RecordingSummarizer(["not json at all"]))
    assert stats["reason"] == "summary_invalid"
    stats = await _refusal(
        messages, RecordingSummarizer([json.dumps({"objective": {"text": "", "sources": []}})])
    )
    assert stats["reason"] == "summary_invalid"


@pytest.mark.asyncio
async def test_source_index_out_of_range_refused():
    messages = _trajectory_context()
    bad = _summary_json(
        objective={"text": "o", "sources": [9999]}
    )
    stats = await _refusal(messages, RecordingSummarizer([bad]))
    assert stats["reason"] == "summary_invalid"
    assert "out of trajectory range" in stats["error"]


@pytest.mark.asyncio
async def test_segment_failure_refused_and_reports_segment():
    window, output = _context_window_for(4_000)
    messages = _trajectory_context()  # 多段
    summarizer = RecordingSummarizer([_summary_json(), RuntimeError("segment boom")])
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        keep_recent=0,
        summarize=summarizer,
        context_window=window,
        max_output=output,
    )
    assert stats["compacted"] is False
    assert stats["reason"] == "segment_failed"
    assert stats["failed_segment"] == 1
    assert new_context is messages


@pytest.mark.asyncio
async def test_merge_failure_refused():
    window, output = _context_window_for(4_000)
    messages = _trajectory_context()
    calls = []

    async def summarizer(*args, **_kwargs):
        segment_messages = args[-1]
        calls.append(segment_messages)
        if str(segment_messages[0].get("content") or "").startswith("You are merging"):
            return "garbage-merge"
        return _summary_json()

    _new, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        keep_recent=0,
        summarize=summarizer,
        context_window=window,
        max_output=output,
    )
    assert len(calls) >= 3, "multi-segment input plus a merge call expected"
    assert stats["compacted"] is False
    assert stats["reason"] == "summary_invalid"


@pytest.mark.asyncio
async def test_summary_not_shorter_refused():
    messages = [
        {"role": "user", "content": "g"},
        {"role": "assistant", "content": "a"},
    ]
    huge = _summary_json(objective={"text": "o" + "x" * 5000, "sources": []})
    stats = await _refusal(messages, RecordingSummarizer([huge]))
    assert stats["reason"] == "summary_not_shorter"


@pytest.mark.asyncio
async def test_verbatim_instructions_exceeding_capacity_reported():
    """逐字用户原文单独超过可用容量：明确报告无法无损压缩，禁止静默裁剪。"""
    big = "y" * 5000  # 指令区单独超预算（预算下限 4096 字符）
    messages = [
        {"role": "user", "content": big},
        {"role": "assistant", "content": "a" * 5000},
    ]
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        keep_recent=0,
        summarize=RecordingSummarizer(),
        context_window=1_000,
        max_output=0,
    )
    assert stats["compacted"] is False
    assert stats["reason"] == "verbatim_instructions_exceed_budget"
    assert new_context is messages


@pytest.mark.asyncio
async def test_cancellation_propagates_without_replacing():
    messages = _trajectory_context()

    async def cancelling(messages, **_kwargs):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await compact_context(
            messages,
            head=[],
            notices=[],
            keep_recent=0,
            summarize=cancelling,
            context_window=200_000,
            max_output=32_768,
        )


# ---------------------------------------------------------------------------
# 结构化校验与渲染单元测试
# ---------------------------------------------------------------------------


def test_parse_accepts_fenced_json_and_validates_sources():
    payload = _summary_json(
        corrections=[{"text": "use xtb", "replaces": "use gaussian", "sources": [4]}]
    )
    fenced = f"```json\n{payload}\n```"
    summary = parse_compact_summary(fenced, trajectory_len=10)
    assert summary.corrections[0].replaces == "use gaussian"
    with pytest.raises(CompactSummaryError):
        parse_compact_summary(payload, trajectory_len=3)  # source 4 越界


def test_render_keeps_correction_replacement_visible():
    summary = parse_compact_summary(
        _summary_json(
            corrections=[{"text": "use xtb", "replaces": "use gaussian", "sources": [1]}],
            pending=[{"text": "report barrier", "sources": [2]}],
        ),
        trajectory_len=5,
    )
    rendered = render_compact_summary(summary)
    assert "use xtb (replaces: use gaussian)" in rendered
    assert "[src: 1]" in rendered
    assert "report barrier" in rendered


def test_contract_text_embeds_the_plan_contract_verbatim():
    from cloudra.runtime_v2.compaction import _COMPACT_INSTRUCTION

    for line in COMPACT_SUMMARY_CONTRACT.splitlines():
        assert line in _COMPACT_INSTRUCTION


def test_segment_trajectory_never_truncates_and_covers_all():
    messages = [
        {"role": "assistant", "content": "a" * 100},
        {"role": "tool", "tool_call_id": "t", "content": "b" * 5000},
        {"role": "assistant", "content": "c" * 100},
    ]
    segments = segment_trajectory(messages, 2_000)
    covered = [i for seg in segments for i in seg["message_indexes"]]
    assert set(covered) == {0, 1, 2}
    for seg in segments:
        assert len(seg["text"]) <= 2_000
    joined = "".join(seg["text"] for seg in segments)
    assert "b" * 5000 not in joined  # 被切块了
    assert joined.count("b") == 5000  # 但一个字符都没丢


def test_context_over_budget_uses_existing_window_and_output():
    messages = [{"role": "user", "content": "x" * 5000}]
    assert context_over_budget(messages, context_window=500, max_output=0)
    assert not context_over_budget(messages, context_window=200_000, max_output=32_768)


# ---------------------------------------------------------------------------
# runner 集成：原子安装、版本守卫、触发集合
# ---------------------------------------------------------------------------


class _EchoTools:
    async def execute(self, agent, call, **_kwargs):
        from cloudra.runtime_v2.policies.base import ToolResult

        return ToolResult(is_success=True, summary=f"echo:{call.arguments.get('x')}", data={})


async def _setup_runner(llm, tools_factory=None, *, query="solve it"):
    from cloudra.runtime_v2.agent_runner import AgentRunner
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.policies import default_stages
    from cloudra.runtime_v2.schemas import Command, InvocationProtocol
    from cloudra.runtime_v2.turn_pipeline import TurnPipeline

    core = RuntimeCore(strict_events=True)
    tools = tools_factory(core) if tools_factory is not None else _EchoTools()
    pipeline = TurnPipeline(
        event_log=core.event_log,
        stages=default_stages(),
        llm=llm,
        tools=tools,
    )
    core.runner = AgentRunner(core, pipeline, retry_backoff=(0.0, 0.0))
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "compact"}))
    project = next(iter(core.projects.values()))
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
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    return core, bus, agent


async def _wait_state(agent, state: str, timeout: float = 5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while agent.state.value != state:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"agent stuck in {agent.state.value}, expected {state}")
        await asyncio.sleep(0.01)


class _ScriptedLLM:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    async def complete(self, agent, messages, tools, **_kwargs):
        self.calls.append(list(messages))
        assert self.responses, "no scripted LLM response left"
        return self.responses.pop(0)


def _patch_summarizer(monkeypatch, responses=None):
    """agent_runner 在调用期从模块 import summarize_with_agent_settings，
    patch 模块属性即可。返回记录型 summarizer。"""
    summarizer = RecordingSummarizer(responses)
    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", summarizer
    )
    return summarizer


@pytest.mark.asyncio
async def test_manual_compact_replaces_session_context_atomically(monkeypatch):
    """手动 compact：覆盖全部轮次（含已完成章节），候选经一条
    context.compacted 事件原子安装；旧轨迹进摘要输入，指令区逐字保留。"""
    from cloudra.runtime_v2.policies.base import ToolCall
    from cloudra.runtime_v2.schemas import Command
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    summarizer = _patch_summarizer(monkeypatch)
    llm = _ScriptedLLM(
        [
            LLMResponse(content="", tool_calls=[ToolCall(id="t1", name="echo", arguments={"x": 1})]),
            LLMResponse(content="done", stop_requested=True),
            LLMResponse(content="", tool_calls=[ToolCall(id="t2", name="echo", arguments={"x": 2})]),
            LLMResponse(content="done again", stop_requested=True),
            LLMResponse(content="continued", stop_requested=True),
        ]
    )
    core, bus, agent = await _setup_runner(
        llm, tools_factory=lambda core: _BigDeliveringTools(core, deliver=False)
    )
    await _wait_state(agent, "succeeded")
    # 第二个用户轮次：完成后轨迹里有一整个已完成章节
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "second task"},
        )
    )
    await _wait_state(agent, "succeeded")
    before = core.session_contexts[agent.id].messages
    assert sum(1 for m in before if m.get("role") == "tool") == 2

    await bus.execute(
        Command(
            type="agent.compact", target={"session_id": agent.id}, payload={"keep_recent": 0}
        )
    )
    await bus.execute(
        Command(
            type="agent.message", target={"session_id": agent.id}, payload={"content": "next"}
        )
    )
    await _wait_state(agent, "succeeded")

    after = core.session_contexts[agent.id].messages
    # 指令区逐字保留全部用户消息（含 message_id 身份）
    users = [m for m in after if m.get("role") == "user"]
    assert [m["content"] for m in users] == ["solve it", "second task", "next"]
    assert all(m.get("message_id") for m in users)
    handoffs = [
        m for m in after if str(m.get("content", "")).startswith("[Context compact]")
    ]
    assert len(handoffs) == 1
    assert handoffs[0]["role"] == "assistant"
    # 已完成章节（run 1 的 tool 轮）折叠进摘要；活动章节（run 2）逐字保留
    handoff_index = after.index(handoffs[0])
    assert not any(m.get("role") == "tool" for m in after[:handoff_index])
    assert any(
        m.get("role") == "tool" and str(m.get("content")) == "x" * 5000
        for m in after[handoff_index:]
    )
    assert summarizer.calls, "summarizer never ran"
    summary_input = "\n".join(
        str(m.get("content")) for call in summarizer.calls for m in call
    )
    assert ("x" * 5000) in summary_input  # 已完成章节的工具结果进了摘要输入
    types = [e.type for e in core.event_log.query_session(agent.id)]
    assert "context.compacted" in types
    finished = [
        e for e in core.event_log.query_session(agent.id) if e.type == "compaction.finished"
    ][-1]
    assert finished.data["compacted"] is True
    assert finished.data["trigger"] == "manual"
    assert finished.data["segments"], "segment coverage must be recorded"


@pytest.mark.asyncio
async def test_install_compacted_version_guard_abandons_stale_candidate():
    """版本守卫：候选输入冻结后投影有新消息 → 放弃候选、不落事件、
    投影保持原样（绝不覆盖新增用户纠正）。"""
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.schemas import AgentSession

    core = RuntimeCore(strict_events=True)
    agent = AgentSession(id="as_v", project_id="prj_v", role_id="coordinator", display_name="c")
    contexts = core.contexts
    await contexts.append_output(
        agent=agent,
        run_id="run1",
        messages=[{"role": "user", "content": "v1"}],
    )
    stale_version = len(core.session_contexts[agent.id].messages)
    # 冻结后新消息进入投影
    await contexts.append_output(
        agent=agent, run_id="run1", messages=[{"role": "assistant", "content": "new work"}]
    )
    installed = await contexts.install_compacted(
        agent=agent,
        run_id="run1",
        messages=[{"role": "user", "content": "candidate"}],
        prefix_meta=None,
        expected_version=stale_version,
        trigger="manual",
    )
    assert installed is False
    assert not [
        e for e in core.event_log.query_session(agent.id) if e.type == "context.compacted"
    ]
    assert core.session_contexts[agent.id].messages[-1]["content"] == "new work"


@pytest.mark.asyncio
async def test_schedule_stop_does_not_compact():
    """Task 5：schedule reminder 收尾不再无条件 compact（触发只有
    手动/预算/overflow 三种）。"""
    from cloudra.runtime_v2.schemas import Command
    from cloudra.runtime_v2.turn_pipeline import LLMResponse

    llm = _ScriptedLLM(
        [
            LLMResponse(content="watching", stop_requested=True),
            LLMResponse(content="still ok", stop_requested=True),
        ]
    )
    core, bus, agent = await _setup_runner(llm)
    await _wait_state(agent, "succeeded")
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "[Reminder] check the gaussian log"},
        )
    )
    await _wait_state(agent, "succeeded")
    assert not [
        e for e in core.event_log.query_session(agent.id) if e.type == "compaction.started"
    ]


class _BigDeliveringTools:
    """回大结果（触发预算估算）；deliver=True 时首次调用投递第二个用户消息。"""

    def __init__(self, core, deliver: bool = True) -> None:
        self.core = core
        self._deliver = deliver
        self.delivered = False

    async def execute(self, agent, call, **_kwargs):
        from cloudra.runtime_v2.policies.base import ToolResult

        if self._deliver and not self.delivered:
            self.delivered = True
            self.core.mailbox.deliver(
                to_session_id=agent.id,
                project_id=agent.project_id,
                content="second task",
                sender="user",
            )
        return ToolResult(is_success=True, summary="x" * 5000, data={})


class _TwoToolsLLM:
    """tool、tool、stop 三段；全部轮次记录 messages。"""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def complete(self, agent, messages, tools, **_kwargs):
        from cloudra.runtime_v2.policies.base import ToolCall
        from cloudra.runtime_v2.turn_pipeline import LLMResponse

        self.calls.append(list(messages))
        index = len(self.calls)
        if index == 1:
            return LLMResponse(
                content="", tool_calls=[ToolCall(id="t1", name="echo", arguments={"x": 1})]
            )
        if index == 2:
            return LLMResponse(
                content="", tool_calls=[ToolCall(id="t2", name="echo", arguments={"x": 2})]
            )
        return LLMResponse(content="done", stop_requested=True)


@pytest.mark.asyncio
async def test_budget_trigger_compacts_when_over_estimate(monkeypatch):
    """预算触发：投影估算超过 (context_window − 输出预算)×余量 时自动压缩；
    已完成章节进摘要，活动尾部逐字保留。"""
    from cloudra.runtime_v2.schemas import Command

    summarizer = _patch_summarizer(monkeypatch)
    llm = _TwoToolsLLM()
    core, bus, agent = await _setup_runner(
        llm, tools_factory=_BigDeliveringTools, query=None
    )
    # 极小窗口（预算下限 4096 字符）：大工具结果后投影即超预算；
    # 设置在开跑前完成，消除竞态。
    agent.settings.context_window = 1_200
    agent.settings.max_tokens = 100
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "solve it"},
        )
    )
    await _wait_state(agent, "succeeded")
    finished = [
        e
        for e in core.event_log.query_session(agent.id)
        if e.type == "compaction.finished" and e.data.get("trigger") == "budget"
    ]
    assert finished, "budget compaction never fired"
    assert any(e.data.get("compacted") for e in finished)
    assert summarizer.calls
    # 压缩后轮次的请求含 handoff，且用户指令逐字在位
    handoff_seen = any(
        "[Context compact]" in str(m.get("content")) for m in llm.calls[-1]
    )
    assert handoff_seen
    users = [
        m for m in core.session_contexts[agent.id].messages if m.get("role") == "user"
    ]
    assert [m["content"] for m in users][:2] == ["solve it", "second task"]


@pytest.mark.asyncio
async def test_budget_compact_refusal_keeps_context_and_records_reason(monkeypatch):
    """摘要不缩短轨迹 → 拒绝替换：原上下文不动，compaction.finished 记录
    原因，run 正常继续。"""
    from cloudra.runtime_v2.schemas import Command

    big_summary = _summary_json(objective={"text": "o" + "x" * 100_000, "sources": []})
    _patch_summarizer(monkeypatch, [big_summary] * 8)
    llm = _TwoToolsLLM()
    core, bus, agent = await _setup_runner(
        llm, tools_factory=_BigDeliveringTools, query=None
    )
    agent.settings.context_window = 1_200
    agent.settings.max_tokens = 100
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "solve it"},
        )
    )
    await _wait_state(agent, "succeeded")
    finished = [
        e
        for e in core.event_log.query_session(agent.id)
        if e.type == "compaction.finished" and e.data.get("trigger") == "budget"
    ]
    assert finished
    assert all(not e.data.get("compacted") for e in finished)
    assert all(e.data.get("reason") == "summary_not_shorter" for e in finished)
    # 原上下文未替换：两条 tool 消息仍在投影里
    assert sum(
        1 for m in core.session_contexts[agent.id].messages if m.get("role") == "tool"
    ) == 2


class _ResolvingLLM(_TwoToolsLLM):
    """带生效设置解析钩子的 fake：真实窗口远大于 spawn 快照。"""

    def resolve_effective_settings(self, agent):
        settings = agent.settings.model_copy(deep=True)
        settings.context_window = 1_000_000
        return settings


@pytest.mark.asyncio
async def test_budget_trigger_uses_resolved_context_window_not_spawn_snapshot(monkeypatch):
    """预算判定必须用 provider 解析的生效窗口，不是 spawn 快照：快照里
    context_window 未设置（0）或是小窗口时，误用它会把 config 的大窗口
    架空，上下文在真实容量的一小半就被压缩。"""
    from cloudra.runtime_v2.schemas import Command

    _patch_summarizer(monkeypatch)
    llm = _ResolvingLLM()
    core, bus, agent = await _setup_runner(llm, tools_factory=_BigDeliveringTools, query=None)
    # 快照小窗口：若预算判定误用它，大工具结果必然触发压缩。
    agent.settings.context_window = 1_200
    agent.settings.max_tokens = 100
    await bus.execute(
        Command(
            type="agent.message",
            target={"session_id": agent.id},
            payload={"content": "solve it"},
        )
    )
    await _wait_state(agent, "succeeded")
    fired = [
        e
        for e in core.event_log.query_session(agent.id)
        if e.type == "compaction.finished" and e.data.get("trigger") == "budget"
    ]
    assert not fired
