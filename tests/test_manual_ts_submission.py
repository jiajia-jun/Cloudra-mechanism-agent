"""Manual TS/IRC jobs must never reach the queue; the durable process still can."""

import asyncio
from types import SimpleNamespace

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_admission import AdmissionOutcome
from cloudra.services.compute_store import list_compute_jobs
from cloudra.tools.Chemtool.submit_compute_job import (
    SubmitComputeJob,
    SubmitComputeJob_input_schema,
)
from cloudra.tools.core.calculation_intent import inspect_input

TS_INPUTS = [
    ("gaussian", "#p b3lyp/def2svp Opt=(TS,CalcFC) Freq\n\n"),
    ("gaussian", "#p b3lyp/def2svp Opt=(CalcFC, TS)\n\n"),
    ("gaussian", "#p b3lyp/def2svp\n Opt = (CalcFC,\n TS) Freq\n\n"),
    ("gaussian", "#p hf/3-21g Opt=QST2\n\n"),
    ("gaussian", "#p hf/3-21g Opt=(QST3,CalcFC)\n\n"),
    ("gaussian", "#p hf/3-21g\n IRC=(CalcFC,Forward)\n\n"),
    ("gaussian", "#p hf/3-21g Freq\n\nnormal job\n\n--Link1--\n#p hf/3-21g IRC\n\n"),
    ("orca", "! B3LYP def2-SVP OptTS Freq\n"),
    ("orca", "! B3LYP def2-SVP NEB-TS\n"),
    ("orca", "! B3LYP def2-SVP Fast-NEB-TS\n"),
    ("orca", "! B3LYP def2-SVP ZOOM-NEB-TS\n"),
    ("orca", "! B3LYP def2-SVP ScanTS\n"),
    ("orca", "! B3LYP def2-SVP iRc\n"),
    ("orca", "! HF def2-SVP NEB\n%neb\n NEB_TS true\nend\n"),
    ("orca", "! HF def2-SVP NEB\n%neb NEB_TS true end\n"),
    ("orca", "! HF def2-SVP # note # OptTS\n"),
    ("orca", "! HF def2-SVP NEB\n%neb\n # note # NEB_TS true\nend\n"),
    ("orca", "! HF def2-SVP NEB\n%neb NEB_TS=true end\n"),
    ("orca", "! HF def2-SVP NEB\n%neb NEB_TS = true end\n"),
]


@pytest.fixture
def queue_admission(monkeypatch, tmp_path):
    # Replace only engine/node availability checks; keep the tool and real DB.
    def admit(**kwargs):
        return AdmissionOutcome(
            ok=True, workdir=str(tmp_path), node_id="local", scheduler="local",
        )

    monkeypatch.setattr("cloudra.tools.Chemtool.submit_compute_job.admit_job", admit)
    monkeypatch.setattr("cloudra.services.compute_admission.admit_job", admit)


@pytest.mark.parametrize("engine,content", TS_INPUTS)
@pytest.mark.parametrize("is_async", [True, False])
@pytest.mark.asyncio
async def test_manual_ts_irc_rejected_without_creating_job(
    tmp_path, queue_admission, engine, content, is_async,
):
    path = tmp_path / "ordinary_input.txt"
    path.write_text(content, encoding="utf-8")
    db = await ComputeDB().ainit()
    tool = SubmitComputeJob(subagent=SimpleNamespace(conversation_id="project"))
    result = await tool.tool_call(
        SubmitComputeJob_input_schema(
            input_file=str(path), job_type=engine, is_async=is_async,
        ), session=None,
    )
    assert not result.is_success
    assert result.job_id == -1
    assert "ts_prepare" in result.message
    assert "ts_resume" in result.message
    assert await asyncio.to_thread(list_compute_jobs, db) == []


@pytest.mark.parametrize("engine,content", [
    ("gaussian", "#p b3lyp/def2svp Opt Freq\n\nIRC TS QST2 title\n\n"),
    ("gaussian", "#p hf/3-21g Opt=(ModRedundant)\n\nscan\n\n"),
    ("gaussian", "#p hf/3-21g Opt SCRF=(SMD,Solvent=TSolvent)\n\n"),
    ("gaussian", '#p hf/3-21g External="/tmp/irc/driver" Opt\n\n'),
    ("gaussian", "#p hf/3-21g External='/tmp/irc/driver' Opt\n\n"),
    ("gaussian", "#p hf/3-21g Opt\n\n# IRC and Opt=TS are title text\n\n0 1\n"),
    ("orca", "# OptTS IRC NEB-TS are comments\n! B3LYP def2-SVP Opt Freq\n"),
    ("orca", "! B3LYP def2-SVP Opt # IRC OptTS are comments\n"),
    ("orca", "! HF def2-SVP NEB\n%neb NEB_TS false end\n"),
    ("orca", "! HF def2-SVP NEB\n%neb\n # NEB_TS true\n NEB_TS false\nend\n"),
    ("orca", "! HF def2-SVP NEB\n%neb NEB_TS true NEB_TS = false end\n"),
    ("orca", "! B3LYP def2-SVP\n%geom Scan\n B 0 1 = 1.5, 2.5, 5\n end\nend\n"),
    ("orca", "! B3LYP def2-SVP\n"),
])
@pytest.mark.asyncio
async def test_manual_non_ts_jobs_still_queue(tmp_path, queue_admission, engine, content):
    path = tmp_path / "ts_irc_qst2.inp"
    path.write_text(content, encoding="utf-8")
    tool = SubmitComputeJob(subagent=SimpleNamespace(conversation_id="project"))
    result = await tool.tool_call(
        SubmitComputeJob_input_schema(input_file=str(path), job_type=engine, is_async=True),
        session=None,
    )
    assert result.is_success
    jobs = await asyncio.to_thread(list_compute_jobs, ComputeDB())
    assert len(jobs) == 1
    assert jobs[0]["id"] == result.job_id


@pytest.mark.parametrize("engine,content", TS_INPUTS)
def test_input_inspection_recognizes_ts_irc(engine, content):
    assert inspect_input(content, engine=engine).tasks & {"ts_opt", "irc"}


@pytest.mark.parametrize("purpose,content", [
    ("ts_opt", "! B3LYP def2-SVP OptTS\n"),
    ("irc_forward", "! B3LYP def2-SVP IRC\n"),
])
def test_durable_process_can_queue_ts_and_irc(tmp_path, queue_admission, purpose, content):
    from cloudra.tools.core.ts_process import TsDeclaration, TsProcessRecord, _submit_step

    path = tmp_path / "workflow.inp"
    path.write_text(content, encoding="utf-8")
    record = TsProcessRecord(
        run_id="ts_0001", run_dir=str(tmp_path), workspace_dir=str(tmp_path),
        declaration=TsDeclaration(
            reactant_smiles="C", product_smiles="C", method="b3lyp/def2svp",
        ), owner_conversation_id="project", owner_session_id="agent-session",
    )
    error, job_id = _submit_step(record, purpose, str(path), "orca")
    assert error == ""
    jobs = list_compute_jobs(ComputeDB())
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["conversation_id"] == "project"
    assert jobs[0]["session_id"] == "agent-session"
