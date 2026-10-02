"""Prepare one TS path, revise through resume, inspect without mutation."""
from typing import Any

from pydantic import ConfigDict, Field, field_validator

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.services.ts_pipeline_store import TsRevisionReceipt
from cloudra.tools.core.ts_inputs import TsInput, TsResumeRequest, normalize_ts_input_atoms
from cloudra.tools.core.ts_process import TsProcessRecord, TsStartRequest, resume, start
from cloudra.tools.core.ts_state_view import TsProcessView, build_process_view, inspect_process


class TsPrepare_input_schema(input_schema):
    model_config = ConfigDict(extra='forbid')
    input: TsInput = Field(description='Scientific inputs grouped by reaction, conformers, guess, ts_optimization, verification and execution. Each calculation has its own explicit method. Structure atom references are 1-based; scan coordinates use its engine numbering (ORCA 0-based, Gaussian 1-based).')
    request_key: str = Field(min_length=1, description='Stable prepare request key; reuse the same key when replaying this request.')
    workspace_dir: str | None = None

    @field_validator('request_key')
    @classmethod
    def stable_key(cls, value):
        if not value.strip():
            raise ValueError('nonblank request_key required for prepare replay')
        return value


class TsResume_input_schema(TsResumeRequest, input_schema):
    run_id: str = Field(min_length=1)
    workspace_dir: str | None = None


class TsInspect_input_schema(input_schema):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(min_length=1)
    workspace_dir: str | None = None


class TsProcess_output_schema(TsProcessView, output_schema):
    is_success: bool = Field(default=True, description="Tool call succeeded; this is not scientific validation. Only result.verified=true means the TS passed the recorded scientific checks.")
    receipt: TsRevisionReceipt | None = None


def _resolve_workspace(tool: Tool, value: str | None) -> str:
    if value:
        return resolve_tool_path(tool, value)
    root = getattr(getattr(tool, 'subagent', None), 'working_directory', None)
    if not root:
        raise ValueError('no workspace_dir or Agent working directory is bound')
    return str(root)


def _to_output(record, *, can_write=True):
    from cloudra.services.ts_pipeline_context import pipeline_database
    if record.pipeline_id:
        view = inspect_process(pipeline_database(), project_id=record.owner_conversation_id,
                               run_id=record.run_id, workspace_dir=record.workspace_dir, can_write=can_write)
    else:
        view = build_process_view(record.model_dump(mode='json'), [], can_write=can_write)
    return TsProcess_output_schema(**view.model_dump())


def _read_resume_record(db, workspace, run_id, project):
    from cloudra.services.ts_pipeline_store import read_process_snapshot
    state, jobs = read_process_snapshot(db, project_id=project, run_id=run_id, workspace_dir=workspace)
    if state.get('format_version') != 3:
        raise ValueError('Unsupported TS input format; existing compute jobs remain intact.')
    record = TsProcessRecord.model_validate(state)
    states = {job['job_id']: job['state'] for job in jobs}
    for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]:
        if step.job_id in states:
            step.state = states[step.job_id]
    return record


class TsPrepare(Tool):
    tool_id: str = 't-59'
    tool_name: str = 'ts_prepare'
    tool_description: str = 'Create one durable TS path with grouped explicit scientific inputs. Successful jobs automatically advance. Missing inputs or failed evidence stop at an inspectable checkpoint. Use ts_resume for future revisions on this run; ts_inspect reads state without advancing.'
    input_schema: Any = TsPrepare_input_schema
    output_schema: Any = TsProcess_output_schema

    def is_write(self):
        return True

    async def tool_call(self, user_input: TsPrepare_input_schema, session: Session):
        import asyncio
        try:
            from cloudra.tools.core.permission_model import Permission
            if not self.subagent.permission_all() & Permission.WRITE:
                raise ValueError('TS mutation requires producer write permission')
            workspace = _resolve_workspace(self, user_input.workspace_dir)
            request = TsStartRequest(input=normalize_ts_input_atoms(user_input.input, atom_tables={}),
                workspace_dir=workspace, request_key=user_input.request_key,
                owner_conversation_id=self.subagent.conversation_id,
                owner_session_id=session.id if session else None)
            record = await asyncio.to_thread(start, request)
            return await asyncio.to_thread(_to_output, record)
        except (ValueError, OSError) as exc:
            return TsProcess_output_schema(is_success=False, message=f'ts_prepare: {exc}')


