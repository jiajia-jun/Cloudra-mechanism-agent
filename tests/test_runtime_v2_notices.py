"""NoticeManager unit tests: batch/cursor consumption semantics (Task 3).

消费模型：collect_batch 取回「自消费游标以来的变更」并 park 为 pending
（重试原样返回）；confirm_consumed 在消息进入上下文后推进游标。
fresh=True 是新上下文边界：渲染当前 pin 状态 + 未消费 push。
"""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PolicyResult, ToolResult
from cloudra.runtime_v2.schemas import (
    AgentCapabilities,
    AgentSession,
    PermissionSet,
    RuntimeSettings,
)
from cloudra.runtime_v2.turn_pipeline import LLMResponse, TurnPipeline
from tests.notice_support import commit_notices


def test_notice_restore_reads_only_context_projection_events(monkeypatch):
    log = EventLog(strict=True)
    log.append("context.pin_set", stream="agent", project_id="p", session_id="s",
               data={"key": "goal", "content": "retained pin"})
    log.append("agent.warning", stream="agent", project_id="p", session_id="s",
               data={"content": "irrelevant large audit payload"})

    def reject_full_history(_self):
        raise AssertionError("notice restore must not decode unrelated event history")

    monkeypatch.setattr(EventLog, "__iter__", reject_full_history)
    notices = NoticeManager()
    notices.restore_from(log)
    assert notices.pin_content("s", "goal") == "retained pin"
    notices.push("s", "after restore")
    notices.collect_batch("s", fresh=False)
    assert notices.pending_batch("s")[1] == 3


def test_unchanged_pin_is_not_repeated():
    notices = NoticeManager()
    notices.pin("s1", "goal", "first")
    first = notices.collect_batch("s1", fresh=True)
    assert [m["content"] for m in first] == ["first"]
    commit_notices(notices, "s1")
    # 未变化 pin 不重复：增量批次为空
    assert notices.collect_batch("s1", fresh=False) == []
    # stage 每轮同内容重 pin 是 no-op：无变更、无消息
    notices.pin("s1", "goal", "first")
    assert notices.collect_batch("s1", fresh=False) == []


def test_updated_pin_appends_new_version():
    notices = NoticeManager()
    notices.pin("s1", "goal", "v1")
    notices.collect_batch("s1", fresh=True)
    commit_notices(notices, "s1")
    notices.pin("s1", "goal", "v2")
    batch = notices.collect_batch("s1", fresh=False)
    assert len(batch) == 1
    assert batch[0]["content"].startswith("[Updated context notice: goal]")
    assert "v2" in batch[0]["content"]
    commit_notices(notices, "s1")
    assert notices.collect_batch("s1", fresh=False) == []
    # 新上下文边界渲染的是当前状态 v2（不是 v1 + 更新）
    assert [m["content"] for m in notices.collect_batch("s1", fresh=True)] == ["v2"]


def test_unpin_appends_retraction():
    notices = NoticeManager()
    notices.pin("s1", "goal", "G")
    notices.collect_batch("s1", fresh=True)
    commit_notices(notices, "s1")
    notices.unpin("s1", "goal")
    batch = notices.collect_batch("s1", fresh=False)
    assert len(batch) == 1
    assert batch[0]["content"].startswith("[Context notice retracted: goal]")
    commit_notices(notices, "s1")
    assert notices.collect_batch("s1", fresh=True) == []


def test_unpin_unknown_key_is_noop():
    notices = NoticeManager()
    notices.unpin("s1", "ghost")
    assert notices.collect_batch("s1", fresh=False) == []


