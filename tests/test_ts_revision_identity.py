"""Input revisions retain atom declarations only with concrete identity evidence."""

from pathlib import Path

import pytest

from cloudra.tools.core.ts_inputs import ConformerGuidance, TsInput, normalize_ts_input_atoms
from cloudra.tools.core.ts_revision import plan_input_revision, revise_record
from tests.test_ts_inputs import input_payload
from tests.test_ts_resume_transitions import request
from tests.test_ts_stage_inputs import record_fixture

pytestmark = pytest.mark.usefixtures("rdkit_chemistry", "ts_producer_authority")


def _write_source(directory, role, mol):
    from rdkit import Chem

    directory.mkdir(parents=True, exist_ok=True)
    xyz, mol_path = directory / f"{role}.xyz", directory / f"{role}.mol"
    xyz.write_text(Chem.MolToXYZBlock(mol))
    mol_path.write_text(Chem.MolToMolBlock(mol))
    return dict(kind="file", xyz_path=str(xyz), mol_path=str(mol_path))


def _identity_fixture(tmp_path, *, smiles="O", labels=True):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.ts_process import _build

    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert AllChem.EmbedMolecule(mol, randomSeed=42) == 0
    if labels:
        for atom in mol.GetAtoms():
            atom.SetAtomMapNum(atom.GetIdx() + 10)
    value = input_payload()
    value["reaction"].update(reactant_smiles=smiles, product_smiles=smiles,
                             atom_map=list(range(1, mol.GetNumAtoms() + 1)), reaction_center=[[1, 2]])
    value["conformers"] = dict(
        reactant=_write_source(tmp_path, "reactant", mol),
        product=_write_source(tmp_path, "product", mol),
        guidance=dict(ring_order=list(range(1, mol.GetNumAtoms() + 1)),
                      distance_filters=[dict(atoms=[1, 2], min_ang=.5, max_ang=2.)]),
    )
    value["guess"]["freeze"] = [dict(coord_type="bond", atoms=[0, 2])]
    record = record_fixture(tmp_path, input=normalize_ts_input_atoms(TsInput.model_validate(value), atom_tables={}))
    guidance = record.input.conformers.guidance
    record.input.conformers.guidance = ConformerGuidance()
    _build(record)
    assert record.blocked is None
    record.input.conformers.guidance = guidance
    record.stage, record.terminal = "verdict", "candidate_only"
    return record, mol


@pytest.mark.parametrize("replacement", ["absolute", "copy", "formatted"])
def test_unchanged_concrete_atoms_keep_declarations_across_file_representations(tmp_path, replacement):
    record, mol = _identity_fixture(tmp_path, labels=False)
    before = record.input.model_copy(deep=True)
    if replacement == "absolute":
        record.input.conformers.reactant.xyz_path = "reactant.xyz"
        record.input.conformers.reactant.mol_path = "reactant.mol"
        changes = dict(conformers=dict(reactant=before.conformers.reactant.model_dump()))
    elif replacement == "copy":
        changes = dict(conformers=dict(reactant=_write_source(tmp_path / "copy", "reactant", mol)))
    else:
        xyz = Path(record.input.conformers.reactant.xyz_path)
        # Preserve exact parsed coordinates; only number formatting and comments change.
        old = Path(record.current_seed_xyz_path).read_text().splitlines()
        xyz.write_text("3\nnew comment\n" + "\n".join(
            "  ".join([row.split()[0], *(f"{float(v):.8e}" for v in row.split()[1:4])])
            for row in old[2:5]) + "\n")
        changes = {}
    change = request(record, changes)
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.input.reaction == before.reaction
    assert revised.input.conformers.guidance == before.conformers.guidance
    assert revised.input.guess == before.guess


def test_labelled_coordinate_update_keeps_atom_declarations_but_invalidates_numeric_evidence(tmp_path):
    from cloudra.tools.core.ts_process import TsJobStep

    record, mol = _identity_fixture(tmp_path)
    before = record.input.model_copy(deep=True)
    record.job_steps = [TsJobStep(purpose="ts_opt", job_id=7, state="done")]
    record.optimization_checkpoints = {"reactant": {"energy": -1.}}
    mol.GetConformer().SetAtomPosition(1, (1.4, .8, .1))
    _write_source(tmp_path, "reactant", mol)
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    assert revised.input.reaction == before.reaction
    assert revised.input.conformers.guidance == before.conformers.guidance
    assert revised.input.guess == before.guess
    assert [ref.job_id for ref in receipt.invalidated] == [7]
    assert revised.stage == "build" and revised.optimization_checkpoints == {}
    assert revised.current_ts_guess_path == ""
    assert revised.structures["reactant"]["normalization"]["status"] == "pending"


