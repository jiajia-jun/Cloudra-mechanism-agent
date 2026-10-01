from types import SimpleNamespace

import pytest

pytest.importorskip("rdkit", reason="selected candidate preparation requires RDKit (chem extra)")

from cloudra.services.compute_admission import AdmissionOutcome
from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema
from cloudra.tools.core.ts_process import TsDeclaration, TsStartRequest, start


def test_catalog_prepare_queues_only_selected_optimizer_and_response_retry_reuses_job(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from cloudra.persistence.database import ComputeDB

    tool = ConformerSearch()
    tool.subagent = SimpleNamespace(conversation_id="project", id="owner")
    catalog_dir = tmp_path / "conformers"
    catalog_dir.mkdir()
    catalog = tool._run_regions(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=6, catalog_mode="regions"), str(catalog_dir)
    )
    snapshot = json.loads(Path(catalog.region_snapshot_path).read_text())
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    request = TsStartRequest(
        workspace_dir=str(tmp_path),
        owner_conversation_id="project",
        owner_session_id="owner",
        request_key="selected",
        declaration=TsDeclaration(reactant_smiles="CCCC", product_smiles="CC(C)C", method="b3lyp/def2svp"),
        candidate_catalog={"catalog_id": catalog.catalog_id, "partition_revision": snapshot["revision"]},
    )
    first = start(request)
    second = start(request)
    assert first.stage == "build" and first.waiting_for.startswith("job:")
    assert first.selected_candidate_id in snapshot["descriptors"]
    assert second.waiting_for == first.waiting_for and second.selected_candidate_id == first.selected_candidate_id
    with ComputeDB().connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 1
        assert con.execute("SELECT jobtype FROM compute_jobs").fetchone()[0] == "chem_task"


@pytest.mark.parametrize("retry_product", [False, True])
def test_finished_selected_optimizer_continues_to_one_product_optimizer(tmp_path, monkeypatch, retry_product):
    import json
    from pathlib import Path

    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime.chem_task import ChemTask, result_path
    from cloudra.services.conformer_store import list_candidates
    from cloudra.tools.core.conformer_catalog import content_digest
    from cloudra.tools.core.ts_pipeline_driver import advance_process

    tool = ConformerSearch()
    tool.subagent = SimpleNamespace(conversation_id="project", id="owner")
    out = tmp_path / "confs"
    out.mkdir()
    catalog = tool._run_regions(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=4, catalog_mode="regions"), str(out)
    )
    snapshot = json.loads(Path(catalog.region_snapshot_path).read_text())
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    record = start(
        TsStartRequest(
            workspace_dir=str(tmp_path),
            owner_conversation_id="project",
            owner_session_id="owner",
            declaration=TsDeclaration(reactant_smiles="CCCC", product_smiles="CC(C)C", method="b3lyp/def2svp"),
            candidate_catalog={"catalog_id": catalog.catalog_id, "partition_revision": snapshot["revision"]},
        )
    )
    step = record.job_steps[-1]
    candidate = next(
        c
        for c in list_candidates(ComputeDB(), catalog.catalog_id, project_id="project", owner_id="owner")
        if c.candidate_id == record.selected_candidate_id
    )
    task = ChemTask.model_validate_json(Path(step.input_path).read_text())
    Path(result_path(step.input_path)).write_text(
        json.dumps(
            dict(
                manifest_digest=content_digest(task.model_dump()),
                process_exit_code=0,
                result=dict(
                    returncode=0,
                    normal_termination=True,
                    optimization_converged=True,
                    symbols=candidate.symbols,
                    positions=candidate.positions,
                    energy_hartree=-1.0,
                    log_file=str(tmp_path / "synthetic.out"),
                ),
            )
        )
    )
    with ComputeDB().connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (step.job_id,))
    first = advance_process(ComputeDB(), record.pipeline_id)
    second = advance_process(ComputeDB(), record.pipeline_id)
    assert first["record"]["blocked"] is None
    assert first["record"]["job_steps"][-1]["purpose"] == "product_seed_opt"
    assert second["record"]["waiting_for"] == first["record"]["waiting_for"]
    with ComputeDB().connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 2
    if retry_product:
        from cloudra.tools.core.ts_process import TsAdjustment, TsProcessRecord, resume

        product_step = first["record"]["job_steps"][-1]
        task = ChemTask.model_validate_json(Path(product_step["input_path"]).read_text())
        Path(result_path(product_step["input_path"])).write_text(
            json.dumps(
                dict(
                    manifest_digest=content_digest(task.model_dump()),
                    process_exit_code=0,
                    result=dict(
                        returncode=0,
                        normal_termination=True,
                        optimization_converged=False,
                        symbols=[],
                        positions=[],
                        log_file="synthetic.out",
                    ),
                )
            )
        )
        with ComputeDB().connect() as con:
            con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (product_step["job_id"],))
        failed = TsProcessRecord.model_validate(advance_process(ComputeDB(), record.pipeline_id)["record"])
        raw = next(
            c
            for c in list_candidates(ComputeDB(), catalog.catalog_id, project_id="project", owner_id="owner")
            if c.candidate_id == failed.product_seed_candidate_id
        )
        replacement = tmp_path / "product-new.xyz"
        replacement.write_text(
            str(len(raw.symbols))
            + "\nsynthetic shifted product seed\n"
            + "\n".join(f"{symbol} {p[0] + 0.1} {p[1]} {p[2]}" for symbol, p in zip(raw.symbols, raw.positions))
            + "\n"
        )
        adjustment = TsAdjustment(
            endpoint_seed_retry={
                "retry_id": "product-retry",
                "role": "product",
                "seed_xyz_path": str(replacement),
                "reason": "Explicit alternate geometry after native nonconvergence",
            }
        )
        resumed = resume(failed, adjustment)
        repeated = resume(resumed, adjustment)
        assert repeated.waiting_for == resumed.waiting_for
        assert resumed.current_seed_xyz_path == failed.current_seed_xyz_path
        assert resumed.job_steps[-1].purpose == "product_seed_opt"
        assert resumed.job_steps[-1].job_id != product_step["job_id"]
        with ComputeDB().connect() as con:
            assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 3


