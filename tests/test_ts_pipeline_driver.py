import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.tools.core.ts_inputs import TsInput, TsResumeRequest
from tests.test_ts_pipeline_store import job_payload, payload


def waiting_process(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process, save_process_record
    from cloudra.tools.core.ts_process import TsJobStep, TsProcessRecord

    db = ComputeDB().init()
    created = create_process(db, request_key="driver", payload=payload(workspace_dir=str(tmp_path)))
    pid = created["process_id"]
    prepared_job = job_payload()
    job = bind_stage_job(
        db, process_id=pid, declaration_revision=1, stage_key="ts_opt", attempt=1, job_payload=prepared_job
    )
    record = TsProcessRecord(
        run_id="driver",
        run_dir=str(tmp_path / "ts" / "driver"),
        workspace_dir=str(tmp_path),
        owner_conversation_id="project",
        owner_session_id="owner",
        input=TsInput.model_validate(payload()["input"]),
        pipeline_id=pid,
        stage="refine",
        waiting_for=f"job:{job}",
        job_steps=[TsJobStep(purpose="ts_opt", job_id=job, input_path=prepared_job['path'],
                             actual_calculation=TsInput.model_validate(payload()['input']).ts_optimization)],
    )
    from pathlib import Path

    Path(record.run_dir).mkdir(parents=True, exist_ok=True)
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    return db, pid, job


def test_active_job_does_not_advance_or_resubmit(tmp_path):
    from cloudra.tools.core.ts_pipeline_driver import advance_process

    db, pid, job = waiting_process(tmp_path)
    result = advance_process(db, pid)
    assert result["record"]["waiting_for"] == f"job:{job}"
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1


@pytest.mark.usefixtures("rdkit_chemistry")
def test_terminal_event_advances_without_resume_and_repeated_event_reuses_job(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal

    db, pid, job = waiting_process(tmp_path)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))

    def writer(record, directory):
        from pathlib import Path

        path = Path(directory) / "frequency.inp"
        path.write_text("! Freq B3LYP def2-SVP\n* xyz 0 1\nO 0 0 0\n*\n")
        return "", str(path)

    monkeypatch.setattr(ts_process, "_write_frequency_input", writer)
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    first = handle_process_job_terminal(db, job)
    second = handle_process_job_terminal(db, job)
    assert first["record"]["job_steps"][-1]["purpose"] == "frequency"
    assert second["record"]["job_steps"][-1]["job_id"] == first["record"]["job_steps"][-1]["job_id"]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 2


def test_empty_resume_is_query_and_waiting_adjustment_is_rejected(tmp_path):
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core.ts_process import TsProcessRecord, resume

    db, pid, job = waiting_process(tmp_path)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='running' WHERE id=?", (job,))
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    with pytest.raises(ValueError, match="active"):
        resume(record, TsResumeRequest(changes={"reaction":{"selected_candidate":0}}, reason="fix mapping", request_key="mapping", expected_revision=get_process(db,pid)["revision"]))


@pytest.mark.parametrize('finishes_during_resume', [False, True])
def test_retained_queued_job_records_result_in_its_original_declaration(tmp_path, monkeypatch, finishes_during_resume):
    import json

    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal
    from cloudra.tools.core.ts_process import TsProcessRecord, resume

    db, pid, job = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)['record'])
    if finishes_during_resume:
        def commit_then_finish(*args, **kwargs):
            result = commit_input_revision(*args, **kwargs)
            with db.connect() as con:
                con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (job,))
            return result

        monkeypatch.setattr('cloudra.services.ts_pipeline_store.commit_input_revision', commit_then_finish)
    revised = resume(record, TsResumeRequest(
        changes={'verification': {'irc': {'replace': {
            'engine': 'orca', 'method': 'b97-3c', 'basis_set': '', 'keywords': '',
        }}}},
        reason='Revise the future IRC without replacing the queued TS optimization',
        request_key='queued-irc-change', expected_revision=record.revision,
    ))
    assert revised.declaration_revision == 2
    if not finishes_during_resume:
        assert revised.waiting_for == f'job:{job}'
    assert revised.job_steps[0].source_input_revision == 1
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (job,))
    handle_process_job_terminal(db, job)
    with db.connect() as con:
        source_revision, evidence = con.execute(
            'SELECT declaration_revision,evidence FROM ts_pipeline_stages WHERE job_id=?', (job,),
        ).fetchone()
    assert source_revision == 1
    assert evidence is not None
    assert json.loads(evidence)['status'] == 'failed'


