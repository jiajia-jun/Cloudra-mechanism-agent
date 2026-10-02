"""Durable constrained preparation on the existing TS/compute ledger.

Each derivative is a separate budgeted job. Serializable point checkpoints and
content-addressed stage keys recover READY/checkpoint crash windows without a
second queue, outer iteration limit, or compute deadline.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field

from cloudra.tools.core.conformer_catalog import CatalogModel, content_digest
from cloudra.tools.core.constrained_optimization import (
    OptimizationEvaluation,
    OptimizationRequest,
    OptimizationState,
    initialize_constrained_state,
    step_constrained_state,
)


class OptimizationCheckpoint(CatalogModel):
    state: OptimizationState
    directory: str
    job_ids: list[int] = Field(default_factory=list)
    result: dict | None = None


def advance_optimization(record, stage_key: str, request: OptimizationRequest):
    from cloudra.runtime.chem_task import ChemTask, read_task_result, result_path
    from cloudra.services.compute_store import TERMINAL_STATES
    from cloudra.tools.core.ts_process import (
        TsJobStep,
        _block,
        _job_directory,
        _read_job_state,
        _submit_step,
        _write_immutable_input,
        save_record,
        stage_calculation,
    )
    calculation = stage_calculation(record, 'candidate_evaluation')
    if calculation is None or calculation.engine != 'xtb' or calculation.method != request.method_fingerprint or calculation.keywords:
        raise ValueError('Constrained evaluations require an explicit supported conformer calculation')
    key = content_digest([stage_key, request.model_dump(mode='json'),record.input.reaction.charge,
        record.input.reaction.multiplicity, calculation.model_dump(mode='json')])
    checkpoint = record.optimization_checkpoints.get(key)
    if checkpoint is None:
        checkpoint = OptimizationCheckpoint(state=OptimizationState.model_validate(initialize_constrained_state(request)),
            directory=str(Path(_job_directory(record,'candidate_constraints'))/key))
        record.optimization_checkpoints[key] = checkpoint
        save_record(record)
    if checkpoint.result is not None:
        return checkpoint.result
    while True:
        state = checkpoint.state
        if state.status == 'blocked':
            record.waiting_for = ''
            _block(record, 'build', 'candidate_constrained_optimization_failed', state.error, needs=['conformers.reactant', 'recovery'])
            return None
        if state.status == 'converged':
            result = dict(symbols=request.symbols, positions=state.positions,
                optimization_converged=True, normal_termination=True, returncode=0,
                energy_hartree=state.energy_hartree, method_fingerprint=request.method_fingerprint,
                log_file=state.artifact_refs[-1], artifact_refs=state.artifact_refs,
                job_ids=checkpoint.job_ids, coordinate_backend=state.coordinate_backend,
                numerical_source=state.numerical_source, iterations=state.iteration)
            checkpoint = checkpoint.model_copy(update={'result': result})
            record.optimization_checkpoints[key] = checkpoint
            record.waiting_for = ''
            save_record(record)
            return result
        kind = 'xtb_hessian' if state.status == 'need_hessian' else 'xtb_gradient'
        # Round-trip through the exact XYZ bytes submitted to xTB. These bytes,
        # rather than unrounded Python coordinates, define the evaluation point.
        xyz = '\n'.join([str(len(request.symbols)), 'constrained candidate '+key,
            *[symbol+' '+' '.join(repr(v) for v in row) for symbol,row in zip(request.symbols,state.positions)]])+'\n'
        point_key = content_digest(state.positions)
        directory = Path(checkpoint.directory)/(kind+'_'+point_key)
        directory.mkdir(parents=True, exist_ok=True)
        manifest = directory/'task.json'
        task = ChemTask(task=kind, reactant_xyz=xyz, charge=record.input.reaction.charge,
            multiplicity=record.input.reaction.multiplicity, cpus=record.compute_cpus)
        _write_immutable_input(str(manifest), task.model_dump_json())
        step = next((s for s in record.job_steps if s.purpose=='candidate_evaluation' and s.input_path==str(manifest)),None)
        if step is None:
            error, job = _submit_step(record, 'candidate_evaluation', str(manifest), 'chem_task',
                stage_key=f'candidate_constraints:{key}:{kind}:{point_key}',
                action_kind='frequency' if kind=='xtb_hessian' else 'gradient')
            if error:
                record.waiting_for = ''
                _block(record,'build','candidate_optimization_admission_failed',error,needs=['execution.compute_node','execution.limits'])
                return None
            step = TsJobStep(purpose='candidate_evaluation',job_id=job,input_path=str(manifest),state='ready',
                actual_calculation=calculation, source_input_revision=record.declaration_revision,
                stage_key=f'candidate_constraints:{key}:{kind}:{point_key}')
            record.job_steps.append(step)
            checkpoint = checkpoint.model_copy(update={'job_ids': list(dict.fromkeys([*checkpoint.job_ids,job]))})
            record.optimization_checkpoints[key] = checkpoint
            record.waiting_for = f'job:{job}'
            save_record(record)
        step.state = _read_job_state(record,step.job_id)
        if step.state not in TERMINAL_STATES:
            record.waiting_for = f'job:{step.job_id}'
            return None
        try:
            from cloudra.services.ts_pipeline_context import pipeline_database
            from cloudra.services.ts_pipeline_store import verify_stage_input
            verify_stage_input(pipeline_database(),step.job_id)
            data,_ = read_task_result(step.input_path)
            result = data['result']
            if step.state!='done' or data['process_exit_code']!=0 or result.get('returncode')!=0 or result.get('normal_termination') is not True or result.get('evaluation_valid') is not True:
                raise ValueError('derivative job has no proven successful same-point evaluation')
            if result.get('input_hash')!=point_key or result.get('method_fingerprint')!=request.method_fingerprint or result.get('symbols')!=request.symbols or result.get('positions')!=state.positions:
                raise ValueError('derivative geometry/identity/method mismatch')
            derivative_refs = [result[name] for name in ('gradient_file','hessian_file') if result.get(name)]
            refs = list(dict.fromkeys([*state.artifact_refs,str(manifest),*derivative_refs,str(result_path(str(manifest))),result['log_file']]))
            if kind=='xtb_hessian':
                import numpy as np
                hessian = np.asarray(result['hessian_hartree_per_angstrom2'])
                dimensions = 3*len(request.symbols)
                if hessian.shape!=(dimensions,dimensions) or not np.all(np.isfinite(hessian)) or not np.allclose(hessian,hessian.T):
                    raise ValueError('invalid initial Hessian dimensions/symmetry')
                state = state.model_copy(update={'hessian':hessian.tolist(),'status':'need_gradient','artifact_refs':refs})
            else:
                evaluation = OptimizationEvaluation(input_hash=point_key,method_fingerprint=result['method_fingerprint'],
                    energy_hartree=result['energy_hartree'],gradient_hartree_per_angstrom=result['gradient_hartree_per_angstrom'],artifact_refs=refs)
                state = OptimizationState.model_validate(step_constrained_state(state,evaluation))
                if state.status=='blocked':
                    from cloudra.tools.core.ts_process import _record_candidate_failure
                    _record_candidate_failure(record,'geometry',step,result['log_file'])
        except (OSError,ValueError,KeyError,TypeError) as exc:
            from cloudra.tools.core.ts_process import _record_candidate_failure
            _record_candidate_failure(record,'unclassified_failure',step,step.input_path)
            state = state.model_copy(update={'status':'blocked','error':str(exc)})
        checkpoint = checkpoint.model_copy(update={'state':state})
        record.optimization_checkpoints[key] = checkpoint
        record.waiting_for = ''
        save_record(record)
