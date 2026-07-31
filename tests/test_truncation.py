"""输出被 max_tokens 截断的处理：检测、收敛重试、明确 failed（不落错误答案）。"""

import json
import sqlite3
import types

import pytest

from cloudra.database import ConversationDB


def _make_react(tmp_path, monkeypatch, conv_id="test-trunc"):
    from cloudra.agent import Follower
    from cloudra.react import reAct

    db_path = str(tmp_path / "test.db")
    ConversationDB.from_path(db_path).init()
    monkeypatch.setattr("cloudra.react.get_database_path", lambda _conv_id: db_path)

    agent = Follower(
        id="a-test",
        name="tester",
        prompt="测试",
        query="测试问题",
        conversation_id=conv_id,
    )
    react = reAct(agent)
    # context_manager 的 db_path/context_file 默认指向真实数据目录；
    # 测试隔离：全部改到 tmp（真实库没有 context_events 表，且会留下垃圾文件）
    agent._init_context_manager()
    agent.context_manager.context_file = str(tmp_path / "ctx.json")
    agent.context_manager.db_path = db_path
    return react, db_path


def _chunk(content=None, reasoning=None, finish=None, tool_calls=None):
    delta = types.SimpleNamespace(
        content=content,
        reasoning_content=reasoning,
        tool_calls=tool_calls,
    )
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(delta=delta, finish_reason=finish)]
    )


async def _stream(chunks):
    for chunk in chunks:
        yield chunk


class _TC:
    """模拟流式 tool_call 增量块。"""

    def __init__(self, index, data):
        self.index = index
        self._data = data

    def model_dump(self, exclude_none=True):
        return dict(self._data)


@pytest.mark.asyncio
class TestTruncation:
    async def test_failed_transport_still_records_request_diagnostics(
        self,
        tmp_path,
        monkeypatch,
    ):
        react, db_path = _make_react(tmp_path, monkeypatch)

        async def failed_llm_call():
            react.agent._last_request_diagnostics = {
                "trace_id": "llm_failed",
                "prompt_revision": "sha256:prompt",
                "tool_names": ["text_reader"],
            }
            raise RuntimeError("network down")

        object.__setattr__(react.agent, "llm_call", failed_llm_call)
        with pytest.raises(RuntimeError, match="network down"):
            await react._reasoning_once()

        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                """SELECT data FROM session_events
                WHERE session_id=? AND event_type='llm_request_diagnostics'""",
                (react.session.id,),
            ).fetchone()
        assert row is not None
        diagnostics = json.loads(row[0])
        assert diagnostics["trace_id"] == "llm_failed"
        assert diagnostics["request_state"] == "transport_error"

    async def test_retry_then_fail_marks_failed(self, tmp_path, monkeypatch):
        from cloudra.react import LLMOutputTruncated

        react, db_path = _make_react(tmp_path, monkeypatch)
        calls = []

        async def fake_llm_call():
            calls.append(1)
            return _stream([_chunk(reasoning="超长思考……" * 10, finish="length")])

        object.__setattr__(react.agent, "llm_call", fake_llm_call)

        with pytest.raises(LLMOutputTruncated):
            await react.run()

        # 原始 1 次 + 收敛重试 2 次
        assert len(calls) == 3
        # 上下文中注入了两条收敛提示
        ctx = await react.agent.get_context()
        nudges = [
            m for m in ctx
            if m.get("role") == "system" and "截断" in str(m.get("content", ""))
        ]
        assert len(nudges) == 2
        # session 落库 failed，错误说明包含截断原因，且不会把工具结果当最终答案
        with sqlite3.connect(db_path) as con:
            row = con.execute(
                "SELECT state, error, result FROM session WHERE session_id=?",
                (react.session.id,),
            ).fetchone()
        assert row[0] == "failed"
        assert "截断" in row[1]
        assert not row[2]

    async def test_retry_then_success(self, tmp_path, monkeypatch):
        react, db_path = _make_react(tmp_path, monkeypatch)
        responses = [
            _stream([_chunk(reasoning="思考被截断", finish="length")]),
            _stream([
                _chunk(reasoning="好的", finish=None),
                _chunk(
                    finish="tool_calls",
                    tool_calls=[_TC(0, {"id": "c1", "function": {"name": "stop", "arguments": "{}"}})],
                ),
            ]),
        ]
        calls = []

        async def fake_llm_call():
            calls.append(1)
            return responses[len(calls) - 1]

        object.__setattr__(react.agent, "llm_call", fake_llm_call)

        tool_calls = await react.reasoning()
        assert len(calls) == 2
        assert tool_calls and tool_calls[0]["function"]["name"] == "stop"
        # 成功后计数复位
        assert react._truncation_retries == 0

    async def test_leftover_tool_call_buffer_counts_as_truncation(self, tmp_path, monkeypatch):
        """tool_call 的 JSON 被拦腰截断（无 finish 标记、缓冲有残留）也按截断处理。"""
        react, db_path = _make_react(tmp_path, monkeypatch)
        calls = []

        async def fake_llm_call():
            calls.append(1)
            if len(calls) == 1:
                # 流中途直接结束：buffer 里留下半个 tool_call，没有 finish_reason
                return _stream([
                    _chunk(tool_calls=[_TC(0, {"id": "c1", "function": {"name": "text_writer", "arguments": "{\"pa"}})]),
                ])
            return _stream([
                _chunk(finish="tool_calls", tool_calls=[_TC(0, {"id": "c2", "function": {"name": "stop", "arguments": "{}"}})]),
            ])

        object.__setattr__(react.agent, "llm_call", fake_llm_call)

        tool_calls = await react.reasoning()
        assert len(calls) == 2
        assert tool_calls and tool_calls[0]["function"]["name"] == "stop"


def test_max_tokens_defaults_raised():
    """k3 长 thinking 需要更大的输出预算。"""
    from cloudra.agent import Coordinator, Follower

    assert Coordinator(query="t", conversation_id="t").max_tokens == 32768
    assert Follower(
        id="t", name="t", prompt="p", query="t", conversation_id="t"
    ).max_tokens == 16384
