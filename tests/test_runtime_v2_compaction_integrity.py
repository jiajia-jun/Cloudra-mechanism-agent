"""Compact 完整性（计划 2026-09-13-harness-cache-continuity）：

全量压缩（含用户指令与工具调用，无逐字保留区）、tiktoken 容量口径、
结构化摘要校验（来源下标钳制 + 计数）、按容量分段、合并载荷分批、摘要调用
有界等待、拒替换条件与版本守卫。fake summarizer 证明输入覆盖与
"投影里不再留原文"；字段齐全不等于语义完整——语义质量由人工/真实模型
另行检查。
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
    estimate_messages_tokens,
    estimate_tokens,
    parse_compact_summary,
    render_compact_summary,
    render_message_text,
    segment_trajectory,
    usable_prompt_tokens,
)
from cloudra.runtime_v2.dispatcher import WakePolicy


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
async def test_full_history_folds_into_one_summary():
    """全量压缩：用户指令、assistant 工具调用与工具结果一并折叠成一条
    assistant 摘要消息，投影里不留任何逐字尾部。"""
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
        messages, head=[], notices=[],
        summarize=summarizer, context_window=200_000, max_output=32_768,
    )
    assert stats["compacted"] is True
    assert stats["trajectory_messages"] == len(messages)
    # 新上下文只剩一条 assistant 摘要消息
    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert result[0]["content"].startswith("[Context compact]")
    assert not any(m.get("role") == "user" for m in result)
    # 指令与工具结果逐字进了摘要输入
    seen = "\n".join(
        str(m.get("content")) for call in summarizer.calls for m in call
    )
    assert "finish the entire task" in seen
    assert "old log " * 500 in seen


def _context_window_for(budget_tokens: int) -> tuple[int, int]:
    """反推一个可用容量约为 budget_tokens 的 (context_window, max_output)。"""
    window = int(budget_tokens / 0.85) + 100
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
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t2", "name": "bash", "arguments": {"cmd": "tail"}}]},
        {"role": "tool", "tool_call_id": "t2", "content": "job done, barrier 5.0"},
    ]


@pytest.mark.asyncio
async def test_all_rounds_enter_summary_input_and_nothing_stays_verbatim():
    """三轮目标与纠正、两轮 reminder、>12,000 字符轨迹、末尾关键约束、工具
    调用参数全部进入摘要输入；压缩后的上下文只有一条摘要消息。"""
    messages = _trajectory_context()
    summarizer = RecordingSummarizer()
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
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
    # 用户纠正与工具调用（工具名 + 参数）都在摘要输入里
    assert "correction: use xtb, not gaussian" in summary_input
    assert "[Reminder] poll the job again" in summary_input
    assert "-> call bash" in summary_input
    # 新上下文只有一条 assistant 的 [Context compact] handoff
    assert len(new_context) == 1
    handoff = new_context[0]
    assert handoff["role"] == "assistant"
    assert handoff["content"].startswith("[Context compact]")
    assert "solve the mechanism task" in handoff["content"]
    assert stats["handoff_index"] == 0
    assert stats["trajectory_messages"] == len(messages)


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
    window, output = _context_window_for(2_000)
    budget = usable_prompt_tokens(window, output)
    summarizer = RecordingSummarizer()
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        summarize=summarizer,
        context_window=window,
        max_output=output,
    )
    assert stats["compacted"] is True
    # 包括最后一条 assistant 在内的全部轨迹进入摘要
    covered = sorted(
        index for seg in stats["segments"] for index in seg["message_indexes"]
    )
    assert set(covered) == {0, 1, 2, 3, 4}
    segment_calls = summarizer.calls[: len(stats["segments"])]
    # 多段 → 段数 + 一次 merge 调用
    assert len(stats["segments"]) >= 2
    assert len(summarizer.calls) == len(stats["segments"]) + 1
    # 每段不超预算（送出的载荷按同一口径估算）
    for seg, call in zip(stats["segments"], segment_calls):
        assert seg["tokens"] <= budget
        assert estimate_tokens(str(call[-1]["content"])) <= budget
    # 全文无丢失：段拼接包含原消息首尾与几乎所有行（切块边界至多断行）
    joined = "\n".join(str(call[-1]["content"]) for call in segment_calls)
    assert big[:500] in joined and big[-500:] in joined
    # 一个字符都没丢（按渲染后的轨迹逐字符核对）
    expected = sum(render_message_text(m).count("x") for m in messages)
    assert joined.count("x") == expected


@pytest.mark.asyncio
async def test_user_message_over_4000_chars_is_fully_covered_by_summary_input():
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
        summarize=summarizer,
        context_window=200_000,
        max_output=32_768,
    )
    assert stats["compacted"] is True
    # 全文逐字进摘要输入（不截断），但不再逐字留在压缩后的上下文里
    assert big in "\n".join(
        str(m.get("content")) for call in summarizer.calls for m in call
    )
    assert not any(m.get("role") == "user" for m in new_context)


# ---------------------------------------------------------------------------
# 拒替换条件：一律保留原上下文
# ---------------------------------------------------------------------------


async def _refusal(messages, summarizer, **kwargs):
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
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
    stats = await _refusal(messages, RecordingSummarizer(["", ""]))
    assert stats["reason"] == "summary_invalid"
    assert "empty" in stats["error"]


@pytest.mark.asyncio
async def test_structural_validation_error_refused():
    messages = _trajectory_context()
    stats = await _refusal(messages, RecordingSummarizer(["not json at all"] * 2))
    assert stats["reason"] == "summary_invalid"
    stats = await _refusal(
        messages,
        RecordingSummarizer([json.dumps({"objective": {"text": "", "sources": []}})] * 2),
    )
    assert stats["reason"] == "summary_invalid"


@pytest.mark.asyncio
async def test_source_index_out_of_range_clamped_and_recorded():
    """GH #40 实录：1606 条轨迹的摘要因来源下标越界被整体拒收，压缩永久失败。
    越界下标现在钳制进范围、计数透出 stats，压缩得以完成。"""
    messages = _trajectory_context()
    bad = _summary_json(objective={"text": "o", "sources": [9999]})
    summarizer = RecordingSummarizer([bad] * 40)
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        summarize=summarizer,
        context_window=200_000,
        max_output=32_768,
    )
    assert stats["compacted"] is True
    assert stats["clamped_sources"] >= 1
    assert all(seg["tokens"] > 0 for seg in stats["segments"])
    assert new_context[0]["content"].startswith("[Context compact]")


def test_parse_clamps_negative_and_far_out_of_range_sources():
    """负下标与远界外下标（实录场景：1616 vs 0..1606）都钳进范围并计数。"""
    payload = _summary_json(
        objective={"text": "o", "sources": [-5, 1616]},
        next_actions=[{"text": "keep going", "sources": [1607]}],
    )
    summary = parse_compact_summary(payload, trajectory_len=1607)
    assert summary.objective.sources == [0, 1606]
    assert summary.next_actions[0].sources == [1606]
    assert summary.clamped_sources == 3
    # 合法下标原样保留，不计数
    assert parse_compact_summary(
        _summary_json(objective={"text": "o", "sources": [0, 1606]}),
        trajectory_len=1607,
    ).clamped_sources == 0


@pytest.mark.asyncio
async def test_summary_timeout_reports_segment_failure():
    """provider 对超大摘要停滞时必须有界收敛（GH #40：挂起 10+ 分钟）。"""

    class SlowSummarizer:
        async def __call__(self, _messages):
            await asyncio.sleep(30)
            return _summary_json()

    started = asyncio.get_running_loop().time()
    new_context, stats = await compact_context(
        _trajectory_context(),
        head=[],
        notices=[],
        summarize=SlowSummarizer(),
        context_window=200_000,
        max_output=32_768,
        summary_timeout=0.05,
    )
    elapsed = asyncio.get_running_loop().time() - started
    assert stats["compacted"] is False
    assert stats["reason"] == "segment_failed"
    assert new_context is not None
    assert elapsed < 5.0, "summary_timeout must bound the call"


