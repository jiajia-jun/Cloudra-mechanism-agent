from concurrent.futures import ThreadPoolExecutor

import pytest

from cloudra.persistence.database import ComputeDB


def budget_fixture(tmp_path, **limits):
    from cloudra.services.exploration_budget_store import ExplorationBudget, configure_budget

    db = ComputeDB(data_dir=tmp_path / "data").init()
    configure_budget(
        db,
        process_id="process",
        project_id="project",
        owner_id="owner",
        budget=ExplorationBudget(source="explicit_user", **limits),
    )
    return db


def estimate(key="opt", **overrides):
    from cloudra.services.exploration_budget_store import CostEstimate

    fields = dict(action_key=key, action_kind="optimization", cpu_hours=1, source="fixture")
    fields.update(overrides)
    return CostEstimate(**fields)


def test_two_connections_cannot_exceed_budget(tmp_path):
    from cloudra.services.exploration_budget_store import reserve_actions

    db = budget_fixture(tmp_path, max_compute_actions=1)

    def reserve(number):
        try:
            reserve_actions(
                ComputeDB.from_path(db.path),
                process_id="process",
                decision_id=str(number),
                estimates=[estimate(str(number))],
            )
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, [1, 2])) == [False, True]


def test_duplicate_decision_reserves_once(tmp_path):
    from cloudra.services.exploration_budget_store import budget_usage, reserve_actions

    db = budget_fixture(tmp_path, max_compute_actions=1)
    a = reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    b = reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    assert a.reservation_id == b.reservation_id
    assert budget_usage(db, "process").compute_actions == 1


def test_unknown_cpu_estimate_blocks_under_cpu_cap(tmp_path):
    from cloudra.services.exploration_budget_store import reserve_actions

    db = budget_fixture(tmp_path, estimated_cpu_hours=2)
    with pytest.raises(ValueError, match="unknown"):
        reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate(cpu_hours=None)])


def test_validation_chain_shortfall_blocks_before_ts(tmp_path):
    from cloudra.services.exploration_budget_store import budget_usage, reserve_actions

    db = budget_fixture(tmp_path, max_compute_actions=2)
    with pytest.raises(ValueError, match="budget"):
        reserve_actions(
            db, process_id="process", decision_id="d", estimates=[estimate("ts"), estimate("freq"), estimate("irc")]
        )
    assert budget_usage(db, "process").compute_actions == 0


def test_ready_job_counts_as_accepted_and_active_not_released(tmp_path):
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.exploration_budget_store import (
        attach_existing_job,
        budget_usage,
        reconcile_reservations,
        reserve_actions,
    )

    db = budget_fixture(tmp_path, max_compute_actions=1)
    reservation = reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    job = insert_compute_job(
        db,
        conversation_id="project",
        session_id="owner",
        path="/fixture",
        state="READY",
        jobtype="xtb",
        node_id="fixture",
    )
    attach_existing_job(db, reservation.reservation_id, "opt", job)
    reconcile_reservations(db, "process")
    assert budget_usage(db, "process").compute_actions == 1
    with pytest.raises(ValueError, match="budget"):
        reserve_actions(db, process_id="process", decision_id="next", estimates=[estimate("next")])
    with db.connect() as con:
        assert con.execute("SELECT state FROM compute_jobs WHERE id=?", (job,)).fetchone()[0] == "READY"


def test_failed_job_retains_cost(tmp_path):
    from cloudra.services.exploration_budget_store import ActualCost, budget_usage, reserve_actions, settle_action

    db = budget_fixture(tmp_path, estimated_cpu_hours=2)
    reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    settle_action(
        db,
        process_id="process",
        action_key="opt",
        actual=ActualCost(terminal_state="failed", allocated_cpu_hours=3, measurement_source="recorded_allocated_cpu"),
    )
    assert budget_usage(db, "process").cpu_hours == 3
    assert budget_usage(db, "process").compute_actions == 1


def test_budget_exhaustion_never_kills_job(tmp_path):
    from cloudra.services.exploration_budget_store import reserve_actions

    db = budget_fixture(tmp_path, max_compute_actions=0)
    with db.connect() as con:
        con.execute("INSERT INTO compute_jobs (conversation_id,state,path) VALUES ('project','running','fixture')")
    with pytest.raises(ValueError, match="budget"):
        reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    with db.connect() as con:
        assert con.execute("SELECT state FROM compute_jobs").fetchone()[0] == "running"


