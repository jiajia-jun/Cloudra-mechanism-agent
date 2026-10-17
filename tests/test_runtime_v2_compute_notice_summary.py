"""Automatic notices carry current facts; full TS records stay available on demand."""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from cloudra.runtime_v2.compute_notify import ComputeNotifyBroker
from tests.test_runtime_v2_compute_notify import _insert_terminal_job, _setup_core


@pytest.mark.asyncio
async def test_failed_ts_notice_is_independent_of_atom_tables_and_history(tmp_path, monkeypatch):
    core, project, coordinator = await _setup_core()
    path = tmp_path / "reactant_opt.inp"
    await asyncio.to_thread(path.write_text, "Recorded native input")
    reason = "ORCA geometry optimization did not converge after the allowed iterations"
    job = await asyncio.to_thread(_insert_terminal_job, project.id,
        session_id=coordinator.id, state="failed", last_error=reason, path=str(path), jobtype="orca")
    view = {
        "run_id": "ts_test", "stage": "refine", "status": "blocked", "result": None,
        "blocked": {"failure_class": "job_failed", "message": "Current endpoint optimization failed", "atom_details": []},
        "failed_attempt": {"purpose": "reactant_opt", "job_id": job, "diagnostics": []},
        "next": {"action": "resume", "required_inputs": ["verification.reactant_endpoint"]},
        "details_path": str(tmp_path / "process.json"), "run_dir": str(tmp_path),
        "structures": {}, "available_results": [], "methods": [], "usage": {},
    }
    monkeypatch.setattr("cloudra.tools.core.ts_pipeline_driver.handle_process_job_terminal",
        lambda *_: {"status": "blocked", "record": {}})
    monkeypatch.setattr("cloudra.tools.core.ts_state_view.recorded_notification_view", lambda *_: view)
    broker = ComputeNotifyBroker(core)
    await broker._poll_project(project.id)
    event = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})[-1]
    short = event.data["content"]
    assert reason in short
    assert "reactant_opt" in short and "ts_test" in short
    assert "NEXT:" in short
    assert str(tmp_path / "process.json") in short
    assert "TS state:" not in short
    assert "revision" not in short and "sha256" not in short
    assert "atom_details" not in short

    old_count = len(core.event_log.query_session(coordinator.id, types={"agent.message_injected"}))
    rich = deepcopy(view)
    rich.update(structures={"reactant": {"atoms": ["atom-table-sentinel"] * 5000}},
        available_results=[{"path": "old-history-sentinel"}] * 1000,
        methods=[{"configuration": "old-method-sentinel"}] * 1000,
        usage={"jobs": ["usage-history-sentinel"] * 1000})
    rich["blocked"]["atom_details"] = ["native-log-history-sentinel"] * 1000
    rich["failed_attempt"]["diagnostics"] = ["native-log-history-sentinel"] * 1000
    monkeypatch.setattr("cloudra.tools.core.ts_state_view.recorded_notification_view", lambda *_: rich)
    # Replay the same delivery after an ack retry; no extra notice is created.
    await broker._deliver(project.id, task_id=job, state="failed", session_id=coordinator.id)
    assert len(core.event_log.query_session(coordinator.id, types={"agent.message_injected"})) == old_count
    # A second job with the same input/current facts cannot dump the extra state.
    job2 = await asyncio.to_thread(_insert_terminal_job, project.id,
        session_id=coordinator.id, state="failed", last_error=reason, path=str(path), jobtype="orca")
    rich["failed_attempt"]["job_id"] = job2
    await broker._poll_project(project.id)
    long = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})[-1].data["content"]
    assert abs(len(long) - len(short)) <= len(str(job2)) - len(str(job)) + 50
    for sentinel in ("atom-table-sentinel", "old-history-sentinel", "old-method-sentinel", "native-log-history-sentinel"):
        assert sentinel not in long


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome,verified", [("candidate_only", False), ("verified", True)])
@pytest.mark.parametrize("export_available", [True, False])
async def test_ts_completion_notice_uses_recorded_scientific_verdict(tmp_path, monkeypatch, outcome, verified, export_available):
    core, project, coordinator = await _setup_core()
    await asyncio.to_thread(_insert_terminal_job, project.id, session_id=coordinator.id, path="")
    view = {"run_id": "ts_test", "stage": "verdict", "status": "ended",
        "result": {"outcome": outcome, "verified": verified, "reason": "Recorded direction proof", "evidence_refs": []},
        "message": "Recorded direction proof", "next": {"action": "resume"},
        "run_dir": str(tmp_path), "details_path": str(tmp_path / "process.json") if export_available else ""}
    monkeypatch.setattr("cloudra.tools.core.ts_pipeline_driver.handle_process_job_terminal",
        lambda *_: {"status": "ended", "record": {}})
    monkeypatch.setattr("cloudra.tools.core.ts_state_view.recorded_notification_view", lambda *_: view)
    await ComputeNotifyBroker(core)._poll_project(project.id)
    content = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})[-1].data["content"]
    assert outcome in content
    assert f"verified={str(verified).lower()}" in content
    assert content.count("Recorded direction proof") == 1
    assert "NEXT:" in content
    assert "TS state:" not in content
    if not export_available:
        assert "ts_inspect" in content
        assert "process.json" not in content


