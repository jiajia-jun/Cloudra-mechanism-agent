"""Event-sourced notices: dedup emission, restore projection, context.inject."""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.schemas import Command
from tests.notice_support import commit_notices


def _attached() -> tuple[NoticeManager, EventLog]:
    log = EventLog(strict=True)
    notices = NoticeManager()
    notices.attach(log, lambda session_id: "prj")
    return notices, log


def _types(log: EventLog) -> list[str]:
    return [e.type for e in log]


def test_pin_emits_only_on_change():
    notices, log = _attached()
    notices.pin("s1", "goal", "G")
    notices.pin("s1", "goal", "G")  # identical re-pin: stage-style no-op
    notices.pin("s1", "goal", "G2")
    assert _types(log) == ["context.pin_set", "context.pin_set"]
    assert log.get([e for e in log][-1].event_id).data["content"] == "G2"


def test_unpin_emits_only_when_key_existed():
    notices, log = _attached()
    notices.unpin("s1", "ghost")
    assert _types(log) == []
    notices.pin("s1", "goal", "G")
    notices.unpin("s1", "goal")
    assert _types(log) == ["context.pin_set", "context.pin_cleared"]


def test_push_emits_injected_event():
    notices, log = _attached()
    notices.push("s1", "hint")
    notices.push("s1", "")  # empty content: no event, no queue
    assert _types(log) == ["context.injected"]
    assert [m["content"] for m in notices.collect_batch("s1", fresh=False)] == ["hint"]


def test_unattached_manager_stays_silent():
    log_notice = NoticeManager()
    log_notice.pin("s1", "goal", "G")
    log_notice.push("s1", "hint")
    assert [m["content"] for m in log_notice.collect_batch("s1", fresh=True)] == [
        "G",
        "hint",
    ]


def test_restore_rebuilds_pins_and_unconsumed_pushes():
    """新契约（Task 3）：不丢失优先——未消费（从未进入上下文）的 push
    随事件重放保持 pending；已消费的不重现。游标由
    context.appended 事件恢复。"""
    notices, log = _attached()
    notices.pin("s1", "goal", "G")
    notices.pin("s1", "dag", "D")
    notices.unpin("s1", "goal")
    notices.push("s1", "consumed-push")
    notices.collect_batch("s1", fresh=True)
    commit_notices(notices, "s1")
    notices.push("s1", "never-consumed")

    restored = NoticeManager()
    restored.attach(log, lambda session_id: "prj")
    restored.restore_from(log)
    assert [m["content"] for m in restored.collect_batch("s1", fresh=True)] == [
        "D",
        "never-consumed",
    ]
    commit_notices(restored, "s1")
    # 消费游标随 context.appended 事件落地，重启后不重复
    assert restored.collect_batch("s1", fresh=False) == []


async def _setup_core() -> tuple[RuntimeCore, CommandBus, object]:
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type="project.create", payload={"name": "inject"}))
    project = next(iter(core.projects.values()))
    result = await bus.execute(
        Command(
            type="agent.spawn",
            target={"project_id": project.id},
            payload={"role_id": "coordinator"},
        )
    )
    return core, bus, result.data


@pytest.mark.asyncio
async def test_context_inject_command_roundtrip():
    core, bus, agent = await _setup_core()
    await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": agent.id},
            payload={"kind": "pin", "key": "library", "content": "pinned hint"},
        )
    )
    await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": agent.id},
            payload={"kind": "push", "content": "one-shot hint"},
        )
    )
    assert [m["content"] for m in core.notices.collect_batch(agent.id, fresh=True)] == [
        "pinned hint",
        "one-shot hint",
    ]
    commit_notices(core.notices, agent.id)
    types = [e.type for e in core.event_log if e.session_id == agent.id]
    assert "context.pin_set" in types and "context.injected" in types

    await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": agent.id},
            payload={"kind": "unpin", "key": "library"},
        )
    )
    # unpin 是增量变更：撤销说明按顺序追加
    batch = core.notices.collect_batch(agent.id, fresh=False)
    assert len(batch) == 1
    assert batch[0]["content"].startswith("[Context notice retracted: library]")
    commit_notices(core.notices, agent.id)
    assert core.notices.collect_batch(agent.id, fresh=True) == []


@pytest.mark.asyncio
async def test_context_inject_validation():
    core, bus, agent = await _setup_core()
    missing_key = await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": agent.id},
            payload={"kind": "pin", "content": "x"},
        )
    )
    assert missing_key.accepted is False
    bad_kind = await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": agent.id},
            payload={"kind": "wat", "content": "x"},
        )
    )
    assert bad_kind.accepted is False
    unknown_agent = await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": "as_nope"},
            payload={"kind": "push", "content": "x"},
        )
    )
    assert unknown_agent.accepted is False


@pytest.mark.asyncio
async def test_pins_survive_restore():
    core, bus, agent = await _setup_core()
    await bus.execute(
        Command(
            type="context.inject",
            target={"session_id": agent.id},
            payload={"kind": "pin", "key": "library", "content": "durable hint"},
        )
    )
    # Simulate a process restart: fresh manager over the same event log.
    revived = NoticeManager()
    revived.restore_from(core.event_log)
    assert [m["content"] for m in revived.collect_batch(agent.id, fresh=True)] == [
        "durable hint"
    ]


def test_inject_endpoint():
    from fastapi.testclient import TestClient

    from cloudra.runtime_v2.schemas import AgentSession, Project
    from cloudra.services.api_v2 import create_v2_app

    core = RuntimeCore(strict_events=True)
    project = Project(id="prj_1", name="demo")
    agent = AgentSession(
        id="as_1", project_id="prj_1", role_id="coordinator", display_name="Coordinator"
    )
    core.projects[project.id] = project
    core.agents[agent.id] = agent
    client = TestClient(create_v2_app(core))

    response = client.post(
        "/api/v2/agents/as_1/context/inject",
        json={"kind": "pin", "key": "library", "content": "via http"},
    )
    assert response.status_code == 200
    assert [m["content"] for m in core.notices.collect_batch("as_1", fresh=True)] == [
        "via http"
    ]
    assert any(e.type == "context.pin_set" for e in core.event_log)

    assert client.post(
        "/api/v2/agents/as_nope/context/inject", json={"kind": "push", "content": "x"}
    ).status_code == 404
