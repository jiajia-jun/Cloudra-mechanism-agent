"""cloudra/reAct.py 工具派发行为固定测试：

- dynamic_deep_merge：流式 tool_call chunk 的增量合并（实现在 cloudra/streaming.py）
- _normalize_tool_calls：function.name 为空时按参数签名反推工具名
- act_result：单个/并发工具派发、错误路径（参数 JSON 解析失败、未知工具、空工具名）、
  stop 工具语义、单工具异常隔离
- 取消语义：AgentCancelled / cancel_requested 在 act_result 阶段的当前表现
  （为后续事件驱动重写固定现状）

全部使用临时 DB + mock 工具，禁止真实网络与真实 LLM 调用。
"""

import asyncio
import json
import sqlite3
from typing import Any, ClassVar

import pytest

from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.react import AgentCancelled
from cloudra.infra.config import get_config
from cloudra.infra.streaming import dynamic_deep_merge
from cloudra.persistence.database import ConversationDB
from cloudra.tools import ToolEntry

# ---------------------------------------------------------------------------
# 测试用最小工具
# ---------------------------------------------------------------------------

class _EchoInput(input_schema):
    text: str


class _EchoOutput(output_schema):
    message: str
    is_success: bool = True


class _EchoTool(Tool):
    tool_id: str = "t-echo"
    tool_name: str = "echo_tool"
    tool_description: str = "回显输入文本"
    input_schema: Any = _EchoInput
    output_schema: Any = _EchoOutput

    async def tool_call(self, user_input, session):
        return _EchoOutput(message=f"echo:{user_input.text}")


class _BoomTool(Tool):
    tool_id: str = "t-boom"
    tool_name: str = "boom_tool"
    tool_description: str = "总是爆炸"
    input_schema: Any = _EchoInput
    output_schema: Any = _EchoOutput

    async def tool_call(self, user_input, session):
        raise ValueError("炸了")


class _CancelTool(Tool):
    tool_id: str = "t-cancel"
    tool_name: str = "cancel_tool"
    tool_description: str = "总是抛 AgentCancelled"
    input_schema: Any = _EchoInput
    output_schema: Any = _EchoOutput

    async def tool_call(self, user_input, session):
        raise AgentCancelled()


class _GateInput(input_schema):
    pass


class _WaiterTool(Tool):
    """并发探针：两个实例都启动后才放行，顺序执行会超时失败。"""

    tool_id: str = "t-waiter"
    tool_name: str = "waiter"
    tool_description: str = "并发探针"
    input_schema: Any = _GateInput
    output_schema: Any = _EchoOutput

    gate: ClassVar[dict] = {"started": [], "event": None}

    async def tool_call(self, user_input, session):
        gate = type(self).gate
        gate["started"].append(self.tool_name)
        if len(gate["started"]) >= 2:
            gate["event"].set()
        await asyncio.wait_for(gate["event"].wait(), timeout=5)
        return _EchoOutput(message=f"done:{self.tool_name}")


class _WaiterA(_WaiterTool):
    tool_name: str = "waiter_a"


class _WaiterB(_WaiterTool):
    tool_name: str = "waiter_b"


class _StopInput(input_schema):
    reason: str = ""


class _StopOutput(output_schema):
    stopped: bool = True
    message: str = "已停止"


class _StopTool(Tool):
    tool_id: str = "t-stop"
    tool_name: str = "stop"
    tool_description: str = "停止循环"
    input_schema: Any = _StopInput
    output_schema: Any = _StopOutput

    async def tool_call(self, user_input, session):
        return _StopOutput()


def _make_react(tmp_path, monkeypatch, tool_classes, conv_id="test-dispatch"):
    """构造一个使用临时 DB / 临时 data_dir 的 reAct 实例（同 test_cancel_flow 模式）。
    tool_classes 接收 Tool **类**（非实例），内部包装为 ToolEntry。
    """
    from cloudra.core.agent import Follower
    from cloudra.core.react import reAct

    db_path = str(tmp_path / "test.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.core.react.get_database_path", lambda _cid: db_path)
    monkeypatch.setattr("cloudra.core.react.get_tools_lst", lambda: [ToolEntry(
        cls=cls,
        tool_name=cls._get_field_default("tool_name") or "",
        tool_id=cls._get_field_default("tool_id") or "",
        input_schema=cls._get_field_default("input_schema"),
    ) for cls in tool_classes])
    monkeypatch.setattr(get_config(), "data_dir", tmp_path)

    agent = Follower(
        id="a-test",
        name="tester",
        prompt="测试",
        query="测试问题",
        conversation_id=conv_id,
    )
    react = reAct(agent)
    return react, agent, db_path


