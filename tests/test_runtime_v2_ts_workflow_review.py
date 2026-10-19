"""TS intent warnings and semantic YOLO review share the real call boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cloudra.infra.yolo_guard import YoloGuard
from cloudra.runtime_v2.notices import NoticeManager
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall, ToolResult
from cloudra.runtime_v2.policies.guidance import GuidanceStage
from cloudra.runtime_v2.schemas import AgentCapabilities, PermissionSet, RuntimeSettings


def _context(tmp_path, *, yolo=False, notices=None):
    return PipelineContext(
        agent=SimpleNamespace(id='owner', project_id='project', role_id='small_mol',
                              current_task='Verify the reaction through the TS process'),
        run_id='run', settings_snapshot=RuntimeSettings(yolo=yolo),
        capabilities=AgentCapabilities(permissions=PermissionSet(), tools=['*']),
        inbox_messages=[], emit=lambda *_args, **_kwargs: None,
        workspace_dir=str(tmp_path), notices=notices,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['write', 'edit', 'bash', 'shell'])
async def test_ts_intent_warns_at_alternate_entry_without_banning_it(tmp_path, entry):
    (tmp_path / 'ts.inp').write_text('! HF STO-3G Opt\n')
    (tmp_path / 'run.sh').write_text('orca ts.inp\n')
    arguments = {
        'write': {'path': 'ts.inp', 'content': '! HF STO-3G OptTS\n'},
        'edit': {'path': 'ts.inp', 'edits': [{'old_string': 'Opt', 'new_string': 'OptTS'}]},
        'bash': {'command': 'orca ts.inp'},
        'shell': {'input_file': 'run.sh', 'job_type': 'shell'},
    }[entry]
    if entry in {'bash', 'shell'}:
        (tmp_path / 'ts.inp').write_text('! HF STO-3G OptTS\n')
    notices = NoticeManager()
    call = ToolCall(id='candidate', name='submit_compute_job' if entry == 'shell' else entry,
                    arguments=arguments)

    result = await GuidanceStage().before_tool(_context(tmp_path, notices=notices), call)

    assert result.outcome == 'warn'
    assert notices.pin_content('owner', 'guidance-ts-sop') is not None
    assert notices.pin_content('owner', 'guidance-ts-workflow') is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('approved', [False, True])
@pytest.mark.parametrize('engine', ['orca', 'shell'])
async def test_yolo_judges_individual_submission_instead_of_blanket_ts_ban(tmp_path, monkeypatch, approved, engine):
    (tmp_path / 'ts.inp').write_text('! HF STO-3G OptTS\n')
    (tmp_path / 'run.sh').write_text('orca ts.inp\n')
    judge = AsyncMock(return_value=(approved, 'workflow review decision'))
    monkeypatch.setattr(YoloGuard, 'judge', judge)
    notices = NoticeManager()
    ctx = _context(tmp_path, yolo=True, notices=notices)
    call = ToolCall(id='candidate', name='submit_compute_job', arguments={
        'input_file': 'run.sh' if engine == 'shell' else 'ts.inp', 'job_type': engine,
    })

    result = await GuidanceStage().before_tool(ctx, call)

    judge.assert_awaited_once()
    assert judge.call_args.args[:2] == ('submit_compute_job', call.arguments)
    assert judge.call_args.kwargs['workspace_dir'] == str(tmp_path)
    assert result.outcome == ('warn' if approved else 'block')
    assert notices.pin_content('owner', 'guidance-ts-workflow') is not None


@pytest.mark.asyncio
async def test_plain_native_optimization_does_not_gain_an_extra_yolo_review(tmp_path, monkeypatch):
    (tmp_path / 'opt.inp').write_text('! HF STO-3G Opt Freq\n')
    judge = AsyncMock()
    monkeypatch.setattr(YoloGuard, 'judge', judge)

    result = await GuidanceStage().before_tool(_context(tmp_path, yolo=True, notices=NoticeManager()),
        ToolCall(id='normal', name='submit_compute_job', arguments={'input_file': 'opt.inp', 'job_type': 'orca'}))

    assert result.outcome == 'allow'
    judge.assert_not_awaited()


@pytest.mark.asyncio
async def test_reading_ts_input_is_not_an_execution_warning(tmp_path):
    (tmp_path / 'ts.inp').write_text('! HF STO-3G OptTS\n')
    notices = NoticeManager()

    result = await GuidanceStage().before_tool(_context(tmp_path, notices=notices),
        ToolCall(id='inspect', name='bash', arguments={'command': 'cat ts.inp'}))

    assert result.outcome == 'allow'
    assert notices.pin_content('owner', 'guidance-ts-sop') is None


@pytest.mark.asyncio
async def test_existing_bash_approval_is_not_duplicated_in_guidance(tmp_path, monkeypatch):
    (tmp_path / 'ts.inp').write_text('! HF STO-3G OptTS\n')
    judge = AsyncMock()
    monkeypatch.setattr(YoloGuard, 'judge', judge)

    result = await GuidanceStage().before_tool(_context(tmp_path, yolo=True, notices=NoticeManager()),
        ToolCall(id='shell', name='bash', arguments={'command': 'orca ts.inp'}))

    assert result.outcome == 'warn'
    judge.assert_not_awaited()


@pytest.mark.asyncio
async def test_blocked_ts_process_warns_before_an_opaque_script(tmp_path):
    (tmp_path / 'diagnose.py').write_text('print("diagnostic")\n')
    notices = NoticeManager()
    stage = GuidanceStage()
    ctx = _context(tmp_path, notices=notices)
    await stage.after_tool(ctx, ToolCall(id='prepare', name='ts_prepare'), ToolResult(True, data={
        'run_id': 'ts_original', 'status': 'blocked',
        'blocked': {'stage': 'build', 'failure_class': 'missing_input', 'needs': ['conformers.reactant']},
    }))

    result = await stage.before_tool(ctx,
        ToolCall(id='script', name='bash', arguments={'command': 'python diagnose.py'}))

    assert result.outcome == 'warn'
    assert notices.pin_content('owner', 'guidance-ts-workflow') is not None
