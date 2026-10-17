"""A delayed public resume replay is normalized against its accepted input."""

import asyncio
from copy import deepcopy

import pytest

from cloudra.persistence.database import ComputeDB
from cloudra.services.ts_pipeline_store import read_process_snapshot
from cloudra.tools.Chemtool.ts_search_process import (
    TsPrepare,
    TsPrepare_input_schema,
    TsResume,
    TsResume_input_schema,
)
from cloudra.tools.core.ts_inputs import CalculationRef, QmCalculation
from tests.test_ts_search_process_tools import invoke, owned_tool
from tests.ts_fixtures import calculation_input


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry", "ts_producer_authority")
@pytest.mark.parametrize("later_change", ["engine_definition", "stage_reference"])
async def test_accepted_resume_replay_uses_original_scan_engine_after_later_change(tmp_path, monkeypatch, later_change):
    value = calculation_input(
        reactant_smiles="O", product_smiles="O", method="HF/STO-3G",
        scan={"method": "HF/STO-3G", "scans": [
            {"atoms": [0, 1], "scan_start": 0.8, "scan_end": 1.0, "scan_steps": 2}]},
    )
    value.calculations = {
        "scan_profile": QmCalculation(engine="orca", method="HF", basis_set="STO-3G"),
        "gaussian_profile": QmCalculation(engine="gaussian", method="HF", basis_set="STO-3G"),
    }
    value.guess.calculation = CalculationRef(ref="scan_profile")
    from cloudra.services.compute_admission import AdmissionOutcome
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',
        lambda **_: AdmissionOutcome(ok=True, node_id='fixture', scheduler='local'))
    first = await invoke(owned_tool(TsPrepare, workspace=tmp_path),
                         TsPrepare_input_schema(input=value), call_id="prepare-native-scan")
    assert first.is_success, first.message
    assert first.blocked is None and first.status == "waiting"

    original = TsResume_input_schema(
        run_id=first.run_id, reason="Change the ORCA-native scan interval",
        changes={"guess": {"scans": [
            {"atoms": [0, 1], "scan_start": 0.9, "scan_end": 1.1, "scan_steps": 2}]}},
    )
    tool = owned_tool(TsResume, workspace=tmp_path)
    accepted = await invoke(tool, original, call_id="accepted-orca-coordinates")
    assert accepted.is_success, accepted.message
    assert accepted.receipt.input_revision == 2
    if later_change == "engine_definition":
        changes = {"calculations": {"scan_profile": {"replace": {
            "engine": "gaussian", "method": "HF", "basis_set": "STO-3G"}}}}
    else:
        changes = {"guess": {"calculation": {"replace": {"ref": "gaussian_profile"}}}}
    changed = await invoke(tool, TsResume_input_schema(
        run_id=first.run_id, reason="Change the later scan engine", changes=changes,
    ), call_id="later-gaussian-scan")
    assert changed.is_success, changed.message
    assert changed.receipt.input_revision == 3
    db = ComputeDB()
    before, _ = await asyncio.to_thread(read_process_snapshot, db, project_id="project",
                                        run_id=first.run_id, workspace_dir=str(tmp_path))
    before = deepcopy(before)

    def ledger_snapshot():
        with db.connect() as con:
            return (con.execute("SELECT * FROM ts_pipeline_declarations").fetchall(),
                    con.execute("SELECT * FROM ts_pipeline_revision_receipts").fetchall(),
                    con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0])

    before_ledger = await asyncio.to_thread(ledger_snapshot)

    replay = await invoke(tool, original, call_id="accepted-orca-coordinates")

    assert replay.is_success, replay.message
    assert replay.receipt == accepted.receipt
    after, _ = await asyncio.to_thread(read_process_snapshot, db, project_id="project",
                                       run_id=first.run_id, workspace_dir=str(tmp_path))
    assert after == before
    assert after["input"]["guess"]["scans"][0]["atoms"] == [0, 1]
    assert await asyncio.to_thread(ledger_snapshot) == before_ledger
    assert before_ledger[2] > 0
