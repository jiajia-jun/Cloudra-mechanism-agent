from pathlib import Path

import pytest

from tests.test_ts_pipeline_driver import waiting_process


def test_validation_budget_shortfall_blocks_before_ts_submission(tmp_path, monkeypatch):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.exploration_budget_store import ExplorationBudget, budget_usage, configure_budget
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core.ts_process import TsProcessRecord, _submit_step

    db, pid, _ = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.exploration_budget = ExplorationBudget(source="explicit_user", max_compute_actions=6)
    configure_budget(db, process_id=pid, project_id="project", owner_id="owner", budget=record.exploration_budget)
    path = tmp_path / "new-ts.inp"
    path.write_text("fixture")
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    error, job = _submit_step(record, "ts_opt", str(path), "orca")
    assert job == -1
    assert "budget" in error
    assert budget_usage(db, pid).compute_actions == 0
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1


def test_failed_bound_stage_is_retained_when_declaration_changes(tmp_path):
    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_process import TsAdjustment, TsProcessRecord, resume

    db, pid, job = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.waiting_for = ""
    record.blocked = ts_process.TsBlocked(stage="refine", failure_class="job_failed", message="recorded failure")
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (job,))
    from cloudra.services.ts_pipeline_store import save_process_record

    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    # Mapping changes invalidate downstream work, never the original job row.
    result = resume(record, TsAdjustment(atom_map=[0, 1]))
    assert result.declaration_revision == 2
    assert result.attempt_history[0].job_steps[0].job_id == job
    with db.connect() as con:
        assert con.execute("SELECT state FROM compute_jobs WHERE id=?", (job,)).fetchone()[0] == "failed"


@pytest.mark.parametrize("terminal", [None, "candidate_only"])
def test_candidate_decision_is_scoped_recorded_and_switch_keeps_map_and_old_job(tmp_path, monkeypatch, terminal):
    from cloudra.services.conformer_store import put_candidate, put_region_snapshot
    from cloudra.services.ts_pipeline_store import get_process, save_process_record
    from cloudra.tools.core.conformer_cards import build_region_cards
    from cloudra.tools.core.conformer_catalog import Qualification, content_digest
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates
    from cloudra.tools.core.conformer_selection import SelectionDecision
    from cloudra.tools.core.ts_process import TsAdjustment, TsBlocked, TsProcessRecord, TsStageRecord, resume
    from tests.test_conformer_catalog import make_candidate

    db, pid, job = waiting_process(tmp_path)
    candidates = [
        make_candidate(
            tmp_path,
            geometry_ref="",
            positions=[[0, 0, 0], [x, 0, 0]],
            qualification=Qualification(status="qualified", evidence_refs=["synthetic_qualification"]),
        )
        for x in [1.2, 2.2]
    ]
    for candidate in candidates:
        put_candidate(db, candidate)
    snapshot = partition_candidates(
        candidates, RegionConfig(descriptor_specs=[DescriptorSpec(kind="distance", stable_atom_ids=["C1", "O1"])])
    )
    put_region_snapshot(db, snapshot, project_id="project", owner_id="owner")
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.catalog_id = "cat"
    record.partition_revision = snapshot.revision
    record.selected_candidate_id = candidates[0].candidate_id
    record.terminal = terminal
    record.waiting_for = ""
    record.blocked = TsBlocked(stage="refine", failure_class="wrong_mode", message="fixture wrong mode")
    record.stage_records = [
        TsStageRecord(stage="build", status="done", detail="original"),
        TsStageRecord(stage="map", status="done", detail="original"),
    ]
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (job,))
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    card = next(
        c for c in build_region_cards(snapshot, candidates, []) if candidates[1].candidate_id in c.candidate_ids
    )
    decision = SelectionDecision(
        decision_id="switch",
        catalog_id="cat",
        partition_revision=snapshot.revision,
        declaration_hash=content_digest(record.declaration.model_dump(mode="json")),
        candidate_id=candidates[1].candidate_id,
        region_id=card.region_id,
        reason="try another distance region after wrong mode",
        evidence_refs=card.evidence_refs,
    )
    monkeypatch.setattr("cloudra.tools.core.ts_process.advance", lambda r: r)
    result = resume(record, TsAdjustment(selection_decision=decision))
    assert result.stage == "assemble" and result.selected_candidate_id == candidates[1].candidate_id
    assert result.terminal is None
    assert result.stage_record("map").detail == "original"
    assert result.attempt_history[0].job_steps[0].job_id == job
    assert Path(result.current_seed_xyz_path).is_file()
    again = resume(result, TsAdjustment(selection_decision=decision))
    assert len(again.attempt_history) == 1 and again.selection_decision_id == "switch"
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1