@pytest.mark.asyncio
async def test_single_object_where_array_is_required_retried_then_recovered():
    """模型把列表字段写成单个 entry 对象（真实故障：seq 47043/46632/2819）
    → 带同一段轨迹与校验错误重问一次；模型改对后正常压缩。"""
    messages = _trajectory_context()
    bare_object = json.dumps(
        _summary_payload(
            active_requests={"text": "deliver the barrier", "sources": [0]}
        ),
        ensure_ascii=False,
    )
    summarizer = RecordingSummarizer([bare_object, _summary_json()])
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        summarize=summarizer,
        context_window=200_000,
        max_output=32_768,
    )
    assert stats["compacted"] is True
    assert len(summarizer.calls) == 2, "one retry, not a loop"
    retry = summarizer.calls[1]
    assert retry[0] == summarizer.calls[0][0]  # 同一份系统指令
    assert retry[1] == summarizer.calls[0][1]  # 同一段轨迹
    assert len(retry) == 3  # 不重复发送坏回复，避免重问把请求挤出窗口
    assert retry[2]["role"] == "user"
    assert "active_requests" in retry[2]["content"]
    assert "JSON array" in retry[2]["content"]
    assert "deliver the barrier" in new_context[-1]["content"]


@pytest.mark.asyncio
async def test_single_object_refused_after_the_one_retry():
    messages = _trajectory_context()
    bare_object = json.dumps(
        _summary_payload(active_requests={"text": "x", "sources": []})
    )
    summarizer = RecordingSummarizer([bare_object, bare_object])
    stats = await _refusal(messages, summarizer)
    assert stats["reason"] == "summary_invalid"
    assert "active_requests" in stats["error"]
    assert len(summarizer.calls) == 2, "retry is bounded"