def test_two_native_seed_checkpoints_reach_queued_path_with_no_reoptimization(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime.chem_task import ChemTask, result_path
    from cloudra.services.conformer_store import list_candidates
    from cloudra.tools.core.conformer_catalog import content_digest
    from cloudra.tools.core.ts_pipeline_driver import advance_process
    from cloudra.tools.core.ts_process import TsAdjustment, TsProcessRecord, resume

    tool = ConformerSearch()
    tool.subagent = SimpleNamespace(conversation_id="project", id="owner")
    out = tmp_path / "confs"
    out.mkdir()
    catalog = tool._run_regions(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=4, catalog_mode="regions"), str(out)
    )
    snapshot = json.loads(Path(catalog.region_snapshot_path).read_text())
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    record = start(
        TsStartRequest(
            workspace_dir=str(tmp_path),
            owner_conversation_id="project",
            owner_session_id="owner",
            declaration=TsDeclaration(reactant_smiles="CCCC", product_smiles="CC(C)C", method="b3lyp/def2svp"),
            candidate_catalog={"catalog_id": catalog.catalog_id, "partition_revision": snapshot["revision"]},
        )
    )
    for phase in ("candidate_opt", "product_seed_opt"):
        step = record.job_steps[-1]
        assert step.purpose == phase
        target = record.selected_candidate_id if phase == "candidate_opt" else record.product_seed_candidate_id
        candidate = next(
            c
            for c in list_candidates(ComputeDB(), catalog.catalog_id, project_id="project", owner_id="owner")
            if c.candidate_id == target
        )
        task = ChemTask.model_validate_json(Path(step.input_path).read_text())
        Path(result_path(step.input_path)).write_text(
            json.dumps(
                dict(
                    manifest_digest=content_digest(task.model_dump()),
                    process_exit_code=0,
                    result=dict(
                        returncode=0,
                        normal_termination=True,
                        optimization_converged=True,
                        symbols=candidate.symbols,
                        positions=candidate.positions,
                        energy_hartree=-1.0,
                        log_file=str(tmp_path / "synthetic.out"),
                    ),
                )
            )
        )
        with ComputeDB().connect() as con:
            con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (step.job_id,))
        record = TsProcessRecord.model_validate(advance_process(ComputeDB(), record.pipeline_id)["record"])
    assert record.blocked.stage == "map"
    product_path = record.product_seed_xyz_path
    record = resume(record, TsAdjustment(atom_map=list(range(14))))
    assert record.blocked is None and record.stage == "guess"
    assert record.job_steps[-1].purpose == "path" and record.waiting_for
    assert record.product_seed_xyz_path == product_path
    with ComputeDB().connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 3