@pytest.mark.parametrize("role", ["reactant", "product", "both"])
@pytest.mark.parametrize("engine", ["orca", "gaussian"])
def test_labelled_renumbering_preserves_canonical_inherited_references(tmp_path, role, engine):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path)
    record.input.guess.calculation.engine = engine
    before = record.input.model_copy(deep=True)
    permutation = [2, 0, 1]  # New rows contain old atoms 2, 0, 1.
    for side in (["reactant", "product"] if role == "both" else [role]):
        _write_source(tmp_path, side, Chem.RenumberAtoms(mol, permutation))
    change = request(record, {})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.input.reaction == before.reaction
    assert revised.input.conformers.guidance == before.conformers.guidance
    assert revised.input.guess == before.guess


def test_unique_full_graph_renumbering_without_labels_preserves_canonical_atom_references(tmp_path):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path, smiles="F[C@](Cl)(Br)I", labels=False)
    permutation = [4, 3, 2, 1, 0]
    _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, permutation))
    change = request(record, {})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.input.reaction.atom_map == [0, 1, 2, 3, 4]
    assert revised.input.reaction.reaction_center == [(0, 1)]
    assert revised.input.guess.scans[0].atoms == [0, 1]


def test_unlabelled_symmetric_update_blocks_unproved_canonical_order(tmp_path):
    from rdkit import Chem

    from cloudra.tools.core.ts_inputs import XtbPathGuess

    record, mol = _identity_fixture(tmp_path, labels=False)
    record.input.guess = XtbPathGuess(kind="xtb_path", method="GFN2-xTB")
    _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [0, 2, 1]))
    change = request(record, {})
    with pytest.raises(ValueError, match="atom correspondence is unproved"):
        plan_input_revision(record, change)
    assert record.input.reaction.atom_map == [0, 1, 2]
    assert record.input.guess.kind == "xtb_path"


@pytest.mark.parametrize("mutation", ["isotope", "label", "stereo", "species"])
def test_changed_atom_identity_or_chemical_graph_cannot_inherit_references(tmp_path, mutation):
    record, mol = _identity_fixture(tmp_path, smiles="F[C@](Cl)(Br)I")
    if mutation == "isotope":
        mol.GetAtomWithIdx(0).SetIsotope(19)
    elif mutation == "label":
        mol.GetAtomWithIdx(0).SetAtomMapNum(0)
    elif mutation == "stereo":
        mol.GetAtomWithIdx(1).InvertChirality()
        for index in range(mol.GetNumAtoms()):
            point = mol.GetConformer().GetAtomPosition(index)
            mol.GetConformer().SetAtomPosition(index, (-point.x, point.y, point.z))
    else:
        mol.GetAtomWithIdx(0).SetAtomicNum(7)
    _write_source(tmp_path, "reactant", mol)
    change = request(record, {})
    with pytest.raises(ValueError, match="atom correspondence is unproved"):
        plan_input_revision(record, change)
    assert record.input.reaction.atom_map == [0, 1, 2, 3, 4]


@pytest.mark.parametrize("renumber", [False, True])
def test_inherited_heavy_binding_refreshes_digest_and_preserves_one_based_indices(tmp_path, renumber):
    from rdkit import Chem

    from cloudra.tools.core.ts_inputs import HeavyAtomBinding
    from cloudra.tools.core.ts_process import _bound_input_structure

    record, mol = _identity_fixture(tmp_path, smiles="F[C@](Cl)(Br)I", labels=False)
    record.input.conformers.reactant.heavy_atom_binding = HeavyAtomBinding(
        structure_digest=record.structures["reactant"]["structure_digest"], indices=[1, 2, 3, 4, 5])
    old_digest = record.input.conformers.reactant.heavy_atom_binding.structure_digest
    if renumber:
        mol = Chem.RenumberAtoms(mol, [4, 3, 2, 1, 0])
    else:
        point = mol.GetConformer().GetAtomPosition(0)
        mol.GetConformer().SetAtomPosition(0, (point.x + .01, point.y, point.z))
    _write_source(tmp_path, "reactant", mol)
    change = request(record, {})
    revised = revise_record(record, change, plan_input_revision(record, change))
    binding = revised.input.conformers.reactant.heavy_atom_binding
    assert binding.indices == [1, 2, 3, 4, 5]
    assert (binding.structure_digest == old_digest) is renumber
    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process
    from cloudra.tools.core.ts_process import TsProcessRecord
    from tests.test_ts_revision_canonical_overwrite import _ledger
    db = _ledger(tmp_path, record)
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    commit_input_revision(db, process_id=record.pipeline_id, request=change,
                          record=revised.model_dump(mode="json"), receipt=receipt)
    revised = TsProcessRecord.model_validate(get_process(db, record.pipeline_id)["record"])
    # Verify the normal downstream input identity reader accepts the refreshed
    # binding. Scientific geometry qualification is independent of this test.
    from cloudra.tools.core.ts_process import _build
    guidance = revised.input.conformers.guidance
    revised.input.conformers.guidance = ConformerGuidance()
    _build(revised)
    revised.input.conformers.guidance = guidance
    assert revised.blocked is None
    assert revised.structures["reactant"]["structure_digest"] == binding.structure_digest
    _bound_input_structure(revised, "reactant", require_identity=False, persist_artifact=False)