def test_prepare_response_retry_returns_original_checkpoint(tmp_path, monkeypatch):
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_process import TsStartRequest, start

    def blocked(record):
        return ts_process._block(record, "map", "mapping_needed", "explicit mapping needed", needs=["reaction.selected_candidate"])

    monkeypatch.setattr(ts_process, "advance", blocked)
    request = TsStartRequest(
        workspace_dir=str(tmp_path),
        owner_conversation_id="project",
        owner_session_id="owner",
        input=TsInput.model_validate(payload()["input"]),
        request_key="retry-key",
    )
    first = start(request)
    second = start(request)
    assert first.pipeline_id == second.pipeline_id
    assert first.run_id == second.run_id
    assert second.blocked.failure_class == "mapping_needed"
    with ComputeDB().connect() as con:
        assert con.execute("SELECT COUNT(*) FROM ts_pipeline_processes").fetchone()[0] == 1


@pytest.mark.usefixtures("rdkit_chemistry")
def test_driver_uses_supplied_ledger_and_never_default_database(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process, save_process_record
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_pipeline_driver import advance_process

    db = ComputeDB(data_dir=tmp_path / "separate").init()
    process = create_process(db, request_key="custom", payload=payload(workspace_dir=str(tmp_path)))
    job = bind_stage_job(
        db,
        process_id=process["process_id"],
        declaration_revision=1,
        stage_key="ts_opt",
        attempt=1,
        job_payload=job_payload(),
    )
    record = ts_process.TsProcessRecord(
        run_id="custom",
        pipeline_id=process["process_id"],
        run_dir=str(tmp_path / "custom"),
        workspace_dir=str(tmp_path),
        owner_conversation_id="project",
        owner_session_id="owner",
        input=ts_process.TsInput.model_validate(payload()["input"]),
        stage="refine",
        waiting_for=f"job:{job}",
        job_steps=[ts_process.TsJobStep(purpose="ts_opt", job_id=job, input_path=job_payload()["path"])],
    )
    save_process_record(db, process_id=process["process_id"], record=record.model_dump(mode="json"))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))

    def writer(record, directory):
        from pathlib import Path

        path = Path(directory) / "frequency.inp"
        path.write_text("! Freq B3LYP def2-SVP\n* xyz 0 1\nO 0 0 0\n*\n")
        return "", str(path)

    monkeypatch.setattr(ts_process, "_write_frequency_input", writer)
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    result = advance_process(db, process["process_id"])
    assert result["record"]["waiting_for"] == f"job:{job + 1}"
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 2


def test_resume_reload_uses_authoritative_waiting_checkpoint(tmp_path):
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core.ts_process import TsProcessRecord, resume

    db, pid, job = waiting_process(tmp_path)
    stale = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    stale.waiting_for = ""
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='running' WHERE id=?", (job,))
    with pytest.raises(ValueError, match="active"):
        resume(stale, TsResumeRequest(changes={"reaction":{"selected_candidate":0}}, reason="fix mapping", request_key="mapping", expected_revision=get_process(db,pid)["revision"]))
    assert get_process(db, pid)["record"]["waiting_for"] == f"job:{job}"


def test_pipeline_path_is_queued_without_running_engine_in_tool_worker(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core import ts_process

    db, pid, _ = waiting_process(tmp_path)
    record = ts_process.TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.stage = "guess"
    record.waiting_for = ""
    record.job_steps = []
    from cloudra.tools.core.reaction_state import ReactionStructures
    from cloudra.tools.core.ts_inputs import XtbPathGuess
    Chem = pytest.importorskip('rdkit.Chem')
    molecule = Chem.AddHs(Chem.MolFromSmiles('O'))
    conformer = Chem.Conformer(3)
    for index, point in enumerate([[0, 0, 0], [.96, 0, 0], [-.24, .93, 0]]):
        conformer.SetAtomPosition(index, point)
    molecule.AddConformer(conformer)
    record.input.reaction.reactant_smiles = record.input.reaction.product_smiles = 'O'
    record.structures = ReactionStructures(reactant=molecule, product=molecule, product_to_reactant=(0, 1, 2))
    record.input.guess = XtbPathGuess(kind="xtb_path", method="GFN2-xTB")
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )

    def forbidden(*args):
        pytest.fail("queued process invoked an unmanaged engine")

    monkeypatch.setattr("cloudra.tools.core.xtb_path_runner.run_xtb_path", forbidden)
    result = ts_process._guess(record)
    assert result.waiting_for.startswith("job:")
    assert result.job_steps[-1].purpose == "path"
    with db.connect() as con:
        assert (
            con.execute("SELECT jobtype FROM compute_jobs WHERE id=?", (result.job_steps[-1].job_id,)).fetchone()[0]
            == "chem_task"
        )