def _tc(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


async def _tool_messages(agent):
    context = await agent.get_context()
    return [m for m in context if m.get("role") == "tool"]


class TestDynamicDeepMerge:
    def test_strings_concatenate(self):
        buf = {}
        dynamic_deep_merge(buf, {"function": {"arguments": '{"text":'}})
        dynamic_deep_merge(buf, {"function": {"arguments": ' "hi"}'}})
        assert buf["function"]["arguments"] == '{"text": "hi"}'

    def test_type_and_name_overwritten_not_appended(self):
        # type/name 是固定枚举值，重复 chunk 直接覆盖而非字符串累加，
        # 否则会产生 'functionfunction' 这类非法值
        buf = {"type": "function", "function": {"name": "echo"}}
        dynamic_deep_merge(buf, {"type": "function", "function": {"name": "_tool"}})
        assert buf["type"] == "function"
        assert buf["function"]["name"] == "_tool"

    def test_numeric_fields_overwritten(self):
        buf = {"index": 0}
        dynamic_deep_merge(buf, {"index": 0, "id": "call_1"})
        assert buf["index"] == 0
        assert buf["id"] == "call_1"


@pytest.mark.asyncio
class TestNormalizeToolCalls:
    async def test_infer_by_full_signature(self, tmp_path, monkeypatch):
        react, _, _ = _make_react(tmp_path, monkeypatch, [_EchoTool, _StopTool])
        tcs = [_tc("c1", "", '{"text": "hi"}')]
        result = react._normalize_tool_calls(tcs)
        assert result[0]["function"]["name"] == "echo_tool"

    async def test_infer_tool_with_no_required_fields(self, tmp_path, monkeypatch):
        # stop 的 required 为空，只能靠全字段集合精确匹配
        react, _, _ = _make_react(tmp_path, monkeypatch, [_EchoTool, _StopTool])
        tcs = [_tc("c1", "", '{"reason": "done"}')]
        result = react._normalize_tool_calls(tcs)
        assert result[0]["function"]["name"] == "stop"

    async def test_infer_by_required_subset_fuzzy(self, tmp_path, monkeypatch):
        # 多了未知字段时：full 精确匹配落空，退到 required 子集模糊匹配
        react, _, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        tcs = [_tc("c1", "", '{"text": "hi", "extra": 1}')]
        result = react._normalize_tool_calls(tcs)
        assert result[0]["function"]["name"] == "echo_tool"

    async def test_no_match_leaves_name_empty(self, tmp_path, monkeypatch):
        react, _, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        tcs = [_tc("c1", "", '{"unknown": 1}')]
        result = react._normalize_tool_calls(tcs)
        assert result[0]["function"]["name"] == ""

    async def test_invalid_arguments_json_leaves_name_empty(self, tmp_path, monkeypatch):
        react, _, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        tcs = [_tc("c1", "", "{invalid json")]
        result = react._normalize_tool_calls(tcs)
        assert result[0]["function"]["name"] == ""

    async def test_arguments_as_dict_also_inferred(self, tmp_path, monkeypatch):
        react, _, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        tcs = [_tc("c1", "", {"text": "hi"})]
        result = react._normalize_tool_calls(tcs)
        assert result[0]["function"]["name"] == "echo_tool"

    async def test_non_empty_names_untouched_and_maps_lazy(self, tmp_path, monkeypatch):
        react, _, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        tcs = [_tc("c1", "echo_tool", '{"text": "hi"}')]
        result = react._normalize_tool_calls(tcs)
        assert result[0]["function"]["name"] == "echo_tool"
        # 没有空 name 时不构建反查表（惰性）
        assert react._tool_arg_maps is None


@pytest.mark.asyncio
class TestActResult:
    async def test_single_tool_dispatch(self, tmp_path, monkeypatch):
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        stopped = await react.act_result([_tc("c1", "echo_tool", '{"text": "hi"}')])

        assert stopped is False
        assert react._continue is True
        messages = await _tool_messages(agent)
        assert len(messages) == 1
        assert messages[0]["tool_call_id"] == "c1"
        payload = json.loads(messages[0]["content"])
        assert payload["message"] == "echo:hi"
        assert payload["is_success"] is True
        # 工具执行完毕后 session 回到 thinking
        assert react.session.state == "thinking"

    async def test_multiple_tool_calls_run_concurrently(self, tmp_path, monkeypatch):
        _WaiterTool.gate = {"started": [], "event": asyncio.Event()}
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_WaiterA, _WaiterB])
        stopped = await react.act_result([
            _tc("c1", "waiter_a", "{}"),
            _tc("c2", "waiter_b", "{}"),
        ])

        assert stopped is False
        # 若顺序执行，waiter_a 会在 event.wait() 上超时（safe_call 包成错误结果）
        assert sorted(_WaiterTool.gate["started"]) == ["waiter_a", "waiter_b"]
        messages = await _tool_messages(agent)
        contents = [m["content"] for m in messages]
        assert any("done:waiter_a" in c for c in contents)
        assert any("done:waiter_b" in c for c in contents)

    async def test_results_recorded_in_call_order(self, tmp_path, monkeypatch):
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        await react.act_result([
            _tc("c1", "echo_tool", '{"text": "first"}'),
            _tc("c2", "echo_tool", '{"text": "second"}'),
        ])
        messages = await _tool_messages(agent)
        assert [m["tool_call_id"] for m in messages] == ["c1", "c2"]
        assert "echo:first" in messages[0]["content"]
        assert "echo:second" in messages[1]["content"]

    async def test_arguments_with_literal_newline_parse(self, tmp_path, monkeypatch):
        # 固定行为：json.loads(strict=False) 允许参数字符串中出现未转义换行，
        # 这是 LLM 生成多行参数时的常见情况
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        stopped = await react.act_result([_tc("c1", "echo_tool", '{"text": "line1\nline2"}')])
        assert stopped is False
        messages = await _tool_messages(agent)
        payload = json.loads(messages[0]["content"])
        assert payload["message"] == "echo:line1\nline2"

    async def test_malformed_json_arguments_error_path(self, tmp_path, monkeypatch):
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        stopped = await react.act_result([_tc("c1", "echo_tool", "{invalid json")])

        assert stopped is False
        messages = await _tool_messages(agent)
        assert len(messages) == 1
        assert messages[0]["tool_call_id"] == "c1"
        assert "Failed to parse tool arguments (JSON Error)" in messages[0]["content"]

    async def test_unknown_tool_error_path(self, tmp_path, monkeypatch):
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        stopped = await react.act_result([_tc("c1", "nonexistent_tool", "{}")])

        assert stopped is False
        messages = await _tool_messages(agent)
        assert len(messages) == 1
        assert "Tool not found: nonexistent_tool" in messages[0]["content"]

    async def test_empty_tool_name_error_path(self, tmp_path, monkeypatch):
        # act_result 不再反推工具名（反推发生在 reasoning 的 _normalize_tool_calls），
        # 空 name 直接回错误消息提醒 LLM 补全
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        stopped = await react.act_result([_tc("c1", "", "{}")])

        assert stopped is False
        messages = await _tool_messages(agent)
        assert len(messages) == 1
        assert "Tool call is missing function.name" in messages[0]["content"]
        assert "echo_tool" in messages[0]["content"]  # 列出当前可用工具

    async def test_stop_tool_requests_termination(self, tmp_path, monkeypatch):
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_StopTool])
        stopped = await react.act_result([_tc("c1", "stop", '{"reason": "done"}')])

        assert stopped is True
        assert react._continue is False
        messages = await _tool_messages(agent)
        assert any('"stopped": true' in m["content"] for m in messages)

    async def test_stop_without_registered_tool_still_stops(self, tmp_path, monkeypatch):
        # 固定现状（怪癖）：stop 判定发生在工具查找之前，
        # 即使工具表里没有 stop，也会返回 stop_requested=True 并写入"找不到工具"错误
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_EchoTool])
        stopped = await react.act_result([_tc("c1", "stop", "{}")])

        assert stopped is True
        assert react._continue is False
        messages = await _tool_messages(agent)
        assert any("Tool not found: stop" in m["content"] for m in messages)

    async def test_tool_exception_isolated_from_others(self, tmp_path, monkeypatch):
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_BoomTool, _EchoTool])
        stopped = await react.act_result([
            _tc("c1", "boom_tool", '{"text": "x"}'),
            _tc("c2", "echo_tool", '{"text": "ok"}'),
        ])

        assert stopped is False
        messages = await _tool_messages(agent)
        assert len(messages) == 2
        # safe_call 把异常包成带工具名的 [Tool error] RuntimeError，
        # gather(return_exceptions=True) 转成错误消息，react 层不再二次套壳
        assert "[Tool error]" in messages[0]["content"]
        assert "boom_tool" in messages[0]["content"]
        assert "炸了" in messages[0]["content"]
        assert "Fix the arguments" in messages[0]["content"]
        # 另一个工具不受影响，正常返回
        assert "echo:ok" in messages[1]["content"]

    async def test_telemetry_events_written(self, tmp_path, monkeypatch):
        react, agent, db_path = _make_react(tmp_path, monkeypatch, [_EchoTool])
        await react.act_result([_tc("c1", "echo_tool", '{"text": "hi"}')])

        with sqlite3.connect(db_path) as con:
            rows = con.execute(
                "SELECT event_type FROM session_events WHERE session_id=?",
                (react.session.id,),
            ).fetchall()
        event_types = [r[0] for r in rows]
        assert "tool_started" in event_types
        assert "tool_finished" in event_types


