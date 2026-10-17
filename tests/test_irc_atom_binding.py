"""Native IRC evidence retains its concrete atom correspondence."""
from pathlib import Path

import numpy as np
import pytest

from cloudra.tools.core import irc_evidence
from cloudra.tools.core.irc_path import prove_irc_endpoint_direction

FIXTURE = Path(__file__).parent / "fixtures" / "nu3_atom_binding"
MAP = [1, 4, 5, 6, 10, 11, 3, 2, 7, 8, 9]


def binding():
    return {
        "process_id": "concrete-path", "declaration_revision": 8,
        "atom_map": MAP, "charge": 0,
        "reactant_mol": (FIXTURE / "reactant.mol").read_text(),
        "product_mol": (FIXTURE / "product.mol").read_text(),
    }


def owned_structures():
    from cloudra.tools.core.molecule import read_molecule
    from cloudra.tools.core.reaction_state import ReactionStructures

    return ReactionStructures(
        reactant=read_molecule(str(FIXTURE / "reactant.mol")),
        product=read_molecule(str(FIXTURE / "product.mol")),
        product_to_reactant=tuple(index - 1 for index in MAP),
    )


def materials():
    return (
        irc_evidence.irc_endpoint_geometries(FIXTURE / "irc.out"),
        irc_evidence.probe_log(FIXTURE / "ts.out")[1],
        irc_evidence.probe_log(FIXTURE / "reactant.out")[1],
        irc_evidence.probe_log(FIXTURE / "product.out")[1],
    )


def _write_endpoint_lineage_materials(directory):
    """Add native Opt first frames while retaining the fixture's bound final atom rows."""
    for name in ("ts.out", "irc.out", "reactant.out", "product.out", "irc_IRC_F.xyz", "irc_IRC_B.xyz"):
        (directory / name).write_bytes((FIXTURE / name).read_bytes())
    ends = irc_evidence.irc_endpoint_geometries(directory / "irc.out")
    # This fixture's backward frame relaxes to the reactant, forward to product.
    # Product Opt uses its declared MOL order, so reorder its input with MAP too.
    initial = {
        "reactant.out": ends[1],
        "product.out": ([ends[0][0][index - 1] for index in MAP],
                        [ends[0][1][index - 1] for index in MAP]),
    }
    for name, (symbols, positions) in initial.items():
        path = directory / name
        native = path.read_text()
        first_coordinates = ('CARTESIAN COORDINATES (ANGSTROEM)\n---------------------------------\n'
            + ''.join(f'{symbol} {x:.12f} {y:.12f} {z:.12f}\n'
                      for symbol, (x, y, z) in zip(symbols, positions, strict=True)) + '\n')
        index = native.index('CARTESIAN COORDINATES (ANGSTROEM)')
        path.write_text(native[:index] + first_coordinates
            + 'THE OPTIMIZATION HAS CONVERGED\n' + native[index:])


def test_native_irc_uses_complete_map_for_independently_bound_minima(rdkit_chemistry):
    ends, ts, source, target = materials()
    assert not next(irc_evidence.iter_direction_verdicts(ends, [ts], [source], [target]))["is_decidable"]
    actual = next(irc_evidence.iter_direction_verdicts(
        ends, [ts], [source], [target], atom_binding=binding()
    ))
    assert actual["is_decidable"] and actual["is_match"]


def test_map_is_not_applied_to_same_elements_with_wrong_hydrogen_parents(rdkit_chemistry):
    _, ts, source, target = materials()
    changed = np.array(target[1], dtype=float)
    changed[[2, 8]] = changed[[8, 2]]
    orders = irc_evidence.bound_atom_orders(ts, source, (target[0], changed), binding())
    assert orders is None


