"""Current input files expose only the accepted canonical atom numbering."""

from pathlib import Path

import pytest

from cloudra.services.ts_pipeline_store import commit_input_revision, create_process, get_process, save_process_record
from cloudra.tools.core.structure_artifacts import read_xyz_atoms
from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
from tests.test_ts_pipeline_store import payload
from tests.test_ts_resume_transitions import request
from tests.test_ts_revision_identity import _identity_fixture, _write_source

pytestmark = pytest.mark.usefixtures("rdkit_chemistry", "ts_producer_authority")


def _ledger(tmp_path, record):
    from cloudra.persistence.database import ComputeDB

    db = ComputeDB(data_dir=tmp_path / "ledger").init()
    declaration = payload(workspace_dir=str(tmp_path))
    declaration["input"] = record.input.model_dump(mode="json")
    record.pipeline_id = create_process(db, request_key="prepare", payload=declaration)["process_id"]
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode="json"))
    record.revision = get_process(db, record.pipeline_id)["revision"]
    return db


def test_commit_overwrites_current_files_with_new_coordinates_in_old_order_and_replays_once(tmp_path):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    old_input = record.input.model_copy(deep=True)
    old_snapshot = Path(record.current_seed_xyz_path).read_bytes()
    mol.GetConformer().SetAtomPosition(1, (1.4, .8, .1))
    replacement = _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    raw = Path(replacement["xyz_path"]).read_bytes()
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert Path(replacement["xyz_path"]).read_bytes() == raw  # Planning stays pure.
    commit_input_revision(db, process_id=record.pipeline_id, request=change,
                          record=revised.model_dump(mode="json"), receipt=receipt)
    accepted = get_process(db, record.pipeline_id)
    assert accepted["record"]["input"]["reaction"] == old_input.reaction.model_dump(mode="json")
    assert accepted["record"]["input"]["guess"] == old_input.guess.model_dump(mode="json")
    assert accepted["record"]["input"]["conformers"]["reactant"]["xyz_path"] == replacement["xyz_path"]
    atoms = read_xyz_atoms(replacement["xyz_path"])
    assert [symbol for symbol, _ in atoms] == ["O", "H", "H"]
    assert atoms[1][1] == [1.4, .8, .1]
    canonical_mol = Chem.MolFromMolFile(replacement["mol_path"], removeHs=False)
    assert [atom.GetAtomMapNum() for atom in canonical_mol.GetAtoms()] == [10, 11, 12]
    assert Chem.MolToSmiles(canonical_mol) == Chem.MolToSmiles(mol)
    assert Path(record.current_seed_xyz_path).read_bytes() == old_snapshot
    assert (Path(record.run_dir) / "build/input_0002/reactant/seed.xyz").read_bytes() == Path(replacement["xyz_path"]).read_bytes()
    normalization = accepted["record"]["structures"]["reactant"]["normalization"]
    assert normalization["status"] == "applied"
    assert normalization["source_to_canonical"] == [3, 1, 2]
    assert normalization["canonical_to_source"] == [2, 3, 1]
    assert not list(tmp_path.rglob("*raw*"))
    canonical_bytes = Path(replacement["xyz_path"]).read_bytes()
    commit_input_revision(db, process_id=record.pipeline_id, request=change,
                          record=revised.model_dump(mode="json"), receipt=receipt)
    assert get_process(db, record.pipeline_id) == accepted
    assert Path(replacement["xyz_path"]).read_bytes() == canonical_bytes