def test_terminal_stage_records_immutable_execution_evidence(tmp_path, monkeypatch):
    import json

    from cloudra.tools.core.ts_pipeline_driver import advance_process

    db, pid, job = waiting_process(tmp_path)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (job,))
    monkeypatch.setattr("cloudra.tools.core.ts_process.advance", lambda r: r)
    advance_process(db, pid)
    advance_process(db, pid)
    with db.connect() as con:
        evidence = con.execute("SELECT evidence FROM ts_pipeline_stages WHERE job_id=?", (job,)).fetchone()[0]
    assert json.loads(evidence)["status"] == "failed"
    assert len(json.loads(evidence)["input_hash"]) == 64


@pytest.mark.parametrize('purpose', ['ts_opt', 'frequency'])
def test_completed_job_keeps_the_atom_binding_frozen_when_it_was_submitted(tmp_path, monkeypatch, purpose):
    import json
    from copy import deepcopy
    from pathlib import Path

    from cloudra.infra.compute_utils import resolve_log_path
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import (
        atom_binding_for_log,
        create_process,
        save_process_record,
    )
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.molecule import with_positions
    from cloudra.tools.core.reaction_state import ReactionStructures
    from cloudra.tools.core.ts_pipeline_driver import handle_process_job_terminal

    Chem = pytest.importorskip('rdkit.Chem')
    molecule = Chem.AddHs(Chem.MolFromSmiles('O'))
    conformer = Chem.Conformer(3)
    for index, point in enumerate([[0, 0, 0], [.96, 0, 0], [-.24, .93, 0]]):
        conformer.SetAtomPosition(index, point)
    molecule.AddConformer(conformer)
    declared = payload(workspace_dir=str(tmp_path))
    declared['input']['reaction'].update(reactant_smiles='O', product_smiles='O')
    db = ComputeDB().init()
    process = create_process(db, request_key='frozen-binding', payload=declared)
    record = ts_process.TsProcessRecord(run_id='frozen-binding', pipeline_id=process['process_id'],
        run_dir=str(tmp_path / 'run'), workspace_dir=str(tmp_path), owner_conversation_id='project',
        owner_session_id='owner', input=declared['input'], stage='submit',
        structures=ReactionStructures(reactant=molecule, product=molecule, candidate=molecule,
                                      product_to_reactant=(0, 1, 2)))
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))
    with use_pipeline_database(db):
        if purpose == 'ts_opt':
            ts_process._submit(record)
        else:
            frequency = Path(record.run_dir) / 'frequency.inp'
            frequency.parent.mkdir(parents=True, exist_ok=True)
            frequency.write_text('! Freq B3LYP def2svp\n%pal nprocs 2 end\n%maxcore 1024\n* xyz 0 1\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\n*\n')
            error, job = ts_process._submit_step(record, 'frequency', str(frequency), 'orca')
            assert not error
            record.job_steps.append(ts_process.TsJobStep(purpose='frequency', job_id=job, input_path=str(frequency),
                actual_calculation=record.input.verification.frequency, atom_binding=ts_process._direction_atom_binding(record)))
    assert record.blocked is None
    step = record.job_steps[-1]
    frozen = deepcopy(step.atom_binding)
    assert frozen['atom_map'] == [1, 2, 3]
    record.structures.product = with_positions(molecule, [[0, 0, 0], [1.4, 0, 0], [0, 1.3, 0]])
    record.structures.product_to_reactant = (0, 2, 1)
    record.stage, record.waiting_for = 'refine', f'job:{step.job_id}'
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
    log = Path(resolve_log_path(step.input_path, 'orca', step.job_id))
    log.write_text('ORCA TERMINATED NORMALLY\n')
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (step.job_id,))
    monkeypatch.setattr(ts_process, 'advance', lambda state: state)
    handle_process_job_terminal(db, step.job_id)
    with db.connect() as con:
        evidence = json.loads(con.execute('SELECT evidence FROM ts_pipeline_stages WHERE job_id=?',
                                         (step.job_id,)).fetchone()[0])
    if purpose == 'frequency':
        import hashlib
        frozen['ts_log_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
    assert evidence['atom_binding'] == frozen
    assert evidence['atom_binding']['atom_map'] == [1, 2, 3]
    assert atom_binding_for_log(db, log, tmp_path) == frozen


pytestmark = pytest.mark.usefixtures("ts_producer_authority")