@pytest.mark.asyncio
class TestActResultCancellation:
    async def test_agent_cancelled_from_tool_is_swallowed(self, tmp_path, monkeypatch):
        # 固定现状：工具内抛出 AgentCancelled 会被 safe_call 包成 RuntimeError，
        # 再被 gather(return_exceptions=True) 吞掉，act_result 正常返回错误消息，
        # 取消信号【不会】从 act_result 传播出去。
        react, agent, _ = _make_react(tmp_path, monkeypatch, [_CancelTool, _EchoTool])
        stopped = await react.act_result([
            _tc("c1", "cancel_tool", '{"text": "x"}'),
            _tc("c2", "echo_tool", '{"text": "ok"}'),
        ])

        assert stopped is False
        assert react._continue is True
        messages = await _tool_messages(agent)
        assert "[Tool error]" in messages[0]["content"]
        assert "cancel_tool" in messages[0]["content"]
        assert "echo:ok" in messages[1]["content"]

    async def test_cancel_requested_state_not_checked_during_act(self, tmp_path, monkeypatch):
        # 固定现状：act_result 内部不调用 _check_cancellation，
        # 即使 DB 中已置 cancel_requested，工具仍执行完毕。
        react, agent, db_path = _make_react(tmp_path, monkeypatch, [_EchoTool])
        with sqlite3.connect(db_path) as con:
            con.execute(
                "UPDATE session SET state='cancel_requested' WHERE session_id=?",
                (react.session.id,),
            )
            con.commit()

        stopped = await react.act_result([_tc("c1", "echo_tool", '{"text": "hi"}')])

        assert stopped is False
        messages = await _tool_messages(agent)
        assert "echo:hi" in messages[0]["content"]


