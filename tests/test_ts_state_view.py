"""TS verdict output remains distinct from invocation and workflow completion."""

import pytest
from pydantic import ValidationError

from cloudra.tools.core.ts_state_view import TsProcessView, build_process_view


def state_input(**groups):
    from cloudra.tools.core.ts_inputs import TsInput
    value = TsInput(reaction=dict(reactant_smiles='O', product_smiles='O', charge=0,
                                 multiplicity=1)).model_dump(mode='json')
    value.update(groups)
    return value


def test_verdict_output_rejects_unknown_outcome():
    """An arbitrary result label must not cross the recorded-verdict boundary."""
    with pytest.raises(ValidationError):
        TsProcessView(result={
            "outcome": "complete", "verified": True, "reason": "Claimed completion", "evidence_refs": [],
        })


@pytest.mark.parametrize("terminal,verified", [
    ("verified", True), ("candidate_only", False), ("search_failed", False), ("invalid_input", False),
])
def test_ended_workflow_preserves_recorded_scientific_verdict(tmp_path, terminal, verified):
    state = {
        "format_version": 7, "run_id": "ts_fixture", "revision": 1,
        "run_dir": str(tmp_path), "stage": "verdict", "terminal": terminal,
        "stage_records": [{"stage": "verdict", "status": "done", "detail": "Recorded reason"}],
        "evidence_candidates": ["frequency.out", "irc.out"],
        "input": state_input(),
    }
    view = build_process_view(state, [], can_write=False)
    assert view.status == "ended"
    assert view.result == {
        "outcome": terminal, "verified": verified, "reason": "Recorded reason",
        "evidence_refs": ["frequency.out", "irc.out"],
    }
    assert view.model_dump(mode="json")["result"] == view.result


def test_scan_actual_configuration_contract_and_artifact_survive_separate_scan_step(tmp_path):
    from copy import deepcopy

    planned = dict(engine='orca', method='HF', basis_set='STO-3G', keywords='TightSCF')
    actual = dict(engine='orca', method='HF', basis_set='STO-3G', keywords='TightSCF',
                  frequency_mode='auto', orca_blocks=None, end_setting='')
    contract = dict(verification='native_input_matches_resolved_configuration', declared=actual)
    state = dict(format_version=7, run_id='ts_scan', revision=2, declaration_revision=3,
        run_dir=str(tmp_path), stage='guess', input=state_input(calculations={'scan_level': planned},
        guess=dict(kind='scan', calculation={'ref': 'scan_level'},
                   scans=[dict(atoms=[0, 1], scan_end=2, scan_steps=5)])), job_steps=[], stage_records=[],
        scan_step=dict(purpose='scan', job_id=17, input_path='scan.inp', actual_calculation=actual,
                       method_contract={'verification': 'older_snapshot'}, source_input_revision=3),
        method_checks={'scan.inp': contract})
    jobs = [dict(job_id=17, purpose='scan', state='done', log_path='scan.out', source_input_revision=3)]
    before = deepcopy(state)
    view = build_process_view(state, jobs, can_write=False)
    scan = next(entry for entry in view.methods if entry['purpose'] == 'scan')
    assert scan['planned'] == actual
    assert scan['actual'] == actual
    assert scan['contract'] == contract
    artifact = next(entry for entry in view.available_results if entry.get('job_id') == 17)
    assert artifact['artifacts'] == ['scan.out']
    assert artifact['input_revision_relation'] == 'current'
    assert state == before
    state['input']['calculations']['scan_level']['keywords'] = 'VeryTightSCF'
    updated = next(entry for entry in build_process_view(state, jobs, can_write=False).methods
                   if entry['purpose'] == 'scan')
    assert updated['planned']['keywords'] == 'VeryTightSCF'
    assert updated['actual']['keywords'] == 'TightSCF'
    assert updated['contract'] == contract


def test_legacy_format_keeps_raw_method_snapshots_isolated_without_resolving(tmp_path):
    planned = dict(engine='orca', method='b3lyp/def2svp', keywords='TightSCF')
    actual = dict(engine='orca', method='b3lyp/def2svp', keywords='TightSCF')
    state = dict(format_version=4, run_id='ts_legacy', revision=1, run_dir=str(tmp_path),
        stage='verdict', terminal='verified', input=dict(guess=dict(kind='scan', calculation=planned)),
        scan_step=dict(purpose='scan', job_id=9, input_path='historical.inp', actual_calculation=actual),
        job_steps=[], stage_records=[])
    view = build_process_view(state, [], can_write=True)
    assert view.status == 'isolated'
    assert view.next['action'] == 'inspect'
    assert view.result is None
    scan = next(entry for entry in view.methods if entry['purpose'] == 'scan')
    assert scan['planned'] == planned
    assert scan['actual'] == actual