@pytest.mark.parametrize("kind", ["generate", "catalog"])
def test_recorded_constructed_geometry_can_be_replaced_by_identical_file(tmp_path, kind):
    from cloudra.tools.core.ts_inputs import CatalogConformer, GeneratedConformer

    record, mol = _identity_fixture(tmp_path)
    before = record.input.model_copy(deep=True)
    record.input.conformers.reactant = (GeneratedConformer(kind="generate", generation="ETKDGv3", seed=42)
        if kind == "generate" else CatalogConformer(kind="catalog", catalog_id="catalog", candidate_id="candidate", partition_revision="partition"))
    record.structures["reactant"]["source_kind"] = kind
    replacement = _write_source(tmp_path / "copy", "reactant", mol)
    change = request(record, dict(conformers=dict(reactant=replacement)))
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.input.reaction == before.reaction
    assert revised.input.conformers.guidance == before.conformers.guidance
    assert revised.input.guess == before.guess


def test_explicit_replacement_references_are_not_translated_twice(tmp_path):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path)
    _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    guess = record.input.guess.model_dump()
    guess["scans"][0]["atoms"], guess["freeze"][0]["atoms"] = [1, 2], [1, 0]
    change = request(record, dict(reaction=dict(atom_map=[1, 2, 0], reaction_center=[[1, 2]]),
        conformers=dict(guidance=dict(ring_order=[1, 2, 0], distance_filters=[dict(atoms=[1, 2], min_ang=.5, max_ang=2.)])),
        guess=guess))
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.input.reaction.atom_map == [0, 1, 2]
    assert revised.input.reaction.reaction_center == [(0, 1)]
    assert revised.input.conformers.guidance.ring_order == [0, 1, 2]
    assert revised.input.guess.scans[0].atoms == [0, 1]
    assert revised.input.guess.freeze[0].atoms == [0, 2]


def test_revision_transaction_commits_canonical_declarations_and_replay_once(tmp_path):
    from rdkit import Chem

    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import (
        commit_input_revision,
        create_process,
        get_process,
        save_process_record,
    )
    from tests.test_ts_pipeline_store import payload

    record, mol = _identity_fixture(tmp_path)
    db = ComputeDB(data_dir=tmp_path / "ledger").init()
    declaration = payload(workspace_dir=str(tmp_path))
    declaration["input"] = record.input.model_dump(mode="json")
    record.pipeline_id = create_process(db, request_key="prepare", payload=declaration)["process_id"]
    save_process_record(db, process_id=record.pipeline_id, record=record.model_dump(mode="json"))
    record.revision = get_process(db, record.pipeline_id)["revision"]
    _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    change = request(record, {})
    receipt = plan_input_revision(record, change)
    revised = revise_record(record, change, receipt)
    commit_input_revision(db, process_id=record.pipeline_id, request=change, record=revised.model_dump(mode="json"), receipt=receipt)
    accepted = get_process(db, record.pipeline_id)
    assert accepted["record"]["input"]["reaction"]["atom_map"] == [0, 1, 2]
    assert accepted["record"]["input"]["guess"]["scans"][0]["atoms"] == [0, 1]
    commit_input_revision(db, process_id=record.pipeline_id, request=change, record=revised.model_dump(mode="json"), receipt=receipt)
    assert get_process(db, record.pipeline_id) == accepted