@pytest.mark.asyncio
async def test_context_retained_after_stop(tmp_path, monkeypatch):
    """回归：子 Agent 经 stop 结束后上下文保留（不再 clear_context）——
    上下文已按 session 隔离，新任务不会串，旧上下文留档供事后审查。"""
    react, agent, db_path = _make_react(tmp_path, monkeypatch, [_EchoTool, _StopTool])
    # ContextManager 的事件表走 data_dir 解析的库（不经 cloudra.core.react.get_database_path），
    # 单独初始化，避免 drain_pending_events 打到无表的新库。
    cm = agent._ensure_context_manager()
    ConversationDB.from_path(cm.db_path).init()
    await agent.update_context({"role": "assistant", "content": "历史推理留档"})

    rounds = 0

    async def fake_reasoning():
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            return [_tc("c1", "echo_tool", '{"text": "hi"}')]
        return [_tc("c2", "stop", '{"reason": "done"}')]

    monkeypatch.setattr(react, "reasoning", fake_reasoning)

    result = await react.run()

    assert result
    context = await agent.get_context()
    contents = [str(m.get("content", "")) for m in context]
    assert any("历史推理留档" in c for c in contents)
    assert any(m.get("role") == "tool" for m in context)  # 工具记录也还在


@pytest.mark.asyncio
async def test_revive_after_stop_keeps_context(tmp_path, monkeypatch):
    """回归：schedule 提醒复活场景——executor 在同一 reAct 实例上置 _continue=True
    再次 run()，第一轮留下的上下文必须仍然可见（此前 stop 会 clear_context，
    复活后 agent 完全失忆）。"""
    react, agent, db_path = _make_react(tmp_path, monkeypatch, [_EchoTool, _StopTool])
    cm = agent._ensure_context_manager()
    ConversationDB.from_path(cm.db_path).init()

    rounds = 0

    async def fake_reasoning():
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            return [_tc("c1", "echo_tool", '{"text": "第一轮的计算结果"}')]
        if rounds == 2:
            return [_tc("c2", "stop", '{"reason": "等待计算"}')]
        # 复活后：直接给正文收尾
        return []

    monkeypatch.setattr(react, "reasoning", fake_reasoning)

    first = await react.run()
    assert first

    # 模拟 executor._run_with_reminder_waits 的复活路径
    react._continue = True
    second = await react.run()
    assert second

    context = await agent.get_context()
    # 工具结果以 JSON 存进上下文（ensure_ascii=False，非 ASCII 不转义），按原文匹配
    marker = "第一轮的计算结果"
    contents = [str(m.get("content", "")) for m in context]
    assert any(marker in c for c in contents)