def test_invalid_stage_binding_fails_loud_without_new_job(tmp_path):
    from cloudra.services.exploration_budget_store import bind_reserved_job, reserve_actions

    db = budget_fixture(tmp_path)
    reservation = reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    with pytest.raises(ValueError):
        bind_reserved_job(db, reservation_id=reservation.reservation_id, action_key="opt", stage_job_payload={})
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 0


def test_model_retry_consumes_new_action_but_response_retry_does_not(tmp_path):
    from cloudra.services.exploration_budget_store import reserve_actions

    db = budget_fixture(tmp_path, max_model_calls=1)
    ai = estimate("model1", action_kind="model", cpu_hours=None)
    reserve_actions(db, process_id="process", decision_id="d", estimates=[ai])
    reserve_actions(db, process_id="process", decision_id="d", estimates=[ai])
    with pytest.raises(ValueError, match="budget"):
        reserve_actions(
            db,
            process_id="process",
            decision_id="retry",
            estimates=[estimate("model2", action_kind="model", cpu_hours=None)],
        )


@pytest.mark.parametrize("state,reported_job", [("running", True), ("done", False), ("failed", True)])
def test_bound_job_settlement_requires_matching_terminal_evidence(tmp_path, state, reported_job):
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.exploration_budget_store import (
        ActualCost,
        attach_existing_job,
        budget_usage,
        reserve_actions,
        settle_action,
    )

    db = budget_fixture(tmp_path, estimated_cpu_hours=1)
    reservation = reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    job = insert_compute_job(
        db,
        conversation_id="project",
        session_id="owner",
        path="/fixture",
        state=state,
        jobtype="xtb",
        node_id="fixture",
    )
    attach_existing_job(db, reservation.reservation_id, "opt", job)
    with pytest.raises(ValueError, match="terminal|job"):
        settle_action(
            db,
            process_id="process",
            action_key="opt",
            actual=ActualCost(
                job_id=job if reported_job else None,
                terminal_state="done",
                allocated_cpu_hours=0,
                measurement_source="fixture",
            ),
        )
    assert budget_usage(db, "process").cpu_hours == 1
    with pytest.raises(ValueError, match="budget"):
        reserve_actions(db, process_id="process", decision_id="next", estimates=[estimate("next")])


def test_bound_terminal_job_can_settle_and_retry_idempotently(tmp_path):
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.exploration_budget_store import (
        ActualCost,
        attach_existing_job,
        budget_usage,
        reserve_actions,
        settle_action,
    )

    db = budget_fixture(tmp_path, estimated_cpu_hours=1)
    reservation = reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    job = insert_compute_job(
        db,
        conversation_id="project",
        session_id="owner",
        path="/fixture",
        state="done",
        jobtype="xtb",
        node_id="fixture",
    )
    attach_existing_job(db, reservation.reservation_id, "opt", job)
    actual = ActualCost(job_id=job, terminal_state="done", allocated_cpu_hours=0.5, measurement_source="fixture")
    for _ in range(2):
        settle_action(db, process_id="process", action_key="opt", actual=actual)
    assert budget_usage(db, "process").cpu_hours == 0.5


def test_cannot_attach_running_job_to_previously_settled_action(tmp_path):
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.exploration_budget_store import (
        ActualCost,
        attach_existing_job,
        reserve_actions,
        settle_action,
    )

    db = budget_fixture(tmp_path, estimated_cpu_hours=1)
    reservation = reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    settle_action(
        db,
        process_id="process",
        action_key="opt",
        actual=ActualCost(terminal_state="done", allocated_cpu_hours=0, measurement_source="fixture"),
    )
    job = insert_compute_job(
        db,
        conversation_id="project",
        session_id="owner",
        path="/fixture",
        state="running",
        jobtype="xtb",
        node_id="fixture",
    )
    with pytest.raises(ValueError, match="settled"):
        attach_existing_job(db, reservation.reservation_id, "opt", job)