def test_conflicting_stable_xyz_identity_tags_cannot_be_ignored_as_comments(tmp_path):
    record, _ = _identity_fixture(tmp_path, labels=False)
    source = Path(record.input.conformers.reactant.xyz_path)
    snapshot = Path(record.current_seed_xyz_path)
    old_rows = snapshot.read_text().splitlines()
    old_rows[2:] = [row + f" in:{index}" for index, row in enumerate(old_rows[2:])]
    snapshot.write_text("\n".join(old_rows) + "\n")
    new_rows = list(old_rows)
    new_rows[3] = new_rows[3].replace("in:1", "in:2")
    new_rows[4] = new_rows[4].replace("in:2", "in:1")
    source.write_text("\n".join(new_rows) + "\n")
    change = request(record, {})
    with pytest.raises(ValueError, match="atom correspondence is unproved"):
        plan_input_revision(record, change)


def test_stale_explicit_and_inherited_heavy_binding_digests_fail_loud(tmp_path):
    from cloudra.tools.core.ts_inputs import HeavyAtomBinding

    record, mol = _identity_fixture(tmp_path, smiles="F[C@](Cl)(Br)I", labels=False)
    record.input.conformers.reactant.heavy_atom_binding = HeavyAtomBinding(structure_digest="stale", indices=[1, 2, 3, 4, 5])
    point = mol.GetConformer().GetAtomPosition(0)
    mol.GetConformer().SetAtomPosition(0, (point.x + .01, point.y, point.z))
    replacement = _write_source(tmp_path, "reactant", mol)
    with pytest.raises(ValueError, match="structure digest is stale"):
        plan_input_revision(record, request(record, {}))
    replacement["heavy_atom_binding"] = dict(structure_digest="explicit-new-digest", indices=[1, 2, 3, 4, 5])
    change = request(record, dict(conformers=dict(reactant=replacement)))
    with pytest.raises(ValueError, match="explicit heavy-atom binding structure digest is stale"):
        plan_input_revision(record, change)


def test_inherited_heavy_binding_never_reinterprets_zero_as_last_atom(tmp_path):
    from cloudra.tools.core.ts_inputs import HeavyAtomBinding

    record, mol = _identity_fixture(tmp_path)
    record.input.conformers.reactant.heavy_atom_binding = HeavyAtomBinding(
        structure_digest=record.structures["reactant"]["structure_digest"], indices=[0])
    point = mol.GetConformer().GetAtomPosition(1)
    mol.GetConformer().SetAtomPosition(1, (point.x + .01, point.y, point.z))
    _write_source(tmp_path, "reactant", mol)
    with pytest.raises(ValueError, match="heavy-atom binding indices"):
        plan_input_revision(record, request(record, {}))


@pytest.mark.parametrize("explicit", [False, True])
def test_ambiguous_reactant_requires_redeclaration_of_inherited_rotation_axis(tmp_path, explicit):
    from rdkit import Chem

    from cloudra.tools.core.ts_inputs import RotatedConformer

    record, mol = _identity_fixture(tmp_path, labels=False)
    record.input.conformers.product = RotatedConformer(kind="rotate_about_bond", atoms=(0, 1), degrees=60.)
    _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, [0, 2, 1]))
    changes = dict(conformers=dict(product=dict(kind="rotate_about_bond", atoms=[0, 2], degrees=60.))) if explicit else {}
    change = request(record, changes)
    with pytest.raises(ValueError, match="atom correspondence is unproved"):
        plan_input_revision(record, change)
    assert record.input.conformers.product.atoms == (0, 1)


def test_species_edit_cannot_launder_an_invalid_old_heavy_binding(tmp_path):
    from cloudra.tools.core.ts_inputs import HeavyAtomBinding

    record, _ = _identity_fixture(tmp_path, smiles="CCO", labels=False)
    record.input.conformers.reactant.heavy_atom_binding = HeavyAtomBinding(
        structure_digest=record.structures["reactant"]["structure_digest"], indices=[3, 2, 1])
    # This backwards binding is invalid against CCO but becomes valid against
    # OCC. Updating its digest without checking the old meaning would bless it.
    change = request(record, dict(reaction=dict(reactant_smiles="OCC")))
    with pytest.raises(ValueError, match="inherited heavy-atom binding"):
        plan_input_revision(record, change)


