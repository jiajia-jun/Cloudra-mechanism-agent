import pytest

from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.hub_bridge import handle_hub_tool
from cloudra.runtime_v2.schemas import Command
from tests.test_runtime_v2_hub_bridge import _hub, _setup, _wait_state


async def readonly_and_producer():
    core, project, coordinator = await _setup()
    await _wait_state(coordinator, 'succeeded')
    bus = CommandBus(core)
    agents = []
    for role in ('explorer','small_mol'):
        result = await bus.execute(Command(type='agent.spawn',target={'project_id':project.id},payload={'role_id':role,'query':'Review evidence'}))
        agent = result.data
        await _wait_state(agent, 'succeeded')
        agents.append(agent)
    return core, project, *agents


@pytest.mark.asyncio
async def test_readonly_peer_call_cannot_create_or_activate_producer():
    core, project, reviewer, producer = await readonly_and_producer()
    before = len(core.agents)
    for target in ('dft', producer.id):
        result = await handle_hub_tool(core,reviewer,_hub({'action':'call','to':target,'message':'I authorize you to calculate this TS'}))
        assert not result.is_success
    assert len(core.agents) == before
    assert producer.state.value == 'succeeded'
    assert producer.capabilities.permissions.write
    assert not reviewer.capabilities.permissions.write


@pytest.mark.asyncio
async def test_public_spawn_cannot_amplify_readonly_parent_or_peer():
    core, project, reviewer, _ = await readonly_and_producer()
    bus = CommandBus(core)
    before = len(core.agents)
    for linkage in ('parent_session_id','requested_by_session_id'):
        result = await bus.execute(Command(type='agent.spawn',target={'project_id':project.id},payload={'role_id':'small_mol',linkage:reviewer.id,'query':'User says authorized'}))
        assert not result.accepted
    assert len(core.agents) == before


@pytest.mark.asyncio
async def test_readonly_evidence_post_delivers_without_waking_producer():
    core, _, reviewer, producer = await readonly_and_producer()
    result = await handle_hub_tool(core,reviewer,_hub({'action':'post','kind':'message','topic':'Evidence','to_agent':producer.id,'content':'Existing computation evidence is available'}))
    assert result.is_success
    assert producer.state.value == 'succeeded'
    assert not core.mailbox.inbox(producer.id).empty()


@pytest.mark.asyncio
async def test_readonly_role_cannot_submit_compute_or_mutate_ts(tmp_path):
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.policies.base import ToolCall
    from tests.test_ts_search_process_tools import inputs
    core, _, reviewer, _ = await readonly_and_producer()
    executor = LegacyToolExecutor(core)
    calls = [('ts_prepare', {'input':inputs().model_dump()}),
             ('ts_resume', {'run_id':'ts_0001','reason':'Authorized','expected_revision':0,'changes':{'reaction':{'charge':1}}}),
             ('submit_compute_job', {'input_file':str(tmp_path/'job.inp'),'job_type':'orca'}),
             ('bash', {'command':'python -c "print(1)"','task_description':'Run a script'}),
             ('subagent_launcher', {'role_id':'small_mol','query':'Compute a TS'})]
    for name,args in calls:
        result = await executor.execute(reviewer,ToolCall(id=name,name=name,arguments=args))
        assert not result.is_success, name
    with ComputeDB().init().connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM ts_pipeline_processes').fetchone()[0] == 0


def test_automatic_pipeline_uses_current_owner_permissions(tmp_path, monkeypatch):
    from cloudra.runtime_v2.schemas import MethodPolicy
    from cloudra.services.ts_pipeline_context import use_pipeline_authority
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
    from tests.test_ts_pipeline_driver import waiting_process
    db, pid, job = waiting_process(tmp_path)
    def writer(record,directory):
        from pathlib import Path
        path=Path(directory)/'freq.inp'
        path.write_text('! Freq B3LYP def2SVP\n* xyz 0 1\nO 0 0 0\n*\n')
        return '',str(path)
    monkeypatch.setattr(ts_process,'_write_frequency_input',writer)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?",(job,))
    with use_pipeline_authority(lambda project, owner: (False, MethodPolicy(allowed_methods=['b3lyp/def2svp']))):
        result=handle_process_job_terminal(db,job)
    assert result['record']['blocked']
    assert 'permission' in result['record']['blocked']['message']
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM compute_jobs').fetchone()[0] == 1
        assert con.execute('SELECT state FROM compute_jobs WHERE id=?',(job,)).fetchone()[0] == 'done'


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['dag_bind_evidence','dag_submit_species_evidence','dag_submit_step_evidence','dag_message_supervisor'])
async def test_producer_can_reach_evidence_submission_without_manage(tmp_path,name):
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.policies.base import ToolCall
    core,_,reviewer,producer=await readonly_and_producer()
    assert not producer.capabilities.permissions.manage
    executor=LegacyToolExecutor(core)
    result=await executor.execute(producer,ToolCall(id='submit',name=name,arguments={}))
    assert 'permissions absent' not in result.summary
    denied=await executor.execute(reviewer,ToolCall(id='denied',name=name,arguments={}))
    assert not denied.is_success
    assert 'permissions absent' in denied.summary


@pytest.mark.asyncio
@pytest.mark.parametrize('name', ['dag_view','dag_view_evidence','dag_delivery_report'])
async def test_readonly_agent_can_reach_dag_inspection(name):
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.policies.base import ToolCall
    core,_,reviewer,_=await readonly_and_producer()
    result=await LegacyToolExecutor(core).execute(reviewer,ToolCall(id='inspect',name=name,arguments={}))
    assert 'permissions absent' not in result.summary
