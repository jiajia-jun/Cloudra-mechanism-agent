from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from cloudra.persistence.database import ComputeDB


def payload(**overrides):
    data = dict(
        project_id="project",
        owner_id="owner",
        workspace_dir="/fixture",
        declaration=dict(reactant_smiles="CC", product_smiles="CC", method="b3lyp/def2svp"),
    )
    data.update(overrides)
    return data


def job_payload(**overrides):
    data = dict(
        conversation_id="project",
        session_id="owner",
        path="/fixture/input.inp",
        state="ready",
        jobtype="orca",
        node_id="fixture",
    )
    data.update(overrides)
    path = Path(ComputeDB().path).parent / "stage-fixtures" / Path(data["path"]).name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("synthetic engine input")
    data["path"] = str(path)
    return data


def test_request_retry_returns_original_process_and_conflicts_are_rejected(tmp_path):
    from cloudra.services.ts_pipeline_store import create_process

    db = ComputeDB(data_dir=tmp_path).init()
    first = create_process(db, request_key="request", payload=payload())
    assert create_process(db, request_key="request", payload=payload()) == first
    with pytest.raises(ValueError, match="conflict"):
        create_process(db, request_key="request", payload=payload(workspace_dir="/another"))


def test_two_connections_bind_one_stage_job(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process

    db = ComputeDB(data_dir=tmp_path).init()
    process = create_process(db, request_key="request", payload=payload())
    # Prepare immutable bytes before racing the two independent DB connections.
    stage_job = job_payload()

    def bind(_):
        return bind_stage_job(
            ComputeDB.from_path(db.path),
            process_id=process["process_id"],
            declaration_revision=1,
            stage_key="ts_opt",
            attempt=1,
            job_payload=stage_job,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(bind, range(2)))
    assert jobs[0] == jobs[1]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1


def test_changed_bound_input_conflicts_and_foreign_owner_is_rejected(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process

    db = ComputeDB(data_dir=tmp_path).init()
    process = create_process(db, request_key="request", payload=payload())
    kwargs = dict(process_id=process["process_id"], declaration_revision=1, stage_key="ts_opt", attempt=1)
    bind_stage_job(db, **kwargs, job_payload=job_payload())
    with pytest.raises(ValueError, match="conflict"):
        bind_stage_job(db, **kwargs, job_payload=job_payload(path="/other"))
    with pytest.raises(ValueError, match="owner"):
        bind_stage_job(db, **dict(kwargs, stage_key="frequency"), job_payload=job_payload(session_id="foreign"))


def test_stage_result_compare_and_swap_preserves_history(tmp_path):
    from cloudra.services.ts_pipeline_store import (
        bind_stage_job,
        commit_stage_result,
        create_process,
        get_process,
        process_for_job,
    )

    db = ComputeDB(data_dir=tmp_path).init()
    process = create_process(db, request_key="request", payload=payload())
    pid = process["process_id"]
    job = bind_stage_job(
        db, process_id=pid, declaration_revision=1, stage_key="ts_opt", attempt=1, job_payload=job_payload()
    )
    current = get_process(db, pid)
    evidence = dict(status="done", artifacts=["log"], input_hash="input")
    assert commit_stage_result(
        db, process_id=pid, expected_revision=current["revision"], stage_key="ts_opt", attempt=1, evidence=evidence
    )
    assert not commit_stage_result(
        db,
        process_id=pid,
        expected_revision=current["revision"],
        stage_key="ts_opt",
        attempt=1,
        evidence=dict(evidence, status="failed"),
    )
    assert process_for_job(db, job) == pid


def test_stage_job_and_budget_binding_commit_atomically(tmp_path):
    from cloudra.services.exploration_budget_store import ExplorationBudget, configure_budget, reserve_actions
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process
    from tests.test_exploration_budget_store import estimate

    db = ComputeDB(data_dir=tmp_path).init()
    process = create_process(db, request_key="request", payload=payload())
    configure_budget(
        db,
        process_id=process["process_id"],
        project_id="project",
        owner_id="owner",
        budget=ExplorationBudget(source="explicit_user", max_compute_actions=1),
    )
    reservation = reserve_actions(
        db, process_id=process["process_id"], decision_id="decision", estimates=[estimate("ts")]
    )
    job = bind_stage_job(
        db,
        process_id=process["process_id"],
        declaration_revision=1,
        stage_key="ts_opt",
        attempt=1,
        job_payload=job_payload(),
        reservation_id=reservation.reservation_id,
        action_key="ts",
    )
    with db.connect() as con:
        assert con.execute("SELECT job_id FROM exploration_actions").fetchone()[0] == job
    with pytest.raises(ValueError):
        bind_stage_job(
            db,
            process_id=process["process_id"],
            declaration_revision=1,
            stage_key="frequency",
            attempt=1,
            job_payload=job_payload(path="/frequency"),
            reservation_id=reservation.reservation_id,
            action_key="missing",
        )
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1


def test_budget_api_binds_stage_and_job_in_one_transaction(tmp_path):
    from cloudra.services.exploration_budget_store import (
        ExplorationBudget,
        bind_reserved_job,
        configure_budget,
        reserve_actions,
    )
    from cloudra.services.ts_pipeline_store import create_process
    from tests.test_exploration_budget_store import estimate

    db = ComputeDB(data_dir=tmp_path).init()
    process = create_process(db, request_key="budget-api", payload=payload())
    configure_budget(
        db,
        process_id=process["process_id"],
        project_id="project",
        owner_id="owner",
        budget=ExplorationBudget(source="explicit_user", max_compute_actions=1),
    )
    reservation = reserve_actions(
        db, process_id=process["process_id"], decision_id="decision", estimates=[estimate("ts")]
    )
    data = dict(
        process_id=process["process_id"],
        declaration_revision=1,
        stage_key="ts_opt",
        attempt=1,
        job_payload=job_payload(),
    )
    first = bind_reserved_job(db, reservation_id=reservation.reservation_id, action_key="ts", stage_job_payload=data)
    assert (
        bind_reserved_job(db, reservation_id=reservation.reservation_id, action_key="ts", stage_job_payload=data)
        == first
    )


def test_declaration_revision_preserves_original_request_and_stage_history(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process, revise_declaration

    db = ComputeDB(data_dir=tmp_path).init()
    original = payload()
    process = create_process(db, request_key="revision", payload=original)
    first = bind_stage_job(
        db,
        process_id=process["process_id"],
        declaration_revision=1,
        stage_key="ts_opt",
        attempt=1,
        job_payload=job_payload(),
    )
    changed = dict(original["declaration"], atom_map=[0, 1])
    revision = revise_declaration(
        db, process_id=process["process_id"], expected_declaration_revision=1, declaration=changed
    )
    assert revision == 2
    second = bind_stage_job(
        db,
        process_id=process["process_id"],
        declaration_revision=2,
        stage_key="ts_opt",
        attempt=1,
        job_payload=job_payload(path="/revision2"),
    )
    assert first != second
    assert create_process(db, request_key="revision", payload=original)["process_id"] == process["process_id"]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM ts_pipeline_stages").fetchone()[0] == 2
    with pytest.raises(ValueError, match="stale"):
        revise_declaration(db, process_id=process["process_id"], expected_declaration_revision=1, declaration=changed)


def test_same_bound_path_with_changed_bytes_is_rejected(tmp_path):
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process

    db = ComputeDB(data_dir=tmp_path).init()
    process = create_process(db, request_key="bytes", payload=payload())
    job = job_payload()
    args = dict(
        process_id=process["process_id"], declaration_revision=1, stage_key="ts_opt", attempt=1, job_payload=job
    )
    bind_stage_job(db, **args)
    Path(job["path"]).write_text("changed input bytes")
    with pytest.raises(ValueError, match="conflict"):
        bind_stage_job(db, **args)
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1


def test_stage_execution_rejects_input_changed_after_binding(tmp_path):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process, verify_stage_input

    db = ComputeDB().init()
    process = create_process(db, request_key="execution-digest", payload=payload())
    path = tmp_path / "immutable.inp"
    path.write_text("accepted input")
    data = job_payload()
    data["path"] = str(path)
    job = bind_stage_job(
        db, process_id=process["process_id"], declaration_revision=1, stage_key="opt", attempt=1, job_payload=data
    )
    verify_stage_input(db, job)
    path.write_text("different input")
    with pytest.raises(ValueError, match="changed"):
        verify_stage_input(db, job)
