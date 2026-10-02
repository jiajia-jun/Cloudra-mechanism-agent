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
    job = bind_stage_job(
        db, process_id=pid, declaration_revision=1, stage_key="ts_opt", attempt=1, job_payload=job_payload()
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
        job_steps=[TsJobStep(purpose="ts_opt", job_id=job, input_path="/fixture/input.inp")],
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

    db, pid, _ = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    with pytest.raises(ValueError, match="active"):
        resume(record, TsResumeRequest(changes={"reaction":{"atom_map":[0,1]}}, reason="fix mapping", request_key="mapping", expected_revision=get_process(db,pid)["revision"]))


def test_prepare_response_retry_returns_original_checkpoint(tmp_path, monkeypatch):
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_process import TsStartRequest, start

    def blocked(record):
        return ts_process._block(record, "map", "mapping_needed", "explicit mapping needed", needs=["atom_map"])

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
    with pytest.raises(ValueError, match="active"):
        resume(stale, TsResumeRequest(changes={"reaction":{"atom_map":[0,1]}}, reason="fix mapping", request_key="mapping", expected_revision=get_process(db,pid)["revision"]))
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
    record.input.reaction.atom_map = [0]
    from cloudra.tools.core.ts_inputs import XtbPathGuess
    record.input.guess = XtbPathGuess(kind="xtb_path", method="GFN2-xTB")
    monkeypatch.setattr(ts_process, "_read_built_xyz", lambda *args: (["H"], [[0, 0, 0]], "", ""))
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


pytestmark = pytest.mark.usefixtures("ts_producer_authority")
