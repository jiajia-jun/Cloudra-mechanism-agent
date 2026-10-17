import asyncio
import json

import pytest
from pydantic_core import to_json

from cloudra.persistence.database import ComputeDB


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_existing_runs_drop_only_intervention_limits(tmp_path, asynchronous):
    from cloudra.services.ts_pipeline_store import bind_stage_job, create_process, get_process
    from cloudra.tools.core.ts_inputs import TsInput
    from cloudra.tools.core.ts_process import TsProcessRecord
    from tests.test_ts_pipeline_store import job_payload, payload

    def seed():
        db = ComputeDB(data_dir=tmp_path).init()
        declaration = payload(workspace_dir=str(tmp_path))
        declaration["input"]["conformers"]["guidance"]["distance_filters"] = [
            dict(atoms=[1, 2], min_ang=1e-6, max_ang=2.0)]
        state = create_process(db, request_key="old-run", payload=declaration)
        declaration = state["payload"]
        job_id = bind_stage_job(db, process_id=state["process_id"], declaration_revision=1,
            stage_key="ts_opt", attempt=1, job_payload=job_payload())
        record = TsProcessRecord(run_id="ts_0001", pipeline_id=state["process_id"],
            run_dir=str(tmp_path / "ts" / "ts_0001"), workspace_dir=str(tmp_path),
            owner_conversation_id="project", owner_session_id="owner",
            input=declaration["input"], intervention_count=2).model_dump(mode="json")
        limits = dict(source="old agent declaration", max_compute_actions=12,
            max_model_calls=None, max_interventions=2)
        record["input"]["execution"]["limits"] = limits
        record["attempt_history"] = [dict(declaration_revision=1, job_steps=[],
            stage_records=[], reason="old mapping fix", input=record["input"])]
        declaration["input"] = record["input"]
        with db.connect() as con:
            con.execute("UPDATE compute_jobs SET state='running' WHERE id=?", (job_id,))
            con.execute("UPDATE ts_pipeline_processes SET payload=?,record=? WHERE process_id=?",
                (to_json(declaration).decode(), to_json(record).decode(), state["process_id"]))
            con.execute("UPDATE ts_pipeline_declarations SET payload=? WHERE process_id=?",
                (to_json(record["input"]).decode(), state["process_id"]))
        return db.path, state["process_id"]

    path, pid = await asyncio.to_thread(seed)
    db = ComputeDB.from_path(path)
    if asynchronous:
        await db.ainit()
    else:
        await asyncio.to_thread(db.init)

    def verify():
        state = get_process(db, pid)
        current = TsProcessRecord.model_validate(state["record"])
        assert current.intervention_count == 2
        assert "max_interventions" not in current.input.execution.limits.model_dump()
        assert current.input.execution.limits.max_compute_actions == 12
        assert current.input.execution.limits.source == "old agent declaration"
        assert current.attempt_history[0].reason == "old mapping fix"
        with db.connect() as con:
            initial = json.loads(con.execute("SELECT payload FROM ts_pipeline_processes").fetchone()[0])
            saved = json.loads(con.execute("SELECT payload FROM ts_pipeline_declarations").fetchone()[0])
        for value in (initial["input"], saved, state["record"]["attempt_history"][0]["input"]):
            assert "max_interventions" not in value["execution"]["limits"]
            assert TsInput.model_validate(value) == current.input
        assert create_process(db, request_key="old-run", payload=initial) == state
        with db.connect() as con:
            assert con.execute("SELECT state FROM compute_jobs").fetchall() == [("running",)]
        before = state["record"]
        ComputeDB.from_path(path).init()
        assert get_process(db, pid)["record"] == before

    await asyncio.to_thread(verify)