def test_explicit_map_keeps_existing_geometry_distance_limit(rdkit_chemistry):
    ends, ts, source, target = materials()
    inverse = [MAP.index(index + 1) for index in range(len(MAP))]
    bad = np.array(target[1], dtype=float) * 10
    result = prove_irc_endpoint_direction(
        *ts, ends[0], ends[1], source, (target[0], bad), [],
        atom_orders=[list(range(11)), list(range(11)), list(range(11)), inverse],
    )
    assert not result["is_decidable"] and not result["is_match"]


@pytest.mark.parametrize("paired", [False, True])
@pytest.mark.parametrize("valid_map", [False, True])
def test_log_based_direction_uses_same_binding_for_combined_and_split_irc(tmp_path, rdkit_chemistry, paired, valid_map):
    _write_endpoint_lineage_materials(tmp_path)
    paths = [tmp_path / "ts.out", tmp_path / "reactant.out", tmp_path / "product.out"]
    irc = tmp_path / "irc.out"
    archived = dict(binding(), atom_map=MAP if valid_map else list(range(1, len(MAP) + 1)))
    associations = {str(irc): archived, str(paths[0]): archived}
    if paired:
        passed, _ = irc_evidence.verify_short_irc_pair(
            irc, irc, [paths[0]], [paths[2]], [paths[1]],
            atom_bindings=associations,
        )
    else:
        passed, _ = irc_evidence.verify_short_irc_direction(
            irc, [paths[0]], [paths[2]], [paths[1]], atom_bindings=associations,
        )
    assert passed is valid_map


