"""Message receipts identify the persisted message, including when waking an Agent."""

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.runtime_v2.schemas import AgentSession, Project
from cloudra.services.api_v2 import create_v2_app


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["running", "succeeded"])
async def test_message_receipt_identifies_message_before_wake_events(tmp_path, state):
    core = RuntimeCore(strict_events=True)
    core.store = RuntimeStore(tmp_path / "runtime.db")
    core.projects["p"] = Project(id="p", name="receipts")
    core.agents["a"] = AgentSession(
        id="a", project_id="p", role_id="explorer", display_name="receiver", state=state,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_v2_app(core)), base_url="http://testserver",
        ) as client:
            response = await client.post("/api/v2/agents/a/messages", json={"content": "hello"})
            assert response.status_code == 200
            receipt = response.json()
            assert receipt["accepted"] is True
            event = await client.get(f"/api/v2/agents/a/events/{receipt['event_id']}")
            assert event.status_code == 200
            assert event.json()["type"] == "agent.message_injected"
            assert event.json()["data"]["content"] == "hello"
    finally:
        await core.aclose()