def test_supplement_sampling_is_budgeted_queued_archived_and_idempotent(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime.chem_task import run_task
    from cloudra.services.conformer_store import get_region_snapshot, list_candidates
    from cloudra.services.exploration_budget_store import ExplorationBudget, budget_usage
    from cloudra.services.ts_pipeline_store import save_process_record
    from cloudra.tools.core.conformer_cards import build_region_cards
    from cloudra.tools.core.conformer_catalog import content_digest
    from cloudra.tools.core.conformer_selection import SamplingRequest, SelectionDecision
    from cloudra.tools.core.ts_pipeline_driver import advance_process
    from cloudra.tools.core.ts_process import TsAdjustment, TsBlocked, TsProcessRecord, resume

    db = ComputeDB()
    tool = ConformerSearch()
    tool.subagent = SimpleNamespace(conversation_id="project", id="owner")
    out = tmp_path / "confs"
    out.mkdir()
    catalog = tool._run_regions(
        ConformerSearch_input_schema(smiles="CCCC", num_confs=2, catalog_mode="regions"), str(out)
    )
    revision = json.loads(Path(catalog.region_snapshot_path).read_text())["revision"]
    monkeypatch.setattr(
        "cloudra.services.compute_admission.admit_job",
        lambda **_: AdmissionOutcome(ok=True, node_id="fixture", scheduler="local"),
    )
    record = start(
        TsStartRequest(
            workspace_dir=str(tmp_path),
            owner_conversation_id="project",
            owner_session_id="owner",
            declaration=TsDeclaration(reactant_smiles="CCCC", product_smiles="CC(C)C", method="b3lyp/def2svp"),
            candidate_catalog={"catalog_id": catalog.catalog_id, "partition_revision": revision},
            exploration_budget=ExplorationBudget(source="explicit_user", max_compute_actions=2),
        )
    )
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='failed' WHERE id=?", (record.job_steps[-1].job_id,))
    record.waiting_for = ""
    record.blocked = TsBlocked(stage="build", failure_class="decision_needed", message="synthetic failure")
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode="json"))
    candidates = list_candidates(db, catalog.catalog_id, project_id="project", owner_id="owner")
    snapshot = get_region_snapshot(db, catalog.catalog_id, revision, project_id="project", owner_id="owner")
    cards = build_region_cards(snapshot, candidates, [])
    decision = SelectionDecision(
        decision_id="supplement",
        catalog_id=catalog.catalog_id,
        partition_revision=revision,
        declaration_hash=content_digest(record.declaration.model_dump(mode="json")),
        action="supplement_sampling",
        reason="Sample missing structural coverage",
        evidence_refs=cards[0].evidence_refs,
        sampling=SamplingRequest(method="ETKDGv3", count=3, seed=72),
    )
    first = resume(record, TsAdjustment(selection_decision=decision))
    repeated = resume(first, TsAdjustment(selection_decision=decision))
    assert repeated.waiting_for == first.waiting_for
    step = first.job_steps[-1]
    assert step.purpose == "sampling" and budget_usage(db, record.pipeline_id).compute_actions == 2
    assert run_task(step.input_path) == 0  # RDKit only; no engine invocation.
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (step.job_id,))
    final = TsProcessRecord.model_validate(advance_process(db, record.pipeline_id)["record"])
    assert final.blocked.failure_class == "decision_needed" and final.partition_revision != revision
    after = list_candidates(db, catalog.catalog_id, project_id="project", owner_id="owner")
    assert len(after) == len(candidates) + 3
    assert all(not c.energies for c in after)
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM compute_jobs").fetchone()[0] == 2