def test_old_stage_snapshot_does_not_read_current_process_mapping(tmp_path):
    import hashlib

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import bind_stage_job, commit_stage_result, create_process, get_process
    from cloudra.tools.core.ts_process import TsInput, TsProcessRecord
    from tests.test_ts_pipeline_store import payload

    db = ComputeDB(data_dir=tmp_path / "ledger").init()
    request = payload(workspace_dir=str(tmp_path))
    request["input"]["reaction"].update(reactant_smiles="[H][P@TB14]1([H])([H])CCO1",
        product_smiles="C=C.O=[PH3]")
    process = create_process(db, request_key="binding", payload=request)
    native = tmp_path / "frequency.inp"
    native.write_text("! Freq B3LYP def2-SVP\n")
    job = bind_stage_job(db, process_id=process["process_id"], declaration_revision=1,
        stage_key="frequency", attempt=1, job_payload=dict(conversation_id="project", session_id="owner",
            path=str(native), state="ready", jobtype="orca", node_id="fixture"))
    log_dir = tmp_path / ".cloudra"
    log_dir.mkdir()
    log = log_dir / f"calc-{job}.out.log"
    log.write_bytes((FIXTURE / "ts.out").read_bytes())
    frozen = dict(binding(), process_id=process["process_id"], declaration_revision=1)
    stage = dict(status="done", artifacts=[str(log)], input_hash=hashlib.sha256(native.read_bytes()).hexdigest(),
        atom_binding=frozen, log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    assert commit_stage_result(db, process_id=process["process_id"], expected_revision=get_process(db, process["process_id"])["revision"],
        stage_key="frequency", attempt=1, evidence=stage)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
        current = TsProcessRecord(run_id="bound", pipeline_id=process["process_id"],
            run_dir=str(tmp_path / "run"), workspace_dir=str(tmp_path),
            owner_conversation_id="project", owner_session_id="owner", declaration_revision=2,
            input=TsInput.model_validate(request["input"]), structures=owned_structures())
        changed = list(current.structures.product_to_reactant)
        changed[2], changed[3] = changed[3], changed[2]
        current.structures.product_to_reactant = tuple(changed)
        con.execute("UPDATE ts_pipeline_processes SET record=?, declaration_revision=2 WHERE process_id=?",
            (current.model_dump_json(), process["process_id"]))
    with use_pipeline_database(db):
        snap = snapshot_evidence_file(log, tmp_path)
    assert snap.metadata["atom_binding"] == frozen
    # A copied/renamed unrelated log must not borrow another job's map.
    unrelated = tmp_path / "copied.out"
    unrelated.write_bytes(log.read_bytes())
    with use_pipeline_database(db):
        assert "atom_binding" not in snapshot_evidence_file(unrelated, tmp_path).metadata


def test_dag_file_science_consumes_the_archived_concrete_map(tmp_path, rdkit_chemistry):
    from types import SimpleNamespace

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.file_science import file_scientific_checks

    snapshots = {}
    _write_endpoint_lineage_materials(tmp_path)
    for name in ("ts.out", "irc.out", "reactant.out", "product.out"):
        snap = snapshot_evidence_file(tmp_path / name, tmp_path)
        if name in ("ts.out", "irc.out"):
            snap.metadata["atom_binding"] = binding()
        snapshots[name] = snap.model_dump(mode="json")
    store = SimpleNamespace(resolve_evidence=lambda ref: snapshots[ref])
    source = SimpleNamespace(node_id="source", refs=["reactant.out"], stages=[], smiles="[H][P@TB14]1([H])([H])CCO1")
    target = SimpleNamespace(node_id="target", refs=["product.out"], stages=[], smiles="C=C.O=[PH3]")
    step = SimpleNamespace(edge_id="step", refs=["ts.out", "irc.out"], stages=[], source_node_id="source", target_node_id="target")
    graph = SimpleNamespace(nodes=[source,target], edges=[step])
    assert file_scientific_checks(store, graph, "step")["short_irc"]["status"] == "passed"
    for name in ("ts.out", "irc.out"):
        snapshots[name]["metadata"]["atom_binding"]["atom_map"] = list(range(1, len(MAP) + 1))
    assert file_scientific_checks(store, graph, "step")["short_irc"]["status"] == "incomplete"


def test_owned_producer_freezes_bound_mol_without_rereading_source_files(tmp_path):
    from cloudra.tools.core.irc_path import xyz_block
    from cloudra.tools.core.molecule import read_molecule
    from cloudra.tools.core.reaction_state import ReactionStructures
    from cloudra.tools.core.ts_process import TsInput, TsProcessRecord, _direction_atom_binding

    _, _, reactant, product = materials()
    molecules, sources = {}, {}
    for role, geometry in (("reactant", reactant), ("product", product)):
        xyz = tmp_path / (role + ".xyz")
        xyz.write_text(xyz_block(*geometry))
        mol = xyz.with_suffix(".bound.mol")
        mol.write_bytes((FIXTURE / (role + ".mol")).read_bytes())
        molecules[role] = read_molecule(str(mol))
        sources[role] = dict(kind="file", xyz_path=str(xyz), mol_path=str(mol))
        xyz.unlink()
        mol.unlink()
    record = TsProcessRecord(run_id="producer", pipeline_id="producer",
        run_dir=str(tmp_path / "run"), workspace_dir=str(tmp_path),
        input=TsInput(reaction=dict(reactant_smiles="[H][P@TB14]1([H])([H])CCO1",
            product_smiles="C=C.O=[PH3]", charge=0, multiplicity=1), conformers=sources),
        structures=ReactionStructures(**molecules, product_to_reactant=tuple(index - 1 for index in MAP)))
    frozen = _direction_atom_binding(record)
    assert frozen["atom_map"] == MAP
    assert frozen["reactant_mol"] == (FIXTURE / "reactant.mol").read_text()
    assert frozen["product_mol"] == (FIXTURE / "product.mol").read_text()


def test_managed_irc_keeps_unmanaged_ts_material_on_existing_geometry_path(monkeypatch):
    symbols = ["C", "N", "H"]
    def geometry(z):
        return symbols, [[0.,0.,0.], [0.,0.,2.], [0.,0.,z]]
    monkeypatch.setattr(irc_evidence, "irc_endpoint_geometries", lambda *_, **__: (geometry(.7), geometry(1.3)))
    monkeypatch.setattr(irc_evidence, "probe_log", lambda path, **_: (1 if path == "ts" else 0, geometry({"ts":1., "source":.1, "target":1.9}[path])))
    monkeypatch.setattr(irc_evidence, "irc_start_geometry", lambda _: geometry(1.))
    monkeypatch.setattr(irc_evidence, "_optimization_geometries", lambda path, **_: {
        "source": (geometry(.7), geometry(.1)),
        "target": (geometry(1.3), geometry(1.9)),
    }[path])
    passed, _ = irc_evidence.verify_short_irc_direction("irc", ["ts"], ["target"], ["source"],
        atom_bindings={"irc": binding()})
    assert passed


@pytest.mark.parametrize('log_available', [True, False], ids=['available-log', 'missing-log'])
def test_actual_driver_freezes_binding_only_with_native_log(tmp_path, monkeypatch, log_available):
    import hashlib
    import json

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.services.ts_pipeline_store import (
        atom_binding_for_log,
        bind_stage_job,
        create_process,
        save_process_record,
    )
    from cloudra.tools.core import ts_process
    from cloudra.tools.core.ts_pipeline_driver import advance_process
    from tests.test_ts_pipeline_store import payload

    request = payload(workspace_dir=str(tmp_path))
    request["input"]["reaction"].update(reactant_smiles="[H][P@TB14]1([H])([H])CCO1",
        product_smiles="C=C.O=[PH3]")
    db = ComputeDB().init()
    process = create_process(db, request_key="driver-binding", payload=request)
    native = tmp_path / "frequency.inp"
    native.write_text("! Freq B3LYP def2-SVP\n")
    job = bind_stage_job(db, process_id=process["process_id"], declaration_revision=1, stage_key="frequency", attempt=1,
        job_payload=dict(conversation_id="project",session_id="owner",path=str(native),state="ready",jobtype="orca",node_id="fixture"))
    (tmp_path / ".cloudra").mkdir()
    log = tmp_path / ".cloudra" / f"calc-{job}.out.log"
    if log_available:
        log.write_bytes((FIXTURE / "ts.out").read_bytes())
    record = ts_process.TsProcessRecord(run_id="bound", pipeline_id=process["process_id"],
        run_dir=str(tmp_path / "ts" / "bound"),workspace_dir=str(tmp_path),owner_conversation_id="project",owner_session_id="owner",
        input=ts_process.TsInput.model_validate(request["input"]),stage="refine",waiting_for=f"job:{job}",
        structures=owned_structures())
    submitted_binding = ts_process._direction_atom_binding(record)
    assert submitted_binding["ts_log_sha256"] is None
    record.job_steps.append(ts_process.TsJobStep(purpose="frequency", job_id=job,
        input_path=str(native), actual_calculation=record.input.verification.frequency,
        atom_binding=submitted_binding))
    # Completion must preserve the submitted evidence even if current state differs.
    changed = list(record.structures.product_to_reactant)
    changed[2], changed[3] = changed[3], changed[2]
    record.structures.product_to_reactant = tuple(changed)
    save_process_record(db,process_id=process["process_id"],record=record.model_dump(mode="json"))
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?",(job,))
    # The next compute stage is out of scope; the actual completion/freezing path runs.
    monkeypatch.setattr(ts_process,"advance",lambda record: record)
    advance_process(db,process["process_id"])
    with db.connect() as con:
        frozen=json.loads(con.execute("SELECT evidence FROM ts_pipeline_stages WHERE job_id=?",(job,)).fetchone()[0])
    if log_available:
        assert frozen["atom_binding"]["atom_map"] == MAP
        assert frozen["atom_binding"]["reactant_mol"] == submitted_binding["reactant_mol"]
        assert frozen["atom_binding"]["product_mol"] == (FIXTURE / "product.mol").read_text()
        assert frozen["log_sha256"] == hashlib.sha256(log.read_bytes()).hexdigest()
        assert frozen["atom_binding"]["ts_log_sha256"] == frozen["log_sha256"]
        assert submitted_binding["ts_log_sha256"] is None
    else:
        assert frozen["atom_binding"] is None
        assert frozen["log_sha256"] is None
        log.write_bytes((FIXTURE / "ts.out").read_bytes())
    with use_pipeline_database(db):
        snap = snapshot_evidence_file(log,tmp_path)
    assert snap.metadata.get("atom_binding") == frozen["atom_binding"]
    if log_available:
        log.write_text(log.read_text() + '\nChanged native log bytes.\n')
        with pytest.raises(ValueError, match='Native log changed'):
            atom_binding_for_log(db, log, tmp_path)


def test_split_irc_with_one_known_binding_keeps_existing_geometry_path(monkeypatch):
    from cloudra.tools.core.gaussian_frames import FrameRecord

    symbols = ["C", "N", "H"]
    def geometry(z):
        return symbols, [[0.,0.,0.], [0.,0.,2.], [0.,0.,z]]
    def frames(path):
        z = .7 if path == "forward" else 1.3
        coordinate = 1 if path == "forward" else -1
        from cloudra.tools.core.irc_path import xyz_block
        return [FrameRecord(frame=1, xyz=xyz_block(*geometry(z)), reaction_coordinate=coordinate)]
    monkeypatch.setattr(irc_evidence.qm_engine,"detect_qm_engine",lambda _: "gaussian")
    monkeypatch.setattr(irc_evidence,"irc_frames_for",frames)
    monkeypatch.setattr(irc_evidence,"probe_log",lambda path,**_: (1 if path == "ts" else 0,geometry({"ts":1.,"source":.1,"target":1.9}[path])))
    monkeypatch.setattr(irc_evidence,"irc_start_geometry",lambda _: geometry(1.))
    monkeypatch.setattr(irc_evidence, "_optimization_geometries", lambda path, **_: {
        "source": (geometry(.7), geometry(.1)),
        "target": (geometry(1.3), geometry(1.9)),
    }[path])
    passed,_ = irc_evidence.verify_short_irc_pair("forward","reverse",["ts"],["target"],["source"],
        atom_bindings={"forward":binding()})
    assert passed


def _archived_scorer_materials(tmp_path, monkeypatch):
    import hashlib

    from cloudra.benchmark.integrity import EvidenceFile
    from cloudra.benchmark.selfconsistency import _LogProbe
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    _write_endpoint_lineage_materials(tmp_path)
    frozen = dict(binding(), ts_log_sha256=hashlib.sha256((tmp_path / "ts.out").read_bytes()).hexdigest())
    monkeypatch.setattr("cloudra.services.ts_pipeline_store.atom_binding_for_log", lambda *args: frozen if Path(args[1]).name in {"ts.out","irc.out"} else None)
    archived = {name: snapshot_evidence_file(tmp_path / name,tmp_path) for name in ("ts.out","irc.out","reactant.out","product.out")}
    paths = {name: str(Path(snapshot.snapshot_path).relative_to(tmp_path)) for name,snapshot in archived.items()}
    files = {path: EvidenceFile(path=path,kind="orca",size=(tmp_path / path).stat().st_size) for path in paths.values()}
    return _LogProbe(tmp_path,files), paths, archived


def test_independent_file_scorer_consumes_the_same_archived_mapping(tmp_path, monkeypatch, rdkit_chemistry):
    from cloudra.benchmark.selfconsistency import _strict_irc_proof

    probe,paths,_ = _archived_scorer_materials(tmp_path,monkeypatch)
    proof = _strict_irc_proof(probe,list(paths.values()),[paths["reactant.out"]],[paths["product.out"]],
        ts_files=[paths["ts.out"]])
    assert proof is not None
    evidence_paths, details = proof
    assert evidence_paths == [paths[name] for name in ("ts.out", "irc.out", "reactant.out", "product.out")]
    assert any('both actual IRC outer frames' in detail for detail in details)
    invalid = dict(probe.irc_atom_binding(paths["irc.out"]), atom_map=list(range(1, len(MAP) + 1)))
    monkeypatch.setattr(probe, "irc_atom_binding", lambda _: invalid)
    assert _strict_irc_proof(probe,list(paths.values()),[paths["reactant.out"]],[paths["product.out"]],
        ts_files=[paths["ts.out"]]) is None


def test_independent_scorer_does_not_use_mapping_for_a_different_ts_log(tmp_path, monkeypatch, rdkit_chemistry):
    from cloudra.benchmark.selfconsistency import _strict_irc_proof

    probe,paths,_ = _archived_scorer_materials(tmp_path,monkeypatch)
    ts = tmp_path / paths["ts.out"]
    ts.write_text(ts.read_text()+"\nDifferent native job bytes.\n")

    def reject_borrowed_mapping(*_args, **_kwargs):
        raise AssertionError('A different TS frequency witness must not use archived atom identities.')

    monkeypatch.setattr(irc_evidence, '_ordered_graph_matches', reject_borrowed_mapping)
    # Real Opt rows still establish lineage independently; only the archived
    # correspondence is forbidden after the frequency witness bytes changed.
    proof = _strict_irc_proof(probe,list(paths.values()),[paths["reactant.out"]],[paths["product.out"]],
        ts_files=[paths["ts.out"]])
    assert proof is not None


def test_irc_bundle_digest_covers_archived_binding(tmp_path, monkeypatch):
    import hashlib
    import json

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    for name in ("irc.out","irc_IRC_F.xyz","irc_IRC_B.xyz"):
        (tmp_path / name).write_bytes((FIXTURE / name).read_bytes())
    state = {"value": dict(binding(),ts_log_sha256=hashlib.sha256((FIXTURE / "ts.out").read_bytes()).hexdigest())}
    monkeypatch.setattr("cloudra.services.ts_pipeline_store.atom_binding_for_log", lambda *_: state["value"])
    first = snapshot_evidence_file(tmp_path / "irc.out",tmp_path)
    state["value"] = dict(state["value"],declaration_revision=9)
    second = snapshot_evidence_file(tmp_path / "irc.out",tmp_path)
    assert first.snapshot_path != second.snapshot_path
    manifest = Path(first.metadata["irc_manifest"]["snapshot_path"])
    content = manifest.read_bytes()
    assert hashlib.sha256(content).hexdigest() == first.metadata["irc_manifest"]["sha256"]
    assert json.loads(content)["atom_binding"]["declaration_revision"] == 8


def test_rearchiving_verified_irc_preserves_the_bound_mapping(tmp_path, monkeypatch, rdkit_chemistry):
    from cloudra.dag.evidence_ingest import snapshot_evidence_file

    _,_,archived = _archived_scorer_materials(tmp_path,monkeypatch)
    original = archived["irc.out"]
    copied = snapshot_evidence_file(original.snapshot_path,tmp_path)
    assert copied.metadata["atom_binding"] == original.metadata["atom_binding"]


def test_independent_scorer_matches_binding_to_frequency_witness(tmp_path, monkeypatch, rdkit_chemistry):
    from cloudra.benchmark.integrity import EvidenceFile
    from cloudra.benchmark.selfconsistency import _strict_irc_proof

    probe, paths, _ = _archived_scorer_materials(tmp_path, monkeypatch)
    frequency = (tmp_path / paths["ts.out"]).read_text()
    optimization = tmp_path / "opt.out"
    optimization.write_text(frequency.split("VIBRATIONAL FREQUENCIES", 1)[0] + "\nORCA TERMINATED NORMALLY\n")
    probe._files["opt.out"] = EvidenceFile(path="opt.out", kind="orca", size=optimization.stat().st_size)
    proof = _strict_irc_proof(probe, ["opt.out", *paths.values()],
        [paths["reactant.out"]], [paths["product.out"]], ts_files=["opt.out"])
    assert proof is not None
    assert proof[0] == ["opt.out", *[paths[name] for name in ("ts.out", "irc.out", "reactant.out", "product.out")]]