@pytest.mark.asyncio
async def test_segment_failure_refused_and_reports_segment():
    window, output = _context_window_for(1_000)
    messages = _trajectory_context()  # 多段
    summarizer = RecordingSummarizer([_summary_json(), RuntimeError("segment boom")])
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
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
    window, output = _context_window_for(1_000)
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
async def test_message_over_budget_is_segmented_not_refused():
    """单条消息本身超过可用容量：切块跨段覆盖。旧实现遇到"逐字指令区超
    容量"直接拒绝压缩——长会话在那之后再也压不动。"""
    big = "y" * 5000
    messages = [
        {"role": "user", "content": big},
        {"role": "assistant", "content": "a" * 5000},
    ]
    summarizer = RecordingSummarizer()
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        summarize=summarizer,
        context_window=2_000,
        max_output=0,
    )
    assert stats["compacted"] is True
    assert len(stats["segments"]) >= 2
    covered = sorted(
        index for seg in stats["segments"] for index in seg["message_indexes"]
    )
    assert set(covered) == {0, 1}
    payloads = "".join(
        str(call[-1].get("content"))
        for call in summarizer.calls
        if str(call[0].get("content") or "").startswith("You are compacting")
    )
    assert payloads.count("y") == 5000  # 一个字符都没丢
    assert "y" * 5000 not in new_context[0]["content"]


@pytest.mark.asyncio
async def test_merge_payloads_are_batched_when_they_exceed_the_budget():
    """片段摘要的合并载荷超预算时分批多轮合并：一次装不下的输入不再直接
    失败（单次合并实现会在长会话上 merge_failed，进而再也压不动）。"""
    # 除合并正文外，还要容纳系统指令与一次结构校验重问。
    window, output = _context_window_for(1_200)
    messages = [{"role": "assistant", "content": "z" * 1_200} for _ in range(18)]
    fat = _summary_json(objective={"text": "o" * 1_000, "sources": []})
    seen: list[list[dict]] = []

    async def summarizer(messages, **_kwargs):
        seen.append(messages)
        return fat

    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        summarize=summarizer,
        context_window=window,
        max_output=output,
    )
    assert stats["compacted"] is True
    assert len(stats["segments"]) >= 8
    merge_calls = [
        call
        for call in seen
        if str(call[0].get("content") or "").startswith("You are merging")
    ]
    assert len(merge_calls) >= 2, "merge must not be attempted as one oversized call"
    assert len(new_context) == 1