def test_undefined_planned_reference_is_reported_without_hiding_actual_snapshot(tmp_path):
    actual = dict(engine='orca', method='HF', basis_set='STO-3G', keywords='TightSCF')
    state = dict(format_version=7, run_id='ts_bad_ref', revision=1, run_dir=str(tmp_path), stage='submit',
        input=state_input(ts_optimization={'ref': 'missing'}),
        job_steps=[dict(purpose='ts_opt', job_id=None, input_path='existing.inp', actual_calculation=actual)],
        stage_records=[])
    view = build_process_view(state, [], can_write=False)
    entry = next(item for item in view.methods if item['purpose'] == 'ts_opt')
    assert entry['planned'] == {'ref': 'missing'}
    assert 'missing' in entry['planned_error']
    assert entry['actual'] == actual


@pytest.mark.parametrize("accounted,model_calls,compute_actions", [
    ({}, None, 1),
    ({"model_calls": 0, "compute_actions": 0}, 0, 0),
    ({"model_calls": 3, "compute_actions": 5}, 3, 5),
])
def test_usage_ledger_overrides_fallback_and_preserves_actual_jobs(tmp_path, accounted, model_calls, compute_actions):
    state = dict(format_version=7, run_id="ts_usage", revision=1, run_dir=str(tmp_path),
                 stage="refine", intervention_count=2, accounted_usage=accounted,
                 input=state_input(execution={"limits": {"max_compute_actions": 8}}))
    jobs = [dict(job_id=17, state="ready", req_cpus=4)]
    view = build_process_view(state, jobs, can_write=False)
    assert view.usage["model_calls"] == model_calls
    assert view.usage["compute_actions"] == compute_actions
    assert view.usage["interventions"] == 2
    assert view.usage["limits"] == {"max_compute_actions": 8}
    assert view.usage["jobs"] == [dict(job_id=17, runtime_seconds=None, cpus=4,
        memory_mb=None, measured_cpu_hours=None, allocated_cpu_hours=None)]


@pytest.mark.parametrize("job_states,can_write,action", [
    (["ready"], True, "resume"),
    (["running"], True, "wait_for_system"),
    (["cancel_requested"], True, "wait_for_system"),
    (["ready", "running"], True, "wait_for_system"),
    (["ready"], False, "inspect"),
    (["running"], False, "inspect"),
])
def test_queued_jobs_allow_revising_inputs_before_compute_starts(tmp_path, job_states, can_write, action):
    state = dict(format_version=7, run_id="ts_queued", revision=1, run_dir=str(tmp_path),
                 stage="refine", waiting_for=[17],
                 input=state_input(ts_optimization=dict(engine="orca", method="HF", basis_set="STO-3G")))
    jobs = [dict(job_id=17 + index, state=job_state) for index, job_state in enumerate(job_states)]

    view = build_process_view(state, jobs, can_write=can_write)

    assert view.status == "waiting"
    assert view.waiting_for == jobs
    assert view.next == dict(action=action, required_inputs=[],
                             editable_groups=list(state['input']) if action == "resume" else [])


@pytest.mark.parametrize("job_states,can_write,action", [
    (["cancel_requested"], True, "wait_for_system"),
    (["ready"], True, "wait_for_system"),
    (["cancelled"], True, "resume"),
    (["done", "failed", "cancelled"], True, "resume"),
    ([], True, "resume"),
    (["cancel_requested"], False, "inspect"),
    (["cancelled"], False, "inspect"),
])
def test_stopped_process_reports_reason_and_waits_for_cancellation(tmp_path, job_states, can_write, action):
    from copy import deepcopy

    reason = "Use the alternative conformer before continuing"
    state = dict(format_version=7, run_id="ts_stopped", revision=2, run_dir=str(tmp_path),
                 stage="refine", waiting_for="job:17", stop_reason=reason,
                 blocked={"message": "Earlier input is missing", "needs": ["verification.irc"]},
                 input=state_input(ts_optimization=dict(engine="orca", method="HF", basis_set="STO-3G")))
    jobs = [dict(job_id=17 + index, state=job_state) for index, job_state in enumerate(job_states)]
    before = deepcopy(state), deepcopy(jobs)

    view = build_process_view(state, jobs, can_write=can_write)

    assert view.status == "stopped"
    assert reason in view.message
    assert view.result is None
    assert view.waiting_for == [job for job in jobs if job["state"] not in {"done", "failed", "cancelled"}]
    assert view.next == dict(action=action, required_inputs=["verification.irc"] if action == "resume" else [],
                             editable_groups=list(state['input']) if action == "resume" else [])
    assert (state, jobs) == before
