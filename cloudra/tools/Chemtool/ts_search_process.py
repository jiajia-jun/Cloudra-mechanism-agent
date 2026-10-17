"""Prepare, revise, stop or inspect one durable TS path."""
from typing import Any

from pydantic import ConfigDict, Field, field_validator

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.runtime_v2.invocation_context import current_invocation_scope
from cloudra.services.ts_pipeline_store import TsRevisionReceipt
from cloudra.tools.core.ts_inputs import (
    TsInput,
    TsInputChanges,
    TsResumeRequest,
    normalize_ts_input_atoms,
)
from cloudra.tools.core.ts_process import TsProcessRecord, TsStartRequest, resume, start
from cloudra.tools.core.ts_state_view import TsProcessView, build_process_view, inspect_process


class TsPrepare_input_schema(input_schema):
    model_config = ConfigDict(extra='forbid')
    input: TsInput = Field(description='Scientific inputs grouped by reaction, calculations, conformers, guess, ts_optimization, verification and execution. Each calculation explicitly selects engine, one-token method and basis_set (empty for a method without a basis), with keywords and native settings in separate fields. A stage may supply a complete configuration or {ref: name} referring to input.calculations. Sharing a profile is explicit; stages do not inherit another stage\'s method. Structure atom references are 1-based; scan coordinates use its engine numbering (ORCA 0-based, Gaussian/xTB 1-based).')


class TsResume_input_schema(input_schema):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(min_length=1)
    changes: TsInputChanges = Field(default_factory=TsInputChanges, description='Within the same calculation, omitted fields retain existing keywords, frequency_mode, orca_blocks and end_setting; explicit empty values clear them. Changing engine, method or basis_set requires {replace: complete_configuration}; changing a named reference uses {replace: {ref: name}}. calculations profile-map omissions remain unchanged, and null removes an unused profile. A scan-coordinate-only patch need not copy calculation. Use the current atom identities/order reported in structures with each field\'s documented index base: structure/reaction references are 1-based; ORCA scan/freeze references are 0-based; Gaussian/xTB scan references are 1-based. A source patch retains omitted fields and null clears them. Explicit file paths import the current file bytes once, including an unchanged path. Proven incoming atom reorderings convert new atom declarations once within owned molecular state; source files remain unchanged.')
    reason: str = Field(min_length=1)


class TsStop_input_schema(input_schema):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(min_length=1, description='Existing TS run to stop within the current project and workspace.')
    reason: str = Field(min_length=1, description='Why this TS run should stop before further advancement.')

    @field_validator('run_id', 'reason')
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('must not be blank')
        return value


class TsInspect_input_schema(input_schema):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(min_length=1)


class TsProcess_output_schema(TsProcessView, output_schema):
    is_success: bool = Field(default=True, description="Tool call succeeded; this is not scientific validation. Only result.verified=true means the TS passed the recorded scientific checks.")
    receipt: TsRevisionReceipt | None = Field(default=None, description='Durable accepted revision receipt. Imported source hashes identify immutable snapshots. Future references use the current atom table with each field\'s documented index base. Historical QM files retain their original numbering.')


def _resolve_workspace(tool: Tool) -> str:
    root = getattr(getattr(tool, 'subagent', None), 'working_directory', None)
    if not root:
        raise ValueError('no Agent working directory is bound')
    return str(root)


def _request_key(tool_name: str) -> str:
    scope = current_invocation_scope()
    if scope is None or scope.tool_name != tool_name or not scope.tool_call_id:
        raise ValueError('stable tool invocation identity is unavailable')
    return scope.tool_call_id


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
    if state.get('format_version') != 7:
        raise ValueError('Unsupported TS input format; existing compute jobs remain intact.')
    record = TsProcessRecord.model_validate(state)
    states = {job['job_id']: job['state'] for job in jobs}
    for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]:
        if step.job_id in states:
            step.state = states[step.job_id]
    return record