def test_reactivated_job_retains_reserved_allowance(tmp_path):
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.exploration_budget_store import (
        ActualCost,
        attach_existing_job,
        budget_usage,
        reserve_actions,
        settle_action,
    )

    db = budget_fixture(tmp_path, estimated_cpu_hours=1)
    reservation = reserve_actions(db, process_id="process", decision_id="d", estimates=[estimate()])
    job = insert_compute_job(
        db,
        conversation_id="project",
        session_id="owner",
        path="/fixture",
        state="done",
        jobtype="xtb",
        node_id="fixture",
    )
    attach_existing_job(db, reservation.reservation_id, "opt", job)
    settle_action(
        db,
        process_id="process",
        action_key="opt",
        actual=ActualCost(job_id=job, terminal_state="done", allocated_cpu_hours=0, measurement_source="fixture"),
    )
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='running' WHERE id=?", (job,))
    assert budget_usage(db, "process").cpu_hours == 1
    with pytest.raises(ValueError, match="budget"):
        reserve_actions(db, process_id="process", decision_id="next", estimates=[estimate("next")])


def test_release_only_unbound_future_actions_keeps_failed_job_cost(tmp_path):
    from cloudra.services.compute_store import insert_compute_job
    from cloudra.services.exploration_budget_store import (
        attach_existing_job,
        budget_usage,
        release_unbound_actions,
        reserve_actions,
    )

    db = budget_fixture(tmp_path, max_compute_actions=2)
    reservation = reserve_actions(
        db, process_id="process", decision_id="chain", estimates=[estimate("ts"), estimate("freq")]
    )
    job = insert_compute_job(
        db,
        conversation_id="project",
        session_id="owner",
        path="/fixture",
        state="failed",
        jobtype="orca",
        node_id="fixture",
    )
    attach_existing_job(db, reservation.reservation_id, "ts", job)
    released = release_unbound_actions(
        db, process_id="process", action_keys=["ts", "freq"], reason="candidate branch invalidated"
    )
    assert released == ["freq"]
    assert budget_usage(db, "process").compute_actions == 1
    next_job = insert_compute_job(
        db,
        conversation_id="project",
        session_id="owner",
        path="/fixture2",
        state="ready",
        jobtype="orca",
        node_id="fixture",
    )
    with pytest.raises(ValueError, match="released"):
        attach_existing_job(db, reservation.reservation_id, "freq", next_job)
    with db.connect() as con:
        assert con.execute("SELECT state FROM compute_jobs WHERE id=?", (job,)).fetchone()[0] == "failed"


def test_terminal_job_settlement_uses_allocated_runtime_and_keeps_failed_cost(tmp_path):
    from cloudra.services.exploration_budget_store import (
        ActualCost,
        ExplorationBudget,
        budget_usage,
        configure_budget,
        reserve_actions,
        settle_process_jobs,
    )
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process
    from tests.test_ts_pipeline_store import job_payload, payload

    db = ComputeDB(data_dir=tmp_path).init()
    process = create_process(db, request_key="settle", payload=payload())
    configure_budget(
        db,
        process_id=process["process_id"],
        project_id="project",
        owner_id="owner",
        budget=ExplorationBudget(source="explicit_user", max_compute_actions=1),
    )
    reserved = reserve_actions(db, process_id=process["process_id"], decision_id="d", estimates=[estimate("opt")])
    job = bind_stage_job(
        db,
        process_id=process["process_id"],
        declaration_revision=1,
        stage_key="opt",
        attempt=1,
        job_payload=job_payload(req_cpus=2),
        reservation_id=reserved.reservation_id,
        action_key="opt",
    )
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed',start_timestamp=100,end_timestamp=1900 WHERE id=?", (job,))
    settle_process_jobs(db, process["process_id"])
    settle_process_jobs(db, process["process_id"])
    usage = budget_usage(db, process["process_id"])
    assert usage.compute_actions == 1 and usage.cpu_hours == 1
    with db.connect() as con:
        data = ActualCost.model_validate_json(con.execute("SELECT actual FROM exploration_actions").fetchone()[0])
    assert data.terminal_state == "failed" and data.model_calls is None


def test_released_model_action_cannot_be_reactivated_by_same_reservation(tmp_path):
    from cloudra.services.exploration_budget_store import release_unbound_actions, reserve_actions

    db = budget_fixture(tmp_path, max_model_calls=1)
    model = estimate("model", action_kind="model", cpu_hours=None)
    reserve_actions(db, process_id="process", decision_id="d", estimates=[model])
    release_unbound_actions(db, process_id="process", action_keys=["model"], reason="request was not sent")
    with pytest.raises(ValueError, match="released"):
        reserve_actions(db, process_id="process", decision_id="d", estimates=[model])
