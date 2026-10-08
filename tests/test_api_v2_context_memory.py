"""Context estimates skip unrelated large raw result payloads."""

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.effects import EventDraft
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import AgentSession, Project
from cloudra.services.api_v2 import create_v2_app


@pytest.mark.asyncio
async def test_context_stats_do_not_decode_raw_tool_outputs(tmp_path, monkeypatch):
    core = RuntimeCore(strict_events=True)
    core.projects["p"] = Project(id="p", name="context")
    core.agents["a"] = AgentSession(id="a", project_id="p", role_id="explorer", display_name="reader")
    core.store = RuntimeStore(tmp_path / "runtime.db")
    for kind, data in [
        ("agent.message_emitted", {"content": "Hello"}),
        ("tool.result_recorded", {"result": {"data": "x" * (2 * 1024 * 1024)}}),
        ("tool.finished", {"result_summary": "done"}),
        ("llm.completed", {"usage": {"prompt_tokens": 11}}),
    ]:
        await core.event_writer.commit(EventDraft(kind, "agent", "p", session_id="a", data=data))
    decoded_raw_results = []
    original = RuntimeStore._envelope

    def decode(row):
        if row[7] == "tool.result_recorded":
            decoded_raw_results.append(row[0])
        return original(row)

    monkeypatch.setattr(RuntimeStore, "_envelope", staticmethod(decode))
    async with AsyncClient(
        transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v2/agents/a/context")
    assert response.status_code == 200
    assert response.json()["messages"] == 2
    assert response.json()["last_prompt_tokens"] == 11
    assert not decoded_raw_results, "raw outputs should never be loaded for text-only context estimates"
    await core.aclose()