def test_compaction_retry_gate_requires_new_growth():
    """预算触发的重试闸门：一次拒绝后，投影要再长出预算的
    COMPACT_RETRY_GROWTH 才重新尝试（否则每轮都重跑一次全量摘要）。"""
    from cloudra.runtime_v2.agent_runner import COMPACT_RETRY_GROWTH, AgentRunner
    from cloudra.runtime_v2.core import RuntimeCore

    runner = AgentRunner(RuntimeCore(strict_events=True), object())
    budget = 10_000
    assert runner._compaction_retry_due("s1", 20_000, budget) is True
    runner._compact_refusals["s1"] = 20_000
    assert runner._compaction_retry_due("s1", 20_100, budget) is False
    step = max(int(budget * COMPACT_RETRY_GROWTH), 1024)
    assert runner._compaction_retry_due("s1", 20_000 + step, budget) is True


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
                summarize=cancelling,
            context_window=200_000,
            max_output=32_768,
        )


@pytest.mark.asyncio
async def test_summary_call_is_recorded_as_kind_summary(monkeypatch):
    """摘要调用落 kind="summary" 的 llm.completed：压缩成本与主链路一起进
    遥测（cloudra stats tokens 单列），不再隐形。"""
    from types import SimpleNamespace

    from cloudra.runtime_v2.compaction import summarize_with_agent_settings
    from cloudra.runtime_v2.events import EventLog
    from cloudra.runtime_v2.schemas import AgentSession

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def create_with_retry(self, **_kwargs):
            return SimpleNamespace(
                usage={"prompt_tokens": 900, "completion_tokens": 90, "total_tokens": 990},
                finish_reason="stop",
                choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))],
            )

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("cloudra.infra.llm_client.LLMClient", FakeClient)
    agent = AgentSession(
        id="as_sum", project_id="prj_sum", role_id="coordinator", display_name="c"
    )
    log = EventLog(strict=False)
    out = await summarize_with_agent_settings(
        agent, [{"role": "user", "content": "payload"}], event_log=log, run_id="r1"
    )
    assert out == "OK"
    events = [e for e in log.query_session("as_sum") if e.type == "llm.completed"]
    assert len(events) == 1
    assert events[0].data["kind"] == "summary"
    assert events[0].data["usage"]["prompt_tokens"] == 900
    assert events[0].run_id == "r1"


@pytest.mark.asyncio
async def test_summary_usage_is_json_serializable(monkeypatch):
    """真实故障（GH #40 线程）：raw response.usage 是 openai SDK 的
    CompletionUsage 对象，直接进 llm.completed 事件让 event_writer 的
    json 落盘抛 EventPersistenceError——持久化管道被堵死，/compact 500、
    后续写命令全部失效。事件数据必须 JSON 可序列化。"""
    import json as _json
    from types import SimpleNamespace

    from cloudra.runtime_v2.compaction import summarize_with_agent_settings
    from cloudra.runtime_v2.events import EventLog
    from cloudra.runtime_v2.schemas import AgentSession

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def create_with_retry(self, **_kwargs):
            return SimpleNamespace(
                usage=object(),  # 模拟未转换的 CompletionUsage：不可序列化
                finish_reason="stop",
                choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))],
            )

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("cloudra.infra.llm_client.LLMClient", FakeClient)
    agent = AgentSession(
        id="as_sum2", project_id="prj_sum", role_id="coordinator", display_name="c"
    )
    log = EventLog(strict=False)
    out = await summarize_with_agent_settings(
        agent, [{"role": "user", "content": "payload"}], event_log=log, run_id="r1"
    )
    assert out == "OK"
    events = [e for e in log.query_session("as_sum2") if e.type == "llm.completed"]
    assert len(events) == 1
    # 不可序列化（旧代码）就在这里 TypeError——这正是线上 /compact 500 的机制
    _json.dumps(events[0].data)


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
    assert summary.clamped_sources == 0
    # source 4 越界 → 钳到末位（不拒收）
    clamped = parse_compact_summary(payload, trajectory_len=3)
    assert clamped.corrections[0].sources == [2]
    assert clamped.clamped_sources == 1
    # 结构不符仍 fail-loud（只有来源下标越界走钳制）
    with pytest.raises(CompactSummaryError):
        parse_compact_summary(json.dumps({"active_requests": []}), trajectory_len=3)


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
    segments = segment_trajectory(messages, 500)
    covered = [i for seg in segments for i in seg["message_indexes"]]
    assert set(covered) == {0, 1, 2}
    for seg in segments:
        assert seg["tokens"] <= 500
    joined = "".join(seg["text"] for seg in segments)
    assert "b" * 5000 not in joined  # 被切块了
    assert joined.count("b") == 5000  # 但一个字符都没丢