def _revision_request_input(db, record, accepted):
    """Replay native index conversion against the originally accepted declaration."""
    if accepted is None:
        return record.input
    with db.connect() as con:
        row = con.execute('SELECT payload FROM ts_pipeline_declarations WHERE process_id=? AND declaration_revision=?',
                          (record.pipeline_id, accepted.previous_input_revision)).fetchone()
    if row is None:
        raise ValueError('accepted revision has no immutable input declaration')
    return TsInput.model_validate_json(row[0])


async def revise_run(tool, run_id, changes, reason, session, *, expected_revision=None) -> TsProcess_output_schema:
    """Shared run mutation: one scope, revision transaction and queue driver."""
    import asyncio

    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.services.ts_pipeline_store import get_revision_receipt
    try:
        from cloudra.tools.core.permission_model import Permission
        if not tool.subagent.permission_all() & Permission.WRITE:
            raise ValueError('TS mutation requires producer write permission')
        workspace = _resolve_workspace(tool)
        record = await asyncio.to_thread(_read_resume_record, pipeline_database(), workspace, run_id, tool.subagent.conversation_id)
        if tool.subagent.conversation_id != record.owner_conversation_id:
            raise ValueError(f'TS process belongs to a different project ({record.owner_conversation_id})')
        if session and session.id and session.id != record.owner_session_id:
            from cloudra.services.ts_pipeline_store import transfer_process_ownership
            if record.pipeline_id:
                await asyncio.to_thread(
                    transfer_process_ownership,
                    pipeline_database(),
                    process_id=record.pipeline_id,
                    project_id=tool.subagent.conversation_id,
                    new_owner_session_id=session.id,
                )
            record.owner_session_id = session.id
        request_key = _request_key(tool.tool_name)
        accepted = await asyncio.to_thread(get_revision_receipt, pipeline_database(),
            process_id=record.pipeline_id, request_key=request_key)
        if accepted is None and expected_revision is not None and record.revision != expected_revision:
            raise ValueError('stale process revision; inspect the current structure and retry')
        request = TsResumeRequest.model_validate({'changes': changes, 'reason': reason,
            'request_key': request_key,
            'expected_revision': accepted.previous_revision if accepted else record.revision})
        prior_input = await asyncio.to_thread(_revision_request_input, pipeline_database(), record, accepted)
        request.changes = normalize_ts_input_atoms(request.changes, atom_tables={}, current_input=prior_input)
        record = await asyncio.to_thread(resume, record, request)
        out = await asyncio.to_thread(_to_output, record)
        out.receipt = await asyncio.to_thread(get_revision_receipt, pipeline_database(), process_id=record.pipeline_id, request_key=request.request_key)
        return out
    except (ValueError, OSError) as exc:
        return TsProcess_output_schema(is_success=False, run_id=run_id, message=f'{tool.tool_name}: {exc}')


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
            workspace = _resolve_workspace(self)
            request = TsStartRequest(input=normalize_ts_input_atoms(user_input.input, atom_tables={}),
                workspace_dir=workspace, request_key=_request_key(self.tool_name),
                owner_conversation_id=self.subagent.conversation_id,
                owner_session_id=session.id if session else None)
            record = await asyncio.to_thread(start, request)
            return await asyncio.to_thread(_to_output, record)
        except (ValueError, OSError) as exc:
            return TsProcess_output_schema(is_success=False, message=f'ts_prepare: {exc}')


class TsResume(Tool):
    tool_id: str = 't-60'
    tool_name: str = 'ts_resume'
    tool_description: str = 'Revise input groups on the existing TS path. Omitted calculation fields retain settings; explicit empty values clear them. Engine, method or basis changes use {replace: complete_configuration}; profile-reference changes use {replace: {ref: name}}. Proven atom reorderings are handled internally; source files remain unchanged and new incoming atom declarations convert once. Omitted conformer fields retain current state; null clears them. Future calls use the returned current atom order with each field\'s documented index base. Historical QM artifacts retain their original order. Declare the intended change and its reason; the runtime manages concurrency and replay identity. Revise a failed or no-peak search with new scientific inputs, or retry with changes={}; previous attempts remain recorded automatically. Queued jobs allow revisions; superseded queued jobs are withdrawn. Running jobs prevent revisions. Use ts_inspect for reads.'
    input_schema: Any = TsResume_input_schema
    output_schema: Any = TsProcess_output_schema

    def is_write(self):
        return True

    async def tool_call(self, user_input: TsResume_input_schema, session: Session):
        return await revise_run(self, user_input.run_id, user_input.changes, user_input.reason, session)