def test_pending_batch_is_fixed_for_retry():
    """未确认的批次原样保留：LLM 重试拿到同一批，不重新 drain。"""
    notices = NoticeManager()
    notices.push("s1", "hint")
    first = notices.collect_batch("s1", fresh=True)
    again = notices.collect_batch("s1", fresh=True)
    # fresh 边界允许重算（内容不变时逐字节一致）
    assert [m["content"] for m in again] == [m["content"] for m in first]
    same = notices.collect_batch("s1", fresh=False)
    assert [m["content"] for m in same] == [m["content"] for m in first]
    # 未 confirm 期间到达的新变更不进已准备批次，下一轮才出现
    notices.push("s1", "later")
    still = notices.collect_batch("s1", fresh=False)
    assert [m["content"] for m in still] == ["hint"]
    commit_notices(notices, "s1")
    assert [m["content"] for m in notices.collect_batch("s1", fresh=False)] == ["later"]


def test_two_distinct_pushes_are_both_delivered():
    """连续两条不同内容的 push 都必须投递（不存在内容去重误删）。"""
    notices = NoticeManager()
    notices.push("s1", "alpha")
    notices.push("s1", "beta")
    assert [m["content"] for m in notices.collect_batch("s1", fresh=False)] == [
        "alpha",
        "beta",
    ]
    commit_notices(notices, "s1")
    assert notices.collect_batch("s1", fresh=False) == []


def test_fresh_boundary_renders_current_pins_and_unconsumed_pushes():
    notices = NoticeManager()
    notices.pin("s1", "goal", "G")
    notices.push("s1", "old push")
    notices.collect_batch("s1", fresh=True)
    commit_notices(notices, "s1")
    notices.push("s1", "new push")
    # 新上下文：pin 当前状态重渲染；已消费 push 不重现，未消费 push 不丢
    assert [m["content"] for m in notices.collect_batch("s1", fresh=True)] == [
        "G",
        "new push",
    ]


def test_restore_keeps_unconsumed_changes_pending():
    """重启恢复：pin 状态与消费游标从事件重建；未消费 push 不丢。"""
    log = EventLog(strict=True)
    notices = NoticeManager()
    notices.attach(log, lambda session_id: "prj")
    notices.pin("s1", "goal", "G")
    notices.push("s1", "delivered")
    notices.collect_batch("s1", fresh=True)
    commit_notices(notices, "s1")
    notices.push("s1", "never-sent")
    assert [e.type for e in log].count("context.appended") == 1

    restored = NoticeManager()
    restored.attach(log, lambda session_id: "prj")
    restored.restore_from(log)
    # 新上下文边界：pin 当前状态 + 未消费 push；已消费 push 不重现
    assert [m["content"] for m in restored.collect_batch("s1", fresh=True)] == [
        "G",
        "never-sent",
    ]
    # 同上下文增量：只有未消费的 push
    restored2 = NoticeManager()
    restored2.attach(log, lambda session_id: "prj")
    restored2.restore_from(log)
    assert [m["content"] for m in restored2.collect_batch("s1", fresh=False)] == [
        "never-sent"
    ]


class _PinStage:
    name = "pin"

    def __init__(self, notices: NoticeManager) -> None:
        self.notices = notices
        self._pushed = False

    async def before_tool(self, ctx, call):
        return PolicyResult.allow()

    async def after_tool(self, ctx, call, result):
        return None

    async def before_llm(self, ctx, messages):
        self.notices.pin(ctx.agent.id, "goal", "[Task goal] keep me")
        if not self._pushed:
            self.notices.push(ctx.agent.id, "once")
            self._pushed = True


class _FakeLLM:
    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    async def complete(self, agent, messages, tools, on_delta=None):
        self.seen.append(list(messages))
        return LLMResponse(content="ok")


class _FakeTools:
    async def execute(self, agent, call):
        return ToolResult(is_success=True, summary="ok")


async def _run_turn(pipeline, agent, notices=None, history=None):
    return await pipeline.run_turn(
        agent=agent,
        run_id="run1",
        settings=RuntimeSettings(),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=[]),
        inbox_messages=[{"content": "hi"}] if not history else [],
        history=history or [],
        notices=notices,
    )