def test_context_over_budget_uses_existing_window_and_output():
    messages = [{"role": "user", "content": "x" * 5000}]
    assert context_over_budget(messages, context_window=500, max_output=0)
    assert not context_over_budget(messages, context_window=200_000, max_output=32_768)


def test_non_ascii_text_is_not_undercounted():
    """中文按 1 字符 ≈ 1 token 估算：旧实现一律 4 字符/token，中文会话的
    预算闸门会被 4 倍低估架空。"""
    ascii_tokens = estimate_messages_tokens([{"role": "user", "content": "x" * 4_000}])
    cjk_tokens = estimate_messages_tokens([{"role": "user", "content": "构" * 4_000}])
    assert ascii_tokens < 1_100
    assert cjk_tokens > 3_900


def test_tool_call_arguments_are_measured_and_rendered():
    """工具调用参数是线上真实发送的内容：估算必须计入，摘要器必须看得见
    调用了什么工具（旧实现只看 content，两者都丢）。"""
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "c1", "name": "run_python", "arguments": {"code": "x" * 8_000}}
        ],
    }
    rendered = render_message_text(message)
    assert "run_python" in rendered
    assert "x" * 8_000 in rendered
    bare = {"role": "assistant", "content": None}
    assert estimate_messages_tokens([message]) > 1_000
    # 多出来的量只能来自工具调用参数（旧实现这里是 0 差额）
    assert estimate_messages_tokens([message]) > estimate_messages_tokens([bare]) + 900


