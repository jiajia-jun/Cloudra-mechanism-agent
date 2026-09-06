"""Orchestration mode single source of truth (C1).

The project-level ``ProjectSettings.orchestration_mode`` is the inheritable
default every agent picks up at spawn; the agent-level value is the resolved
effective mode (explicit spawn/patch overrides win).  Mid-session
``agent.settings_update`` transitions into dag_guided fire the same
ReconcileSupervision effect that ``project.update`` already had, and startup
reconcile also covers standard-mode projects that contain guided agents.
"""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import PipelineContext
from cloudra.runtime_v2.policies.dag_stage import DagPolicyStage
from cloudra.runtime_v2.schemas import Command, OrchestrationMode
from cloudra.runtime_v2.tool_catalog import guest_tool_names


async def _project(core: RuntimeCore, mode: str | None = None):
    payload: dict = {"name": "modes"}
    if mode is not None:
        payload["settings"] = {"orchestration_mode": mode}
    await CommandBus(core).execute(Command(type="project.create", payload=payload))
    return next(iter(core.projects.values()))


async def _spawn(core: RuntimeCore, project, settings: dict | None = None):
    payload: dict = {"role_id": "coordinator"}
    if settings:
        payload["settings"] = settings
    result = await CommandBus(core).execute(
        Command(type="agent.spawn", target={"project_id": project.id}, payload=payload)
    )
    return result.data


def _ctx(agent) -> PipelineContext:
    return PipelineContext(
        agent=agent,
        run_id="run_mode",
        settings_snapshot=agent.settings,
        capabilities=agent.capabilities,
        inbox_messages=[],
        emit=lambda *a, **k: None,
        workspace_dir=None,
    )


@pytest.mark.asyncio
async def test_project_mode_is_inherited_by_agents_without_override():
    """API-only client sets just the project field: spawned agents must come
    out guided (no silent split-brain)."""
    core = RuntimeCore(strict_events=True)
    project = await _project(core, "dag_guided")
    agent = await _spawn(core, project)
    assert agent.settings.orchestration_mode is OrchestrationMode.DAG_GUIDED


@pytest.mark.asyncio
async def test_inherited_guided_activates_dag_stage_and_tool_projection():
    core = RuntimeCore(strict_events=True)
    project = await _project(core, "dag_guided")
    agent = await _spawn(core, project)
    controller = await DagPolicyStage()._controller(_ctx(agent))
    assert controller is not None, "dag policy stage must activate for an inherited guided agent"
    names = guest_tool_names(
        ["dag_view", "log_parser"], orchestration_mode=agent.settings.orchestration_mode
    )
    assert "dag_view" in names, "dag_* tools must project for an inherited guided agent"


@pytest.mark.asyncio
async def test_explicit_agent_override_beats_project_default():
    """Explicit standard override under a guided project wins, and the dag
    stage stays off for that agent."""
    core = RuntimeCore(strict_events=True)
    project = await _project(core, "dag_guided")
    agent = await _spawn(core, project, settings={"orchestration_mode": "standard"})
    assert agent.settings.orchestration_mode is OrchestrationMode.STANDARD
    assert await DagPolicyStage()._controller(_ctx(agent)) is None
    names = guest_tool_names(
        ["dag_view", "log_parser"], orchestration_mode=agent.settings.orchestration_mode
    )
    assert "dag_view" not in names


@pytest.mark.asyncio
async def test_explicit_guided_override_under_standard_project():
    core = RuntimeCore(strict_events=True)
    project = await _project(core)  # standard
    agent = await _spawn(core, project, settings={"orchestration_mode": "dag_guided"})
    assert agent.settings.orchestration_mode is OrchestrationMode.DAG_GUIDED


@pytest.mark.asyncio
async def test_agent_settings_update_entering_guided_triggers_reconcile(monkeypatch):
    """Mid-session switch standard -> guided must fire the same
    ReconcileSupervision effect project.update already had; guided -> guided
    re-patch is not a migration edge and must not re-fire."""
    calls: list[str] = []

    async def fake_reconcile(core, project_id):
        calls.append(project_id)

    monkeypatch.setattr(
        "cloudra.runtime_v2.supervision.reconcile_supervision", fake_reconcile
    )
    core = RuntimeCore(strict_events=True)
    project = await _project(core)  # standard
    agent = await _spawn(core, project)
    assert agent.settings.orchestration_mode is OrchestrationMode.STANDARD
    bus = CommandBus(core)
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"orchestration_mode": "dag_guided"},
        )
    )
    assert agent.settings.orchestration_mode is OrchestrationMode.DAG_GUIDED
    assert calls == [project.id]
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"orchestration_mode": "dag_guided"},
        )
    )
    assert calls == [project.id], "guided -> guided re-patch must not re-fire reconcile"
    await bus.execute(
        Command(
            type="agent.settings_update",
            target={"session_id": agent.id},
            payload={"orchestration_mode": "dag_record"},
        )
    )
    assert calls == [project.id], "entering dag_record does not consume the supervision mailbox"


@pytest.mark.asyncio
async def test_startup_reconcile_covers_guided_agents_in_standard_project(monkeypatch):
    """A standard-mode project may still hold agents with an explicit guided
    override; their persisted supervision todos need the startup reconcile
    just like a guided project's."""
    from cloudra.services.api_v2.app import create_v2_app

    calls: list[str] = []

    async def fake_reconcile(core, project_id):
        calls.append(project_id)

    monkeypatch.setattr(
        "cloudra.runtime_v2.supervision.reconcile_supervision", fake_reconcile
    )
    core = RuntimeCore(strict_events=True)
    project = await _project(core)  # standard
    await _spawn(core, project, settings={"orchestration_mode": "dag_guided"})
    app = create_v2_app(core)
    async with app.router.lifespan_context(app):
        pass
    assert project.id in calls