def test_proved_renumbering_translates_stable_xyz_identity_assertions_with_atoms(tmp_path):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path)
    snapshot = Path(record.current_seed_xyz_path)
    rows = snapshot.read_text().splitlines()
    rows[2:] = [row + f" in:{index}" for index, row in enumerate(rows[2:])]
    snapshot.write_text("\n".join(rows) + "\n")
    permutation = [2, 0, 1]
    replacement = _write_source(tmp_path, "reactant", Chem.RenumberAtoms(mol, permutation))
    xyz = Path(replacement["xyz_path"])
    rows = xyz.read_text().splitlines()
    rows[2:] = [row + f" in:{old_index}" for row, old_index in zip(rows[2:], permutation)]
    xyz.write_text("\n".join(rows) + "\n")
    change = request(record, {})
    revised = revise_record(record, change, plan_input_revision(record, change))
    assert revised.input.reaction.atom_map == [0, 1, 2]
    assert revised.input.guess.scans[0].atoms == [0, 1]


def test_source_reordered_after_accepted_revision_blocks_before_copying_new_atoms(tmp_path):
    from rdkit import Chem

    from cloudra.tools.core.ts_process import _build

    record, mol = _identity_fixture(tmp_path)
    replacement = _write_source(tmp_path / "copy", "reactant", mol)
    change = request(record, dict(conformers=dict(reactant=replacement)))
    revised = revise_record(record, change, plan_input_revision(record, change))
    _write_source(tmp_path / "copy", "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
    _build(revised)
    assert revised.blocked is not None
    assert revised.blocked.failure_class == "conformer_source_invalid"
    assert revised.blocked.needs == ["conformers.reactant"]
    assert not (Path(record.run_dir) / "build" / "input_0002" / "reactant" / "seed.xyz").exists()


def test_source_change_during_atom_identity_proof_rejects_revision(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.tools.core import ts_revision

    record, mol = _identity_fixture(tmp_path)
    replacement = _write_source(tmp_path / "copy", "reactant", mol)
    change = request(record, dict(conformers=dict(reactant=replacement)))
    receipt = plan_input_revision(record, change)
    original = ts_revision._graph_atom_permutation

    def mutate_after_proof(*args, **kwargs):
        permutation = original(*args, **kwargs)
        _write_source(tmp_path / "copy", "reactant", Chem.RenumberAtoms(mol, [2, 0, 1]))
        return permutation

    monkeypatch.setattr(ts_revision, "_graph_atom_permutation", mutate_after_proof)
    with pytest.raises(ValueError, match="source changed during input revision"):
        revise_record(record, change, receipt)


def test_build_copies_the_captured_proved_bytes_even_if_live_file_changes(tmp_path, monkeypatch):
    from rdkit import Chem

    from cloudra.tools.core.ts_process import _build

    record, mol = _identity_fixture(tmp_path)
    replacement = _write_source(tmp_path / "copy", "reactant", mol)
    change = request(record, dict(conformers=dict(reactant=replacement)))
    revised = revise_record(record, change, plan_input_revision(record, change))
    # Guidance qualification is not part of this file capture invariant.
    revised.input.conformers.guidance = ConformerGuidance()
    source = Path(replacement["xyz_path"])
    accepted = source.read_bytes()
    reordered = Chem.MolToXYZBlock(Chem.RenumberAtoms(mol, [2, 0, 1]))
    original = Path.read_bytes
    changed = False

    def mutate_after_capture(path):
        nonlocal changed
        data = original(path)
        if path == source and not changed:
            changed = True
            source.write_text(reordered)
        return data

    monkeypatch.setattr(Path, "read_bytes", mutate_after_capture)
    _build(revised)
    assert changed
    assert revised.blocked is None
    assert Path(revised.current_seed_xyz_path).read_bytes() == accepted
    assert source.read_bytes() != accepted
    assert "revision_source_hashes" not in revised.input_binding


@pytest.mark.parametrize("renumber", [False, True])
def test_source_change_between_plan_and_revision_cannot_reuse_stale_dependency_receipt(tmp_path, renumber):
    from rdkit import Chem

    record, mol = _identity_fixture(tmp_path)
    change = request(record, dict(ts_optimization=dict(engine="orca", method="HF/STO-3G", keywords="")))
    receipt = plan_input_revision(record, change)
    assert receipt.changes == ["ts_optimization.keywords", "ts_optimization.method"]
    if renumber:
        mol = Chem.RenumberAtoms(mol, [2, 0, 1])
    else:
        point = mol.GetConformer().GetAtomPosition(1)
        mol.GetConformer().SetAtomPosition(1, (point.x + .01, point.y, point.z))
    _write_source(tmp_path, "reactant", mol)
    with pytest.raises(ValueError, match="revision plan changed"):
        revise_record(record, change, receipt)
    assert record.input.reaction.atom_map == [0, 1, 2]
