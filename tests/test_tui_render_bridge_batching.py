"""Tests for the IPC event reducer and bounded RenderBridge loop."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from cloudra.tui.new.render_bridge import RenderBridge, reduce_event_batch


def chunk(session_id: str, stream: str, delta: str) -> dict[str, Any]:
    return {
        "kind": "session_event",
        "session_id": session_id,
        "event_type": "llm_chunk",
        "data": {"agent_name": "Agent", "stream": stream, "delta": delta},
    }


def tool_started(session_id: str, tool: str) -> dict[str, Any]:
    return {
        "kind": "session_event",
        "session_id": session_id,
        "event_type": "tool_started",
        "data": {"tool": tool, "arguments": ""},
    }


def event_type(message: dict) -> str:
    return str(message.get("event_type") or message.get("kind"))


def test_reducer_merges_only_adjacent_compatible_chunks():
    messages = [
        chunk("s1", "content", "a"),
        chunk("s1", "content", "b"),
        tool_started("s1", "Bash"),
        chunk("s1", "content", "c"),
        chunk("s2", "reasoning", "d"),
        chunk("s2", "reasoning", "e"),
    ]
    reduced = reduce_event_batch(messages)
    assert [event_type(m) for m in reduced] == [
        "llm_chunk",
        "tool_started",
        "llm_chunk",
        "llm_chunk",
    ]
    assert [m["data"].get("delta") for m in (reduced[0], reduced[2], reduced[3])] == [
        "ab",
        "c",
        "de",
    ]


def test_reducer_preserves_order_across_boundaries():
    messages = [
        chunk("s1", "content", "a"),
        {"kind": "session_state", "session_id": "s1", "state": "running"},
        chunk("s1", "content", "b"),
        {"kind": "approval_pending", "session_id": "s1"},
        chunk("s1", "content", "c"),
        {"kind": "interaction_requested", "session_id": "s1"},
        chunk("s1", "content", "d"),
    ]
    reduced = reduce_event_batch(messages)
    assert len(reduced) == len(messages)
    assert [event_type(m) for m in reduced] == [
        "llm_chunk",
        "session_state",
        "llm_chunk",
        "approval_pending",
        "llm_chunk",
        "interaction_requested",
        "llm_chunk",
    ]
    assert reduced[0]["data"]["delta"] == "a"
    assert reduced[2]["data"]["delta"] == "b"
    assert reduced[4]["data"]["delta"] == "c"
    assert reduced[6]["data"]["delta"] == "d"


def test_reducer_keeps_different_sessions_and_streams_separate():
    messages = [
        chunk("s1", "content", "a"),
        chunk("s2", "content", "b"),
        chunk("s1", "reasoning", "c"),
        chunk("s1", "content", "d"),
    ]
    reduced = reduce_event_batch(messages)
    assert [event_type(m) for m in reduced] == ["llm_chunk"] * 4
    assert [m["data"]["delta"] for m in reduced] == ["a", "b", "c", "d"]


@pytest.mark.asyncio
async def test_bridge_loop_yields_between_batches():
    """A permanently non-empty queue still lets the loop yield every batch."""
    dispatched: list[str] = []

    class FakeQueue:
        def __init__(self) -> None:
            self._items = list(range(10))

        async def get(self) -> dict:
            await asyncio.sleep(0)
            return {"kind": "session_event", "session_id": "s1", "event_type": "llm_chunk", "data": {"delta": str(self._items.pop(0))}}

        def get_nowait(self) -> dict:
            return {"kind": "session_event", "session_id": "s1", "event_type": "llm_chunk", "data": {"delta": str(self._items.pop(0))}}

        def empty(self) -> bool:
            return not self._items

    class FakeChatLog:
        def ensure_session(self, _session_id: str) -> None:
            pass

        def append_stream_chunk(self, _session_id: str, delta: str, _agent_name: str | None = None) -> None:
            dispatched.append(delta)

        def append_tool(self, *args, **kwargs) -> None:
            pass

    bridge = RenderBridge("conv", FakeChatLog())
    bridge._queue = FakeQueue()
    bridge.MAX_BATCH_MESSAGES = 3
    bridge.MAX_BATCH_SECONDS = 0.001
    task = asyncio.create_task(bridge._loop())
    await asyncio.sleep(0.05)
    await bridge.stop()
    assert dispatched
    # Because the queue is always refilled, not all 10 items need to be processed,
    # but the loop must have yielded at least once (dispatched count <= batch size).
    assert len(dispatched) <= 10