class TsResume(Tool):
    tool_id: str = 't-60'
    tool_name: str = 'ts_resume'
    tool_description: str = 'Revise input groups on the existing TS path. Omitted fields remain; optional null clears; lists, methods and typed sources replace. Requires reason, expected_revision and stable request_key; failures require relevant recovery evidence. Active jobs prevent revisions. Use ts_inspect for reads.'
    input_schema: Any = TsResume_input_schema
    output_schema: Any = TsProcess_output_schema

    def is_write(self):
        return True

    async def tool_call(self, user_input: TsResume_input_schema, session: Session):
        import asyncio

        from cloudra.services.ts_pipeline_context import pipeline_database
        from cloudra.services.ts_pipeline_store import get_revision_receipt
        try:
            from cloudra.tools.core.permission_model import Permission
            if not self.subagent.permission_all() & Permission.WRITE:
                raise ValueError('TS mutation requires producer write permission')
            workspace = _resolve_workspace(self, user_input.workspace_dir)
            record = await asyncio.to_thread(_read_resume_record, pipeline_database(), workspace, user_input.run_id, self.subagent.conversation_id)
            if (self.subagent.conversation_id, session.id if session else None) != (record.owner_conversation_id, record.owner_session_id):
                raise ValueError('TS process belongs to a different project or owner')
            request = TsResumeRequest.model_validate(user_input.model_dump(exclude={'run_id', 'workspace_dir'}, exclude_unset=True))
            request.changes = normalize_ts_input_atoms(request.changes, atom_tables={})
            record = await asyncio.to_thread(resume, record, request)
            out = await asyncio.to_thread(_to_output, record)
            out.receipt = await asyncio.to_thread(get_revision_receipt, pipeline_database(), process_id=record.pipeline_id, request_key=request.request_key)
            return out
        except (ValueError, OSError) as exc:
            return TsProcess_output_schema(is_success=False, run_id=user_input.run_id, message=f'ts_resume: {exc}')


class TsInspect(Tool):
    tool_id: str = 't-ts-inspect'
    tool_name: str = 'ts_inspect'
    tool_description: str = 'Read authoritative TS state, jobs, methods, evidence and missing inputs. Does not advance, retry or change a process. Same-project read-only reviewers may inspect another agent’s run.'
    input_schema: Any = TsInspect_input_schema
    output_schema: Any = TsProcess_output_schema

    def is_read(self):
        return True

    async def tool_call(self, user_input: TsInspect_input_schema, session: Session):
        import asyncio

        from cloudra.services.ts_pipeline_context import pipeline_database
        from cloudra.tools.core.permission_model import Permission
        try:
            workspace = _resolve_workspace(self, user_input.workspace_dir)
            permissions = self.subagent.permission_all()
            if not permissions & Permission.READ:
                raise ValueError('TS inspection requires read permission')
            view = await asyncio.to_thread(inspect_process, pipeline_database(), project_id=self.subagent.conversation_id,
                run_id=user_input.run_id, workspace_dir=workspace, can_write=bool(permissions & Permission.WRITE), owner_id=session.id if session else None)
            return TsProcess_output_schema(**view.model_dump())
        except (ValueError, OSError) as exc:
            return TsProcess_output_schema(is_success=False, run_id=user_input.run_id, message=f'ts_inspect: {exc}')


def get_class():
    return TsPrepare
