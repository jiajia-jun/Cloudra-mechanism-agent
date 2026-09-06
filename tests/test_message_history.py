"""JsonlMessageHistory 钉板测试。"""

import json

import pytest

from cloudra.core.message_history import (
    JsonlMessageHistory,
    build_llm_messages,
    read_context_file,
    repair_tool_pairing,
)


@pytest.fixture
def history(tmp_path):
    return JsonlMessageHistory(
        conversation_id="test-conv",
        agent_id="a-test",
        initial_query="hello",
        context_file=str(tmp_path / "context.jsonl"),
    )


@pytest.mark.asyncio
async def test_load_and_append(history):
    ctx = await history.load()
    assert len(ctx) == 1
    assert ctx[0]["role"] == "user"
    assert ctx[0]["content"] == "hello"

    await history.append({"role": "assistant", "content": "hi there"})
    ctx = await history.load()
    assert len(ctx) == 2
    assert ctx[1]["content"] == "hi there"


@pytest.mark.asyncio
async def test_session_isolation(tmp_path):
    cm1 = JsonlMessageHistory(
        conversation_id="shared_conv",
        agent_id="a-1",
        initial_query="task 1",
        session_id="session_1",
        context_file=str(tmp_path / "s1.jsonl"),
    )
    await cm1.append({"role": "assistant", "content": "result from task 1"})

    cm2 = JsonlMessageHistory(
        conversation_id="shared_conv",
        agent_id="a-1",
        initial_query="task 2",
        session_id="session_2",
        context_file=str(tmp_path / "s2.jsonl"),
    )
    ctx2 = await cm2.load()
    assert len(ctx2) == 1
    assert ctx2[0]["content"] == "task 2"
    assert not any("task 1" in str(msg.get("content", "")) for msg in ctx2)


@pytest.mark.asyncio
async def test_legacy_identity_is_removed_without_losing_history(tmp_path):
    manager = JsonlMessageHistory(
        conversation_id="prompt-conv",
        agent_id="a-prompt",
        initial_query="",
        context_file=str(tmp_path / "legacy.jsonl"),
    )
    legacy = [
        {"role": "system", "content": "已经过期的身份"},
        {"role": "user", "content": "原始任务"},
        {"role": "assistant", "content": "已完成一部分"},
        {
            "role": "system",
            "content": "[Supervisor] 保留这条建议",
        },
        {
            "role": "system",
            "content": "[Context compact] 保留这条梗概",
        },
    ]
    with open(manager.context_file, "w", encoding="utf-8") as stream:
        json.dump(legacy, stream, ensure_ascii=False)

    migrated = await manager.load()
    assert migrated == legacy[1:]
    assert read_context_file(manager.context_file) == legacy[1:]

    messages = await manager.build_messages(
        identity_messages=[{"role": "system", "content": "当前身份"}]
    )
    assert messages[0] == {"role": "system", "content": "当前身份"}
    assert not any("已经过期的身份" in str(msg.get("content")) for msg in messages)
    assert any("已完成一部分" in str(msg.get("content")) for msg in messages)


def test_repair_tool_pairing_adds_synthetic_response():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
        },
    ]
    repaired = repair_tool_pairing(messages)
    assert repaired[-1]["role"] == "tool"
    assert repaired[-1]["tool_call_id"] == "call_1"


def test_build_llm_messages_skips_empty_assistant():
    messages = build_llm_messages(
        history=[{"role": "assistant", "content": ""}],
        identity_messages=[{"role": "system", "content": "identity"}],
    )
    assert messages == [{"role": "system", "content": "identity"}]