@pytest.mark.asyncio
async def test_ordinary_done_notice_keeps_native_log_and_next_without_claiming_science(tmp_path):
    core, project, coordinator = await _setup_core()
    path = tmp_path / "opt.inp"
    await asyncio.to_thread(path.write_text, "Recorded native input")
    job = await asyncio.to_thread(_insert_terminal_job, project.id,
        session_id=coordinator.id, path=str(path), jobtype="orca")
    await ComputeNotifyBroker(core)._poll_project(project.id)
    content = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})[-1].data["content"]
    assert f"Job {job}," in content and "state=done" in content
    assert "log_parser" in content and "NEXT:" in content
    assert path.name in content and str(path.with_suffix('.out')) in content
    assert "scientific verification" in content
    assert "sha256" not in content and "art_" not in content


@pytest.mark.asyncio
@pytest.mark.parametrize("engine,atoms", [("orca", "0,2"), ("gaussian", "1,3"), ("xtb", "1,3")])
async def test_completed_scan_notice_keeps_reaction_window_and_no_peak_observation(tmp_path, monkeypatch, engine, atoms):
    core, project, coordinator = await _setup_core()
    path = tmp_path / "scan.inp"
    await asyncio.to_thread(path.write_text, "Recorded native input")
    job = await asyncio.to_thread(_insert_terminal_job, project.id,
        session_id=coordinator.id, state="done", path=str(path), jobtype=engine)
    record = {"format_version": 7, "input": {
        "reaction": {"reactant_smiles": "[CH2-][PH3+].C=O", "product_smiles": "C=C.O=[PH3]",
            "charge": 0, "multiplicity": 1, "reaction_center": [[0, 2]]},
        "guess": {"kind": "scan", "calculation": {"engine": engine},
            "scans": [{"coord_type": "bond", "atoms": [0, 2], "scan_start": 2.5,
                "scan_end": 1.4, "scan_steps": 14}]}}}
    view = {"run_id": "ts_test", "stage": "guess", "status": "blocked", "result": None,
        "blocked": {"failure_class": "scan_no_candidate", "message": "No usable internal peak was found"},
        "failed_attempt": {"job_id": job, "purpose": "scan"},
        "structures": {"reactant": {"components": 2, "atom_count": 11},
            "product": {"components": 2, "atom_count": 11}},
        "details_path": str(tmp_path / "process.json")}
    monkeypatch.setattr("cloudra.tools.core.ts_pipeline_driver.handle_process_job_terminal",
        lambda *_: {"status": "blocked", "record": record})
    monkeypatch.setattr("cloudra.tools.core.ts_state_view.recorded_notification_view", lambda *_: view)
    await ComputeNotifyBroker(core)._poll_project(project.id)
    content = core.event_log.query_session(coordinator.id, types={"agent.message_injected"})[-1].data["content"]
    assert "Compute Event:" in content and "state=done" in content
    assert "Reaction Window:" in content
    assert "[CH2-][PH3+].C=O" in content and "C=C.O=[PH3]" in content
    assert "charge=0" in content and "multiplicity=1" in content
    assert "11 atoms" in content and "2 components" in content
    assert "centres (1-based): 1-3" in content
    assert f"bond({atoms})" in content and "2.5" in content and "1.4" in content and "scan_steps=14" in content
    assert "scan declaration" in content  # Accepted inputs are not reparsed native observations.
    assert "Physical Reality:" in content and "No usable internal peak was found" in content
    assert "state=blocked" not in content and "outcome=blocked" not in content
    assert "NEXT:" in content and "orientation" in content and "sequential" in content and "NEB" in content
    assert "manual interpolation" not in content


@pytest.mark.asyncio
async def test_scan_window_omits_unknown_start_and_resolves_recorded_calculation_reference(tmp_path):
    core, project, coordinator = await _setup_core()
    job = await asyncio.to_thread(_insert_terminal_job, project.id, session_id=coordinator.id, path="")
    record = {"format_version": 7, "input": {
        "reaction": {"reactant_smiles": "CC", "product_smiles": "C=C", "charge": 0, "multiplicity": 1,
                     "reaction_center": [[0, 1]]},
        "calculations": {"scan": {"engine": "orca", "method": "private-configuration-sentinel"}},
        "guess": {"kind": "scan", "calculation": {"ref": "scan"},
                  "scans": [{"coord_type": "bond", "atoms": [0, 1], "scan_end": 2.0, "scan_steps": 10}]}},
        "scan_step": {"purpose": "scan", "job_id": job}, "effective_reaction_center": [[1, 2]]}
    view = {"run_id": "ts_test", "stage": "guess", "status": "blocked", "result": None,
            "blocked": {"failure_class": "scan_no_candidate", "message": "No internal scan peak"}}
    content = await ComputeNotifyBroker(core)._content_for(job, "done", view=view, record=record)
    assert "scan declaration (orca, 0-based): bond(0,1) end=2.0" in content
    assert "centres (1-based): 2-3" in content
    assert "→" not in content
    assert "atoms" not in content and "components" not in content
    assert "private-configuration-sentinel" not in content


@pytest.mark.asyncio
async def test_new_notice_does_not_relabel_old_failed_attempt_as_current_job(tmp_path):
    core, project, coordinator = await _setup_core()
    job = await asyncio.to_thread(_insert_terminal_job, project.id, session_id=coordinator.id, path="")
    view = {"run_id": "ts_test", "stage": "verdict", "status": "ended",
            "result": {"outcome": "candidate_only", "verified": False, "reason": "IRC endpoints differ from declared minima"},
            "failed_attempt": {"job_id": job + 1, "purpose": "old_failure_step"}}
    content = await ComputeNotifyBroker(core)._content_for(job, "done", view=view)
    assert "old_failure_step" not in content
    assert "IRC endpoints differ from declared minima" in content
    assert "verified=false" in content and "intended bond changes" in content
    assert "sequential scans" not in content and "GSM/NEB" not in content
