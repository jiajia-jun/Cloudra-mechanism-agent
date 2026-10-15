"""Compaction budgets the messages actually sent to the summary model."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from cloudra.runtime_v2.compaction import (
    _COMPACT_INSTRUCTION,
    CompactSummary,
    _merge_partials,
    _summarize_validated,
    compact_context,
    estimate_messages_tokens,
    summarize_with_agent_settings,
)
from cloudra.runtime_v2.schemas import AgentSession, RuntimeSettings


def _summary(text: str = "Continue the requested calculation.") -> dict:
    return {
        "objective": {"text": text, "sources": [0]},
        "active_requests": [],
        "corrections": [],
        "constraints": [],
        "pending": [],
        "completed": [],
        "failed_attempts": [],
        "evidence": [],
        "next_actions": [],
    }


@pytest.mark.asyncio
async def test_summary_request_sends_the_output_budget_used_for_compaction(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def create_with_retry(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))]
            )

        async def aclose(self):
            pass

    monkeypatch.setattr("cloudra.infra.llm_client.LLMClient", Client)
    monkeypatch.setattr(
        "cloudra.runtime_v2.adapters.legacy_default_settings", lambda agent: agent.settings
    )
    agent = AgentSession(
        id="summary-budget",
        project_id="project",
        role_id="coordinator",
        display_name="Coordinator",
        settings=RuntimeSettings(model="summary-model", max_tokens=1536),
    )

    assert await summarize_with_agent_settings(agent, []) == "summary"
    assert captured["max_tokens"] == 1536


@pytest.mark.asyncio
async def test_segment_requests_include_system_and_message_overhead_in_budget():
    calls = []

    async def summarize(messages):
        calls.append(messages)
        return json.dumps(_summary())

    messages = [
        {"role": "tool", "content": "alpha β γ δ 化学🧪\n" * 260}
        for _ in range(2)
    ]
    _, stats = await compact_context(
        messages,
        head=[],
        notices=[],
        summarize=summarize,
        context_window=4000,
        max_output=512,
    )

    assert stats["compacted"] is True
    assert len(stats["segments"]) > 1
    assert all(estimate_messages_tokens(call) <= 2964 for call in calls)
    segment_calls = calls[: len(stats["segments"])]
    assert sum(call[1]["content"].count("🧪") for call in segment_calls) == 520


@pytest.mark.asyncio
async def test_merge_batches_budget_the_actual_serialized_array_and_system_message():
    calls = []

    async def summarize(messages):
        calls.append(messages)
        return json.dumps(_summary())

    partials = [CompactSummary.model_validate(_summary("datum " * 400)) for _ in range(8)]
    summary, _ = await _merge_partials(
        partials,
        summarize=summarize,
        trajectory_len=1,
        budget_tokens=2400,
    )

    assert summary is not None
    assert len(calls) > 1
    assert all(estimate_messages_tokens(call) <= 2400 for call in calls)


@pytest.mark.asyncio
async def test_invalid_summary_retry_preserves_source_payload_without_resending_bad_reply():
    calls = []
    invalid = _summary("bad reply " * 1500)
    invalid["active_requests"] = {"text": "Keep every request.", "sources": [0]}
    replies = [json.dumps(invalid), json.dumps(_summary())]
    payload = "preserve this instruction. " * 200

    async def summarize(messages):
        calls.append(messages)
        return replies.pop(0)

    summary = await _summarize_validated(
        summarize,
        instruction=_COMPACT_INSTRUCTION,
        payload=payload,
        trajectory_len=1,
    )

    assert summary.objective.text == "Continue the requested calculation."
    assert len(calls) == 2
    assert calls[1][1] == {"role": "user", "content": payload}
    assert not any(message["role"] == "assistant" for message in calls[1])
    assert "active_requests" in calls[1][-1]["content"]
    assert estimate_messages_tokens(calls[1]) < 2400
