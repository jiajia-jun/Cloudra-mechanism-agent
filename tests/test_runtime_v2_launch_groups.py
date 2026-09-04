"""Task 10: launch group concurrency tests."""

import asyncio

import pytest

from cloudra.runtime_v2.launch_groups import LaunchGroupManager
from cloudra.runtime_v2.schemas import AgentState


class FakeChild:
    def __init__(self, item_id: str):
        self.id = f"as_{item_id}"
        self.state = AgentState.RUNNING

    async def finish_soon(self, delay: float):
        await asyncio.sleep(delay)
        self.state = AgentState.SUCCEEDED


@pytest.mark.asyncio
async def test_max_concurrency_covers_child_lifetime():
    active = 0
    peak = 0
    started = []

    async def spawner(query):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        started.append(query)
        child = FakeChild(query)
        asyncio.create_task(child.finish_soon(0.05))
        # Yield so the child can finish before this spawner returns.
        while child.state is AgentState.RUNNING:
            await asyncio.sleep(0.01)
        active -= 1
        return child

    manager = LaunchGroupManager(spawner=spawner)
    group = manager.create(
        group_id="grp_1",
        parent_session_id="parent",
        items=[(f"i{i}", f"q{i}") for i in range(10)],
        max_concurrency=2,
    )
    assert group.pending_count == 10
    for _ in range(100):
        if group.state == "finished":
            break
        await asyncio.sleep(0.01)
    assert group.state == "finished"
    assert peak <= 2
    assert len(started) == 10
    assert all(item.state == "succeeded" for item in group.items)
    assert group.summary()["pending_count"] == 0