@pytest.mark.parametrize("crash", [False, True])
def test_endpoint_only_retry_preserves_ts_frequency_irc_and_other_endpoint(tmp_path, monkeypatch, crash):
    from cloudra.services.compute_admission import AdmissionOutcome
    from cloudra.services.ts_pipeline_store import bind_stage_job, get_process, save_process_record
    from cloudra.tools.core.structure_builder import (
        BuildStrategy,
        PreparationRequest,
        StructureInput,
        prepare_structure,
    )
    from cloudra.tools.core.ts_process import TsAdjustment, TsBlocked, TsJobStep, TsProcessRecord, resume
    from tests.test_ts_pipeline_store import job_payload

    db, pid, tsjob = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.declaration.reactant_smiles = "O"
    record.declaration.product_smiles = "CC"
    prepared = prepare_structure(
        PreparationRequest(
            structure=StructureInput(kind="smiles", value="O"),
            output_dir=str(Path(record.run_dir) / "build/reactant"),
            strategy=BuildStrategy(embed=True, optimize=False),
        )
    )
    record.current_seed_xyz_path = prepared.components[0].xyz_path
    record.current_seed_mol_path = prepared.components[0].mol_path
    jobs = {}
    for purpose, state in [
        ("frequency", "done"),
        ("irc", "done"),
        ("product_opt", "done"),
        ("product_frequency", "done"),
        ("reactant_opt", "failed"),
    ]:
        data = job_payload(path=f"/fixture/{purpose}.inp")
        job = bind_stage_job(db, process_id=pid, declaration_revision=1, stage_key=purpose, attempt=1, job_payload=data)
        with db.connect() as con:
            con.execute("UPDATE compute_jobs SET state=? WHERE id=?", (state, job))
        record.job_steps.append(TsJobStep(purpose=purpose, job_id=job, input_path=data["path"], state=state))
        jobs[purpose] = job
    record.waiting_for = ""
    record.blocked = TsBlocked(stage="refine", failure_class="job_failed", message="failed endpoint")
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    seed = tmp_path / "new-water.xyz"
    seed.write_text("3\nsynthetic alternative seed\nO 0 0 0\nH 0.97 0 0\nH -0.25 0.94 0\n")
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    adjustment = TsAdjustment(
        endpoint_retry={
            "retry_id": "retry-water",
            "role": "reactant",
            "seed_xyz_path": str(seed),
            "reason": "alternative qualified endpoint geometry",
        }
    )
    if crash:
        from cloudra.tools.core import ts_process
        from cloudra.tools.core.ts_pipeline_driver import advance_process

        dispatch = ts_process._advance_endpoint_retry

        def die(*args):
            raise RuntimeError("crash after intent checkpoint")

        monkeypatch.setattr(ts_process, "_advance_endpoint_retry", die)
        with pytest.raises(RuntimeError, match="crash after intent"):
            resume(record, adjustment)
        monkeypatch.setattr(ts_process, "_advance_endpoint_retry", dispatch)
        result = TsProcessRecord.model_validate(advance_process(db, pid)["record"])
    else:
        result = resume(record, adjustment)
    again = resume(
        result,
        TsAdjustment(
            endpoint_retry={
                "retry_id": "retry-water",
                "role": "reactant",
                "seed_xyz_path": str(seed),
                "reason": "alternative qualified endpoint geometry",
            }
        ),
    )
    assert again.waiting_for == result.waiting_for
    assert result.waiting_for.startswith("job:") and result.job_steps[-1].purpose == "reactant_opt"
    assert result.job_steps[-1].job_id != jobs["reactant_opt"]
    kept = {s.purpose: s.job_id for s in result.job_steps}
    assert kept["frequency"] == jobs["frequency"] and kept["irc"] == jobs["irc"]
    assert kept["product_frequency"] == jobs["product_frequency"]
    assert result.attempt_history[-1].job_steps[-1].job_id == jobs["reactant_opt"]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 7