def test_explicit_raw_references_convert_once_including_product_map_slots(tmp_path):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path)
    _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    _write_source(tmp_path, "product", Chem.RenumberAtoms(mol, [1, 2, 0]))
    guess = record.input.guess.model_dump()
    guess["scans"][0]["atoms"], guess["freeze"][0]["atoms"] = [1, 2], [1, 0]
    change = request(record, dict(reaction=dict(atom_map=[2, 0, 1], reaction_center=[[1, 2]]),
        conformers=dict(guidance=dict(ring_order=[1, 2, 0],
            distance_filters=[dict(atoms=[1, 2], min_ang=.5, max_ang=2.)])), guess=guess))
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.input.reaction.atom_map == [0, 1, 2]
    assert revised.input.reaction.reaction_center == [(0, 1)]
    assert revised.input.conformers.guidance.ring_order == [0, 1, 2]
    assert revised.input.conformers.guidance.distance_filters[0].atoms == [0, 1]
    assert revised.input.guess.scans[0].atoms == [0, 1]
    assert revised.input.guess.freeze[0].atoms == [0, 2]


def test_unproved_current_file_permutation_blocks_without_claiming_normalization(tmp_path):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path, labels=False)
    replacement = _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [0, 2, 1]))
    before = Path(replacement["xyz_path"]).read_bytes()
    with pytest.raises(ValueError, match="atom correspondence.*unproved|unproved.*atom correspondence"):
        plan_input_revision(record, request(record, {}))
    assert Path(replacement["xyz_path"]).read_bytes() == before
    assert "normalization" not in record.structures["reactant"]


def test_changed_coordinate_source_cannot_reuse_an_equal_dependency_receipt(tmp_path):
    record, mol = _identity_fixture(tmp_path)
    replacement = _write_source(tmp_path / "new", "reactant", mol)
    change = request(record, dict(conformers=dict(reactant=replacement)))
    receipt = plan_input_revision(record, change)
    mol.GetConformer().SetAtomPosition(1, (1.4, .8, .1))
    _write_source(tmp_path / "new", "reactant", mol)
    with pytest.raises(ValueError, match="revision plan changed|source changed"):
        revise_record(record, change, receipt)


def test_ledger_rejection_never_overwrites_current_raw_source(tmp_path):
    from rdkit import Chem

    from cloudra.services.ts_pipeline_store import TsEvidenceReference

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    replacement = _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    before = {name: Path(replacement[name + "_path"]).read_bytes() for name in ("xyz", "mol")}
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    receipt.retained.append(TsEvidenceReference(declaration_revision=1, stage_key="ts_opt", attempt=1, job_id=999))
    with pytest.raises(ValueError, match="evidence binding"):
        commit_input_revision(db, process_id=record.pipeline_id, request=change,
                              record=revised.model_dump(mode="json"), receipt=receipt)
    assert {name: Path(replacement[name + "_path"]).read_bytes() for name in ("xyz", "mol")} == before
    assert get_process(db, record.pipeline_id)["declaration_revision"] == 1


@pytest.mark.parametrize("after_commit", [False, True])
def test_crash_recovers_partial_files_or_committed_declaration_before_authoritative_read(tmp_path, monkeypatch, after_commit):
    import json

    from rdkit import Chem

    from cloudra.persistence import fs_utils
    from cloudra.services import ts_pipeline_store

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    replacement = _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    original = fs_utils.atomic_write_bytes
    original_export = ts_pipeline_store._write_revision_exports
    writes = 0

    def interrupted_write(path, data, **kwargs):
        nonlocal writes
        original(path, data, **kwargs)
        writes += 1
        if writes == 1:
            raise SystemExit("simulated process loss after first current source rewrite")

    def interrupted_export(value):
        raise SystemExit("simulated process loss after durable declaration commit")

    monkeypatch.setattr(ts_pipeline_store, "_write_revision_exports", interrupted_export) if after_commit else monkeypatch.setattr(fs_utils, "atomic_write_bytes", interrupted_write)
    with pytest.raises(SystemExit):
        commit_input_revision(db, process_id=record.pipeline_id, request=change,
                              record=revised.model_dump(mode="json"), receipt=receipt)
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM ts_pipeline_source_rewrites").fetchone()[0] == 1
        assert con.execute("SELECT declaration_revision FROM ts_pipeline_processes").fetchone()[0] == (2 if after_commit else 1)
    monkeypatch.setattr(fs_utils, "atomic_write_bytes", original)
    monkeypatch.setattr(ts_pipeline_store, "_write_revision_exports", original_export)
    accepted = get_process(db, record.pipeline_id)
    assert accepted["declaration_revision"] == 2
    assert accepted["record"]["input"]["reaction"]["atom_map"] == [0, 1, 2]
    assert read_xyz_atoms(replacement["xyz_path"])[0][0] == "O"
    assert [atom.GetAtomMapNum() for atom in Chem.MolFromMolFile(replacement["mol_path"], removeHs=False).GetAtoms()] == [10, 11, 12]
    assert accepted["record"]["structures"]["reactant"]["normalization"]["status"] == "applied"
    assert json.loads((Path(record.run_dir) / "process.json").read_text())["revision"] == accepted["revision"]
    assert json.loads((Path(record.run_dir) / "declare.json").read_text()) == accepted["record"]["input"]
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM ts_pipeline_source_rewrites").fetchone()[0] == 0