class TsStop(Tool):
    tool_id: str = 't-ts-stop'
    tool_name: str = 'ts_stop'
    tool_description: str = 'Stop an existing TS run from advancing. Queued jobs are withdrawn; running jobs receive cancel_requested for the execution worker to finish safely. Existing results remain available. Stopping is workflow control, not scientific failure. Use ts_resume to restart the stopped run with the intended input changes.'
    input_schema: Any = TsStop_input_schema
    output_schema: Any = TsProcess_output_schema

    def is_write(self):
        return True

    async def tool_call(self, user_input: TsStop_input_schema, session: Session):
        import asyncio

        from cloudra.services.ts_pipeline_context import pipeline_database
        from cloudra.tools.core.permission_model import Permission
        try:
            if not self.subagent.permission_all() & Permission.WRITE:
                raise ValueError('TS mutation requires producer write permission')
            workspace = _resolve_workspace(self)
            record = await asyncio.to_thread(_read_resume_record, pipeline_database(), workspace,
                                            user_input.run_id, self.subagent.conversation_id)
            if self.subagent.conversation_id != record.owner_conversation_id:
                raise ValueError(f'TS process belongs to a different project ({record.owner_conversation_id})')
            if session and session.id and session.id != record.owner_session_id:
                from cloudra.services.ts_pipeline_store import transfer_process_ownership
                if record.pipeline_id:
                    await asyncio.to_thread(
                        transfer_process_ownership,
                        pipeline_database(),
                        process_id=record.pipeline_id,
                        project_id=self.subagent.conversation_id,
                        new_owner_session_id=session.id,
                    )
                record.owner_session_id = session.id
            from cloudra.tools.core.ts_process import stop
            record = await asyncio.to_thread(stop, record, user_input.reason)
            return await asyncio.to_thread(_to_output, record)
        except (ValueError, OSError) as exc:
            return TsProcess_output_schema(is_success=False, run_id=user_input.run_id, message=f'ts_stop: {exc}')


class TsInspect(Tool):
    tool_id: str = 't-ts-inspect'
    tool_name: str = 'ts_inspect'
    tool_description: str = 'Read authoritative TS state, current atom tables, jobs, methods, evidence and missing inputs. Current atom identities/order come from owned molecular state; future references use each field\'s documented index base. export_revision may identify a stale JSON export, while this returned revision is authoritative. Historical artifacts retain their original atom order. Does not submit calculations or initiate input revisions; inspection does not change source files or run state. Same-project read-only reviewers may inspect another agent’s run.'
    input_schema: Any = TsInspect_input_schema
    output_schema: Any = TsProcess_output_schema

    def is_read(self):
        return True

    async def tool_call(self, user_input: TsInspect_input_schema, session: Session):
        import asyncio

        from cloudra.services.ts_pipeline_context import pipeline_database
        from cloudra.tools.core.permission_model import Permission
        try:
            workspace = _resolve_workspace(self)
            permissions = self.subagent.permission_all()
            if not permissions & Permission.READ:
                raise ValueError('TS inspection requires read permission')
            view = await asyncio.to_thread(inspect_process, pipeline_database(), project_id=self.subagent.conversation_id,
                run_id=user_input.run_id, workspace_dir=workspace, can_write=bool(permissions & Permission.WRITE), owner_id=session.id if session else None)
            return TsProcess_output_schema(**view.model_dump())
        except (ValueError, OSError) as exc:
            return TsProcess_output_schema(is_success=False, run_id=user_input.run_id, message=f'ts_inspect: {exc}')