def test_budget_change_only_preserves_waiting_geometry_and_does_not_raise_cap(tmp_path):
    from cloudra.services.exploration_budget_store import ExplorationBudget, configure_budget
    from cloudra.services.ts_pipeline_store import get_process, save_process_record
    from cloudra.tools.core.ts_process import TsAdjustment, TsProcessRecord, resume

    db, pid, job = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.current_seed_xyz_path = "/fixture/retained.xyz"
    record.exploration_budget = ExplorationBudget(source="explicit_user", max_compute_actions=10)
    configure_budget(db, process_id=pid, project_id="project", owner_id="owner", budget=record.exploration_budget)
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    updated = resume(record, TsAdjustment(exploration_budget={"source": "explicit_user", "max_compute_actions": 8}))
    assert updated.waiting_for == f"job:{job}" and updated.current_seed_xyz_path == record.current_seed_xyz_path
    assert updated.declaration_revision == record.declaration_revision and updated.stage == record.stage
    assert updated.exploration_budget.max_compute_actions == 8
    with pytest.raises(ValueError, match="raise"):
        resume(updated, TsAdjustment(exploration_budget={"source": "explicit_user", "max_compute_actions": 12}))
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1


def test_partition_revision_update_preserves_seed_and_rejects_incomplete_snapshot(tmp_path, monkeypatch):
    from cloudra.services.conformer_store import put_candidate, put_region_snapshot
    from cloudra.services.ts_pipeline_store import get_process, save_process_record
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates
    from cloudra.tools.core.ts_process import TsAdjustment, TsBlocked, TsProcessRecord, resume
    from tests.test_conformer_catalog import make_candidate

    db, pid, _ = waiting_process(tmp_path)
    a = make_candidate(tmp_path)
    b = make_candidate(tmp_path, generator="second", geometry_ref="", positions=[[0, 0, 0], [2, 0, 0]])
    for candidate in (a, b):
        put_candidate(db, candidate)
    config = RegionConfig(descriptor_specs=[DescriptorSpec(kind="distance", stable_atom_ids=["C1", "O1"])])
    old = partition_candidates([a, b], config)
    new = partition_candidates([a, b], RegionConfig(version=2, descriptor_specs=config.descriptor_specs), previous=old)
    bad = partition_candidates([a], RegionConfig(version=3, descriptor_specs=config.descriptor_specs), previous=old)
    for snapshot in (old, new, bad):
        put_region_snapshot(db, snapshot, project_id="project", owner_id="owner")
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    record.catalog_id = "cat"
    record.partition_revision = old.revision
    record.selected_candidate_id = a.candidate_id
    record.current_seed_xyz_path = a.geometry_ref
    record.waiting_for = ""
    record.blocked = TsBlocked(stage="build", failure_class="partition_revision_needed", message="new evidence needed")
    save_process_record(db, process_id=pid, record=record.model_dump(mode="json"))
    monkeypatch.setattr("cloudra.tools.core.ts_process.advance", lambda r: r)
    with pytest.raises(ValueError, match="members"):
        resume(record, TsAdjustment(partition_revision=bad.revision))
    updated = resume(record, TsAdjustment(partition_revision=new.revision))
    assert updated.current_seed_xyz_path == a.geometry_ref and updated.selected_candidate_id == a.candidate_id
    assert updated.declaration_revision == 1 and updated.partition_revision == new.revision


@pytest.mark.parametrize("role", ["reactant", "product"])
def test_formal_endpoint_rejects_mirrored_declared_stereochemistry(tmp_path, monkeypatch, role):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.services.ts_pipeline_store import get_process
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_process import TsProcessRecord

    db, pid, _ = waiting_process(tmp_path)
    record = TsProcessRecord.model_validate(get_process(db, pid)["record"])
    smiles = "F[C@](Cl)(Br)I"
    record.declaration.reactant_smiles = smiles
    record.declaration.product_smiles = smiles
    graph = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(graph, randomSeed=11) == 0
    positions = graph.GetConformer().GetPositions().tolist()
    symbols = [a.GetSymbol() for a in graph.GetAtoms()]
    mol_path = tmp_path / "endpoint.mol"
    mol_path.write_text(Chem.MolToMolBlock(graph))
    monkeypatch.setattr(ts_process, "_read_built_xyz", lambda *args: (symbols, positions, "", str(mol_path)))
    remap = list(reversed(range(len(symbols)))) if role == "product" else list(range(len(symbols)))
    record.declaration.atom_map = remap

    def ordered(points):
        return (
            [symbols[remap.index(i)] for i in range(len(symbols))],
            [points[remap.index(i)] for i in range(len(symbols))],
        )

    assert ts_process._endpoint_identity_error(record, role, ordered(positions)) == ""
    mirrored = [[-p[0], p[1], p[2]] for p in positions]
    assert "stereochemistry" in ts_process._endpoint_identity_error(record, role, ordered(mirrored))