def test_mid_rewrite_reader_waits_and_never_sees_pending_current_numbering(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from rdkit import Chem

    from cloudra.persistence import fs_utils

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    started, release, reader_entered = Event(), Event(), Event()
    original = fs_utils.atomic_write_bytes

    def paused_write(path, data, **kwargs):
        original(path, data, **kwargs)
        if path == record.input.conformers.reactant.xyz_path:
            started.set()
            assert release.wait(timeout=10)

    def read():
        reader_entered.set()
        return get_process(db, record.pipeline_id)

    monkeypatch.setattr(fs_utils, "atomic_write_bytes", paused_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        commit = pool.submit(commit_input_revision, db, process_id=record.pipeline_id,
                             request=change, record=revised.model_dump(mode="json"), receipt=receipt)
        assert started.wait(timeout=10)
        reader = pool.submit(read)
        assert reader_entered.wait(timeout=10)
        assert not reader.done()
        release.set()
        commit.result(timeout=10)
        accepted = reader.result(timeout=10)
    assert accepted["declaration_revision"] == 2
    assert accepted["record"]["structures"]["reactant"]["normalization"]["status"] == "applied"


def test_regular_failure_after_first_rewrite_restores_both_preimages_and_ledger(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.persistence import fs_utils

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    replacement = _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    before = {name: Path(replacement[name + "_path"]).read_bytes() for name in ("xyz", "mol")}
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    original = fs_utils.atomic_write_bytes
    writes = 0

    def failed_write(path, data, **kwargs):
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("simulated second source write failure")
        original(path, data, **kwargs)

    monkeypatch.setattr(fs_utils, "atomic_write_bytes", failed_write)
    with pytest.raises(OSError):
        commit_input_revision(db, process_id=record.pipeline_id, request=change,
                              record=revised.model_dump(mode="json"), receipt=receipt)
    assert {name: Path(replacement[name + "_path"]).read_bytes() for name in ("xyz", "mol")} == before
    assert get_process(db, record.pipeline_id)["declaration_revision"] == 1
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM ts_pipeline_source_rewrites").fetchone()[0] == 0


def test_submitted_job_file_cannot_be_rewritten_as_a_current_conformer(tmp_path):
    from rdkit import Chem

    from cloudra.services.ts_pipeline_store import bind_stage_job
    from tests.test_ts_pipeline_store import job_payload

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    path = record.input.conformers.reactant.xyz_path
    submitted = job_payload()
    submitted['path'] = path
    job = bind_stage_job(db, process_id=record.pipeline_id, declaration_revision=1, stage_key="ts_opt",
                         attempt=1, job_payload=submitted)
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
    record.revision = get_process(db, record.pipeline_id)["revision"]
    _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    before = Path(path).read_bytes()
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    with pytest.raises(ValueError, match="immutable calculation input or evidence"):
        commit_input_revision(db, process_id=record.pipeline_id, request=change,
                              record=revised.model_dump(mode="json"), receipt=receipt)
    assert Path(path).read_bytes() == before


def test_same_mutable_path_cannot_receive_different_canonical_orders_for_two_roles(tmp_path):
    from rdkit import Chem

    from cloudra.tools.core.ts_process import _store_structure_table

    record, mol = _identity_fixture(tmp_path)
    old_product = Chem.RenumberAtoms(mol, [1, 2, 0])
    Path(record.product_seed_xyz_path).write_text(Chem.MolToXYZBlock(old_product))
    Path(record.product_seed_mol_path).write_text(Chem.MolToMolBlock(old_product))
    _store_structure_table(record, 'product')
    record.input.reaction.atom_map = [1, 2, 0]
    db = _ledger(tmp_path, record)
    shared = _write_source(tmp_path, 'reactant', Chem.RenumberAtoms(mol, [2, 0, 1]))
    change = request(record, dict(conformers=dict(product=shared)))
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    before = Path(shared['xyz_path']).read_bytes()
    with pytest.raises(ValueError, match='conflicting canonical atom orders'):
        commit_input_revision(db, process_id=record.pipeline_id, request=change,
                              record=revised.model_dump(mode='json'), receipt=receipt)
    assert Path(shared['xyz_path']).read_bytes() == before
    assert get_process(db, record.pipeline_id)['declaration_revision'] == 1


def test_other_run_immutable_seed_cannot_be_overwritten_by_this_run(tmp_path):
    from rdkit import Chem

    from cloudra.tools.core.ts_process import _build

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    other, _ = _identity_fixture(tmp_path / 'other-fixtures')
    other.workspace_dir = str(tmp_path)
    _write_source(tmp_path / 'other-fixtures', 'reactant', Chem.RenumberAtoms(mol, [2, 0, 1]))
    other.declaration_revision = 2
    other.input.conformers.guidance.ring_order = []
    other.input.conformers.guidance.distance_filters = []
    _build(other)
    declaration = payload(workspace_dir=str(tmp_path))
    declaration['input'] = other.input.model_dump(mode='json')
    other.pipeline_id = create_process(db, request_key='other-prepare', payload=declaration)['process_id']
    other.declaration_revision = 1
    save_process_record(db, process_id=other.pipeline_id, record=other.model_dump(mode='json'))
    replacement = dict(kind='file', xyz_path=other.current_seed_xyz_path, mol_path=other.current_seed_mol_path)
    before = Path(other.current_seed_xyz_path).read_bytes()
    change = request(record, dict(conformers=dict(reactant=replacement)))
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    with pytest.raises(ValueError, match='immutable calculation input or evidence'):
        commit_input_revision(db, process_id=record.pipeline_id, request=change,
                              record=revised.model_dump(mode='json'), receipt=receipt)
    assert Path(other.current_seed_xyz_path).read_bytes() == before


def test_new_provided_guess_requires_proven_raw_association_but_inherited_guess_keeps_canonical_order(tmp_path):
    from rdkit import Chem

    from cloudra.tools.core.ts_inputs import ProvidedGuess

    record, mol = _identity_fixture(tmp_path)
    guess_path = tmp_path / 'guess.xyz'
    guess_path.write_text(Chem.MolToXYZBlock(mol))
    record.input.guess = ProvidedGuess(kind='provided', xyz_path=str(guess_path), evidence_refs=['stable-declaration'])
    _write_source(tmp_path, 'reactant', Chem.RenumberAtoms(mol, [2, 0, 1]))
    change = request(record, {})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.input.guess == record.input.guess
    unknown = tmp_path / 'new-guess.xyz'
    mol.GetConformer().SetAtomPosition(1, (1.4, .8, .1))
    unknown.write_text(Chem.MolToXYZBlock(mol))
    change = request(record, dict(guess=dict(kind='provided', xyz_path=str(unknown), evidence_refs=['new-declaration'])))
    with pytest.raises(ValueError, match='first resume the source normalization'):
        plan_input_revision(record, change)


def test_explicit_raw_heavy_binding_uses_one_based_indices_and_canonical_geometry_digest(tmp_path):
    from rdkit import Chem

    from cloudra.tools.core.ts_process import TsProcessRecord, _bound_input_structure, _build

    record, mol = _identity_fixture(tmp_path, smiles='F[C@](Cl)(Br)I', labels=False)
    db = _ledger(tmp_path, record)
    raw_mol = Chem.RenumberAtoms(mol, [4, 3, 2, 1, 0])
    replacement = _write_source(tmp_path, 'reactant', raw_mol)
    # The caller's binding digest covers the raw file's actual XYZ precision.
    graph = Chem.MolFromMolFile(replacement['mol_path'], removeHs=False)
    conf = Chem.Conformer(5)
    for index, (_, position) in enumerate(read_xyz_atoms(replacement['xyz_path'])):
        conf.SetAtomPosition(index, position)
    graph.RemoveAllConformers()
    graph.AddConformer(conf)
    replacement['heavy_atom_binding'] = dict(indices=[5, 4, 3, 2, 1])
    change = request(record, dict(conformers=dict(reactant=replacement)))
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert revised.input.conformers.reactant.heavy_atom_binding.indices == [1, 2, 3, 4, 5]
    commit_input_revision(db, process_id=record.pipeline_id, request=change,
                          record=revised.model_dump(mode='json'), receipt=receipt)
    accepted = TsProcessRecord.model_validate(get_process(db, record.pipeline_id)['record'])
    accepted.input.conformers.guidance.ring_order = []
    accepted.input.conformers.guidance.distance_filters = []
    _build(accepted)
    assert accepted.blocked is None
    _bound_input_structure(accepted, 'reactant', require_identity=False, persist_artifact=False)


def test_projected_mol_cannot_change_stereo_when_xyz_contradicts_its_graph(tmp_path):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path, smiles='F[C@](Cl)(Br)I')
    original_mol = Path(record.input.conformers.reactant.mol_path).read_bytes()
    for index in range(mol.GetNumAtoms()):
        point = mol.GetConformer().GetAtomPosition(index)
        mol.GetConformer().SetAtomPosition(index, (-point.x, point.y, point.z))
    Path(record.input.conformers.reactant.xyz_path).write_text(Chem.MolToXYZBlock(mol))
    with pytest.raises(ValueError, match='canonical MOL.*identity|canonical MOL.*stereo'):
        plan_input_revision(record, request(record, {}))
    assert Path(record.input.conformers.reactant.mol_path).read_bytes() == original_mol


def test_build_captures_xyz_and_mol_together_before_other_run_canonical_overwrite(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from rdkit import Chem

    from cloudra.services.ts_pipeline_context import use_pipeline_database
    from cloudra.tools.core.ts_process import _build
    from tests.test_ts_stage_inputs import record_fixture

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    raw = _write_source(tmp_path, 'reactant', Chem.RenumberAtoms(mol, [2, 0, 1]))
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    consumer = record_fixture(tmp_path / 'consumer', workspace_dir=str(tmp_path),
                              input=record.input.model_copy(deep=True))
    consumer.input.conformers.guidance.ring_order = []
    consumer.input.conformers.guidance.distance_filters = []
    before = {name: Path(raw[name + '_path']).read_bytes() for name in ('xyz', 'mol')}
    started, release, commit_entered = Event(), Event(), Event()
    original_read = Path.read_bytes

    def captured_xyz(path):
        data = original_read(path)
        if str(path) == raw['xyz_path'] and not started.is_set():
            started.set()
            assert release.wait(timeout=10)
        return data

    def consume():
        with use_pipeline_database(db):
            return _build(consumer)

    def accept():
        commit_entered.set()
        return commit_input_revision(db, process_id=record.pipeline_id, request=change,
                                     record=revised.model_dump(mode='json'), receipt=receipt)

    monkeypatch.setattr(Path, 'read_bytes', captured_xyz)
    with ThreadPoolExecutor(max_workers=2) as pool:
        build = pool.submit(consume)
        assert started.wait(timeout=10)
        commit = pool.submit(accept)
        assert commit_entered.wait(timeout=10)
        assert not commit.done()
        release.set()
        built = build.result(timeout=10)
        commit.result(timeout=10)
    assert built.blocked is None
    assert Path(built.current_seed_xyz_path).read_bytes() == before['xyz']
    assert Path(built.current_seed_mol_path).read_bytes() == before['mol']


def test_blocked_recovery_inspection_preserves_real_revision_and_jobs_without_current_table(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.persistence import fs_utils
    from cloudra.services.ts_pipeline_store import SourceRewriteRecoveryBlocked, bind_stage_job
    from cloudra.tools.core.ts_process import TsJobStep
    from cloudra.tools.core.ts_state_view import inspect_process
    from tests.test_ts_pipeline_store import job_payload

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    job = bind_stage_job(db, process_id=record.pipeline_id, declaration_revision=1,
                         stage_key='ts_opt', attempt=1, job_payload=job_payload())
    with db.connect() as con:
        con.execute("UPDATE compute_jobs SET state='done' WHERE id=?", (job,))
    record.job_steps = [TsJobStep(purpose='ts_opt', job_id=job, state='done')]
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode='json'))
    record.revision = get_process(db, record.pipeline_id)['revision']
    _write_source(tmp_path, 'reactant', Chem.RenumberAtoms(mol, [2, 0, 1]))
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    original = fs_utils.atomic_write_bytes

    def crash_after_write(path, data, **kwargs):
        original(path, data, **kwargs)
        raise SystemExit('simulated process loss')

    monkeypatch.setattr(fs_utils, 'atomic_write_bytes', crash_after_write)
    with pytest.raises(SystemExit):
        commit_input_revision(db, process_id=record.pipeline_id, request=change,
                              record=revised.model_dump(mode='json'), receipt=receipt)
    monkeypatch.setattr(fs_utils, 'atomic_write_bytes', original)
    Path(record.input.conformers.reactant.xyz_path).write_text('1\nunrelated external edit\nHe 0 0 0\n')
    with pytest.raises(SourceRewriteRecoveryBlocked):
        get_process(db, record.pipeline_id)
    view = inspect_process(db, project_id='project', run_id=record.run_id,
                           workspace_dir=str(tmp_path), can_write=True)
    assert view.run_id == record.run_id
    assert view.revision == record.revision
    assert view.status == 'blocked' and view.result is None
    assert view.blocked['failure_class'] == 'canonical_source_recovery_blocked'
    assert view.blocked['needs'] == ['conformers.reactant']
    assert 'reactant' not in view.structures
    assert view.usage['jobs'][0]['job_id'] == job
    assert view.details_path == ''


def test_unrelated_unsupported_checkpoint_does_not_block_current_source_normalization(tmp_path):
    import json

    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path)
    db = _ledger(tmp_path, record)
    unsupported = create_process(db, request_key='unsupported', payload=payload(workspace_dir=str(tmp_path)))
    with db.connect() as con:
        con.execute('UPDATE ts_pipeline_processes SET record=? WHERE process_id=?',
                    (json.dumps(dict(format_version=3, run_dir=str(tmp_path / 'old-run'),
                                     workspace_dir=str(tmp_path))), unsupported['process_id']))
    _write_source(tmp_path, 'reactant', Chem.RenumberAtoms(mol, [2, 0, 1]))
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    commit_input_revision(db, process_id=record.pipeline_id, request=change,
                          record=revised.model_dump(mode='json'), receipt=receipt)
    assert get_process(db, record.pipeline_id)['declaration_revision'] == 2