def test_windowed_selected_candidate_uses_derivative_queue_and_archives_all_jobs(tmp_path,monkeypatch):
    import json
    from pathlib import Path

    import numpy as np

    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime.chem_task import ChemTask, result_path
    from cloudra.services.conformer_store import list_candidates
    from cloudra.tools.core.conformer_catalog import content_digest
    from cloudra.tools.core.structure_artifacts import read_xyz_atoms
    from cloudra.tools.core.ts_pipeline_driver import advance_process
    from cloudra.tools.core.ts_process import TsProcessRecord
    tool=ConformerSearch()
    tool.subagent=SimpleNamespace(conversation_id='project',id='owner')
    out=tmp_path/'confs'
    out.mkdir()
    catalog=tool._run_regions(ConformerSearch_input_schema(smiles='CCCC',num_confs=2,catalog_mode='regions'),str(out))
    revision=json.loads(Path(catalog.region_snapshot_path).read_text())['revision']
    monkeypatch.setattr('cloudra.services.compute_admission.admit_job',lambda **_:AdmissionOutcome(ok=True,node_id='fixture',scheduler='local'))
    record=start(TsStartRequest(workspace_dir=str(tmp_path),owner_conversation_id='project',owner_session_id='owner',
        declaration=TsDeclaration(reactant_smiles='CCCC',product_smiles='CC(C)C',method='b3lyp/def2svp',distance_filters=[dict(atoms=[0,1],min_ang=.5,max_ang=3.)]),
        candidate_catalog=dict(catalog_id=catalog.catalog_id,partition_revision=revision)))
    assert record.blocked is None and record.job_steps[-1].purpose=='candidate_evaluation'
    parent=record.selected_candidate_id
    jobs=[]
    for _ in range(4):
        step=record.job_steps[-1]
        if step.purpose=='product_seed_opt':
            break
        jobs.append(step.job_id)
        task=ChemTask.model_validate_json(Path(step.input_path).read_text())
        xyz=Path(step.input_path).parent/'fixture.xyz'
        xyz.write_text(task.reactant_xyz)
        atoms=read_xyz_atoms(str(xyz))
        positions=[p for _,p in atoms]
        result=dict(returncode=0,normal_termination=True,evaluation_valid=True,method_fingerprint='GFN2-xTB',input_hash=content_digest(positions),
            positions=positions,symbols=[s for s,_ in atoms],energy_hartree=-1.,log_file=str(xyz))
        if task.task=='xtb_hessian':
            result['hessian_hartree_per_angstrom2']=np.eye(len(atoms)*3).tolist()
        else:
            result['gradient_hartree_per_angstrom']=np.zeros((len(atoms),3)).tolist()
        Path(result_path(step.input_path)).write_text(json.dumps(dict(manifest_digest=content_digest(task.model_dump()),process_exit_code=0,result=result)))
        with ComputeDB().connect() as con:
            con.execute("UPDATE compute_jobs SET state='done' WHERE id=?",(step.job_id,))
        record=TsProcessRecord.model_validate(advance_process(ComputeDB(),record.pipeline_id)['record'])
    assert record.blocked is None and record.job_steps[-1].purpose=='product_seed_opt'
    child=next(c for c in list_candidates(ComputeDB(),catalog.catalog_id,project_id='project',owner_id='owner') if c.candidate_id==record.selected_candidate_id)
    assert child.parent_id==parent
    assert set(child.job_ids)==set(jobs)
    assert child.qualification.status=='qualified'