@pytest.mark.asyncio
async def test_pipeline_consumes_notices_once_across_turns():
    """管线两轮：首轮（fresh 边界）带 pin+push；confirm 后第二轮
    无变化 pin 不重复、已消费 push 不重发——旧消息在历史里保持原位。"""
    log = EventLog(strict=True)
    notices = NoticeManager()
    llm = _FakeLLM()
    pipeline = TurnPipeline(
        event_log=log,
        stages=[_PinStage(notices)],
        llm=llm,
        tools=_FakeTools(),
    )
    agent = AgentSession(
        id="as_test",
        project_id="prj",
        role_id="coordinator",
        display_name="c",
    )
    await _run_turn(pipeline, agent, notices)
    first = llm.seen[0]
    system = [m for m in first if m.get("role") == "system"]
    assert any(m["content"] == "[Task goal] keep me" for m in system)
    assert any(m["content"] == "once" for m in system)

    # runner 的做法：通知消息写进 history 后 confirm
    notice_messages = commit_notices(notices, agent.id)
    history = [
        {"role": "user", "content": "hi"},
        *notice_messages,
        {"role": "assistant", "content": "ok"},
    ]
    await _run_turn(pipeline, agent, notices, history=history)
    second = llm.seen[1]
    # 第二轮 = 历史原样 + 无新增：前缀完整保持
    assert second[: len(first)] == first
    assert len(second) == len(history)


@pytest.mark.asyncio
async def test_pipeline_retry_without_confirm_replays_same_batch():
    """失败轮次未 confirm：下一轮（fresh 边界重算）渲染同一批内容。"""
    log = EventLog(strict=True)
    notices = NoticeManager()
    llm = _FakeLLM()
    pipeline = TurnPipeline(
        event_log=log,
        stages=[_PinStage(notices)],
        llm=llm,
        tools=_FakeTools(),
    )
    agent = AgentSession(
        id="as_test",
        project_id="prj",
        role_id="coordinator",
        display_name="c",
    )
    await _run_turn(pipeline, agent, notices)
    # 模拟失败：不 confirm，直接以同一（空）history 重试
    await _run_turn(pipeline, agent, notices)
    assert llm.seen[1] == llm.seen[0]


def test_scientific_replacements_deliver_only_latest_hint_and_other_notices():
    notices = NoticeManager()
    prefix = 'guidance-scientific-reflection:'
    notices.pin('s1', prefix + 'first', 'Initial observation')
    notices.collect_batch('s1', fresh=True)
    commit_notices(notices, 's1')
    notices.pin('s1', prefix + 'first', 'Superseded observation')
    notices.unpin('s1', prefix + 'first')
    notices.pin('s1', prefix + 'second', 'Another obsolete observation')
    notices.unpin('s1', prefix + 'second')
    notices.pin('s1', prefix + 'last', 'Current scientific observation')
    notices.push('s1', 'Keep the assigned task')

    batch = notices.collect_batch('s1', fresh=False)

    text = '\n'.join(row['content'] for row in batch)
    assert 'Superseded observation' not in text
    assert 'Another obsolete observation' not in text
    assert text.count('Current scientific observation') == 1
    assert 'Keep the assigned task' in text
    assert len(batch) == 2
    assert notices.pin_content('s1', prefix + 'first') is None
    assert notices.pin_content('s1', prefix + 'last') == 'Current scientific observation'
    assert notices.collect_batch('s1', fresh=False) == batch
    commit_notices(notices, 's1')
    assert notices.collect_batch('s1', fresh=False) == []


def test_scientific_hint_added_and_cleared_before_delivery_is_not_injected():
    notices = NoticeManager()
    notices.pin('s1', 'guidance-scientific-reflection:scan', 'Obsolete unconsumed hint')
    notices.unpin('s1', 'guidance-scientific-reflection:scan')
    assert notices.collect_batch('s1', fresh=False) == []
    commit_notices(notices, 's1')
    assert notices.collect_batch('s1', fresh=False) == []