def test_estimator_delegates_to_token_estimator(monkeypatch):
    """容量口径走 TokenEstimator（tiktoken）单一事实源，不再自造 chars/4 口径。"""
    from cloudra.infra.token_estimator import TokenEstimator

    monkeypatch.setattr(
        TokenEstimator, "count_text", classmethod(lambda cls, text: 111)
    )
    monkeypatch.setattr(
        TokenEstimator, "count_messages", classmethod(lambda cls, messages: 222)
    )
    assert estimate_tokens("whatever") == 111
    assert estimate_messages_tokens([{"role": "user", "content": "x"}]) == 222


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
    """手动 compact：覆盖全部轮次（含已完成章节与用户指令），候选经一条
    context.compacted 事件原子安装；旧轨迹进摘要输入，投影不留原文。"""
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
            type="agent.compact", target={"session_id": agent.id}, payload={}
        )
    )
    await bus.execute(
        Command(
            type="agent.message", target={"session_id": agent.id}, payload={"content": "next"}
        )
    )
    await _wait_state(agent, "succeeded")

    after = core.session_contexts[agent.id].messages
    # 全量折叠：旧用户消息不再逐字驻留，压缩边界之后到达的输入照常逐字可见
    users = [m for m in after if m.get("role") == "user"]
    assert [m["content"] for m in users] == ["next"]
    assert all(m.get("message_id") for m in users)
    handoffs = [
        m for m in after if str(m.get("content", "")).startswith("[Context compact]")
    ]
    assert len(handoffs) == 1
    assert handoffs[0]["role"] == "assistant"
    # 两个已完成章节（含工具结果）都不在投影里，只在摘要输入里
    assert not any(m.get("role") == "tool" for m in after)
    assert summarizer.calls, "summarizer never ran"
    summary_input = "\n".join(
        str(m.get("content")) for call in summarizer.calls for m in call
    )
    assert ("x" * 5000) in summary_input
    assert "solve it" in summary_input and "second task" in summary_input
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
            await self.core.dispatcher.commit_and_deliver(
                to_session_id=agent.id,
                project_id=agent.project_id,
                content="second task",
                sender="user",
                wake=WakePolicy.NEVER,
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
    全部历史折叠成摘要。"""
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
    # 压缩后轮次的请求含 handoff，旧指令只以摘要形式存在
    handoff_seen = any(
        "[Context compact]" in str(m.get("content")) for m in llm.calls[-1]
    )
    assert handoff_seen
    assert any(
        "solve it" in str(m.get("content"))
        for call in summarizer.calls
        for m in call
    )
    assert not any(
        m.get("role") == "user" and m.get("content") == "solve it"
        for m in core.session_contexts[agent.id].messages
    )


@pytest.mark.asyncio
async def test_budget_compact_refusal_keeps_context_and_records_reason(monkeypatch):
    """摘要模型失控（每段都回 10 万字符）→ 拒绝替换：原上下文不动，
    记录拒因并明确停止，不能继续发送超过已配置窗口的请求。"""
    from cloudra.runtime_v2.schemas import Command

    big_summary = _summary_json(objective={"text": "o" + "x" * 100_000, "sources": []})

    async def fake_summarize(*args, **_kwargs):
        return big_summary

    monkeypatch.setattr(
        "cloudra.runtime_v2.compaction.summarize_with_agent_settings", fake_summarize
    )
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
    await _wait_state(agent, "failed")
    finished = [
        e
        for e in core.event_log.query_session(agent.id)
        if e.type == "compaction.finished" and e.data.get("trigger") == "budget"
    ]
    assert finished
    assert all(not e.data.get("compacted") for e in finished)
    assert all(
        e.data.get("reason") in {"summary_not_shorter", "merge_capacity", "summary_capacity"}
        for e in finished
    )
    # 已完成的两轮工具结果仍在；未向模型发送第三个超限请求。
    assert sum(
        1 for m in core.session_contexts[agent.id].messages if m.get("role") == "tool"
    ) == 2
    assert len(llm.calls) == 2


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


def test_parse_strips_fenced_json_with_language_tag_and_trailing_prose():
    """GH #48：围栏带语言标签（```json）且闭合围栏后还有散文——旧剥离
    要求末行恰为 ```，散文导致不剥、json.loads 在 char 0 即炸。"""
    payload = _summary_json()
    fenced = f"```json\n{payload}\n```\n另外补充：以上即本次摘要内容。"
    summary = parse_compact_summary(fenced, trajectory_len=5)
    assert summary.objective.text == "solve the mechanism task"


def test_parse_promotes_objective_array_and_bare_string_entries():
    """GH #48 实测（glm-5.3-flash）：objective 写成单元素数组、列表字段
    条目写成裸字符串——无损提升，不烧掉唯一一次重问。"""
    payload = json.dumps(
        {
            "objective": [{"text": "推进 scan 项目", "sources": [0]}],
            "active_requests": ["继续回填 gold [3]"],
            "corrections": [],
            "constraints": [],
            "pending": [],
            "completed": [],
            "failed_attempts": [],
            "evidence": [],
            "next_actions": [],
        },
        ensure_ascii=False,
    )
    summary = parse_compact_summary(payload, trajectory_len=5)
    assert summary.objective.text == "推进 scan 项目"
    assert summary.active_requests[0].text == "继续回填 gold [3]"
    assert summary.active_requests[0].sources == []


def test_parse_promotes_objective_bare_string():
    payload = json.dumps({"objective": "计算机理并回填 gold"}, ensure_ascii=False)
    summary = parse_compact_summary(payload, trajectory_len=3)
    assert summary.objective.text == "计算机理并回填 gold"
    assert summary.objective.sources == []


@pytest.mark.asyncio
async def test_segment_failure_labels_empty_str_exceptions():
    """GH #48：裸 TimeoutError 的 str() 为空——拒替换 stats 必须落到
    类型名，不许 error='' 把真实拒因藏住（线上即此症状）。"""

    class TimeoutSummarizer:
        async def __call__(self, _messages):
            raise asyncio.TimeoutError()

    messages = _trajectory_context()
    new_context, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        summarize=TimeoutSummarizer(),
        context_window=200_000,
        max_output=32_768,
    )
    assert stats["compacted"] is False
    assert stats["reason"] == "segment_failed"
    assert stats["error"] == "TimeoutError"
    assert new_context == messages
