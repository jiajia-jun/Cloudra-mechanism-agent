"""Stop authority comes from current-run user events, never model fields."""

import asyncio
from datetime import timedelta

import pytest
from pydantic import ValidationError

from cloudra.runtime_v2.commands import CommandBus, _cancel_agent_drafts
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.policies.base import PipelineContext
from cloudra.runtime_v2.policies.dag_stage import DagPolicyStage
from cloudra.runtime_v2.schemas import Command
from cloudra.tools.Stoptool.stop_tool import StopTool_input_schema


async def _current_run(tmp_path):
    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    project = (await bus.execute(Command(type="project.create", payload={
        "name": "stop authority", "workspace_dir": str(tmp_path),
        "settings": {"orchestration_mode": "dag_record"},
    }))).data
    agent = (await bus.execute(Command(type="agent.spawn", target={"project_id": project.id},
        payload={"role_id": "coordinator"}))).data
    await core.agent_host.start_run(agent)
    ctx = PipelineContext(agent=agent, run_id=agent.current_run.run_id,
        settings_snapshot=agent.settings.model_copy(deep=True), capabilities=agent.capabilities,
        inbox_messages=[], emit=lambda *_args, **_kwargs: None, workspace_dir=str(tmp_path),
        notices=core.notices)
    return core, agent, DagPolicyStage(core), ctx


async def _cancel_source(core, agent, *, actor="user", **overrides):
    # Use the real command's cancellation payload; leave the run alive until its
    # completion audit, just as the persisted request precedes cancellation.
    draft = _cancel_agent_drafts(agent, actor=actor, message="stop", cause="direct")[0]
    fields = dict(stream=draft.stream, project_id=draft.project_id,
        session_id=draft.session_id, run_id=draft.run_id, data=draft.data)
    fields.update(overrides)
    return await asyncio.to_thread(core.event_log.append, draft.type, **fields)


@pytest.mark.parametrize("field", ["approval_id", "user_stop_event_id"])
def test_stop_rejects_model_supplied_authority(field):
    assert field not in StopTool_input_schema.model_json_schema()["properties"]
    with pytest.raises(ValidationError):
        StopTool_input_schema.model_validate({"delivery_disposition": "user_terminated", field: "fake"})


@pytest.mark.asyncio
async def test_current_user_cancel_is_found_without_model_event_id(tmp_path):
    core, agent, stage, ctx = await _current_run(tmp_path)
    await _cancel_source(core, agent)
    gate = await stage.audit_run_end(ctx, explicit_stop=True,
        stop_arguments={"delivery_disposition": "user_terminated"})
    assert gate.action == "allow_final"
    assert gate.basis == "user_terminated"
    assert gate.report is None


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["system", "coordinator", "model", "User"])
async def test_model_or_system_cancellation_is_not_user_authority(tmp_path, actor):
    core, agent, stage, ctx = await _current_run(tmp_path)
    await _cancel_source(core, agent, actor=actor)
    gate = await stage.audit_run_end(ctx, explicit_stop=True,
        stop_arguments={"delivery_disposition": "user_terminated"})
    assert gate.action == "continue_work"
    assert gate.basis != "user_terminated"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["other_session", "other_project", "old_run"])
async def test_cancel_authority_is_bound_to_current_session_project_and_run(tmp_path, scope):
    core, agent, stage, ctx = await _current_run(tmp_path)
    field, value = {"other_session": ("session_id", "as_other"),
        "other_project": ("project_id", "prj_other"), "old_run": ("run_id", "run_old")}[scope]
    # Even a freshly recorded event cannot authorize a different run/session.
    await _cancel_source(core, agent, **{field: value})
    gate = await stage.audit_run_end(ctx, explicit_stop=True,
        stop_arguments={"delivery_disposition": "user_terminated"})
    assert gate.action == "continue_work"
    assert gate.basis != "user_terminated"


@pytest.mark.asyncio
async def test_previous_cancel_cannot_authorize_next_run_even_without_run_id(tmp_path):
    core, agent, stage, ctx = await _current_run(tmp_path)
    event = await _cancel_source(core, agent, run_id=None)
    event.created_at = agent.current_run.started_at - timedelta(seconds=1)
    gate = await stage.audit_run_end(ctx, explicit_stop=True,
        stop_arguments={"delivery_disposition": "user_terminated"})
    assert gate.action == "continue_work"


@pytest.mark.asyncio
async def test_untrusted_later_notice_does_not_hide_current_user_cancel(tmp_path):
    core, agent, stage, ctx = await _current_run(tmp_path)
    await _cancel_source(core, agent)
    await _cancel_source(core, agent, actor="model")
    gate = await stage.audit_run_end(ctx, explicit_stop=True,
        stop_arguments={"delivery_disposition": "user_terminated"})
    assert gate.action == "allow_final"
    assert gate.basis == "user_terminated"


@pytest.mark.asyncio
async def test_model_event_id_cannot_override_current_run_lookup(tmp_path):
    core, agent, stage, ctx = await _current_run(tmp_path)
    wrong_session = await _cancel_source(core, agent, session_id="as_other")
    gate = await stage.audit_run_end(ctx, explicit_stop=True, stop_arguments={
        "delivery_disposition": "user_terminated", "user_stop_event_id": wrong_session.event_id,
    })
    assert gate.action == "continue_work"
