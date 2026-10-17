"""Catalog and TS checkpoints preserve the supplied molecular state."""

import pytest

pytest.importorskip('rdkit')
from rdkit import Chem  # noqa: E402

from cloudra.persistence.database import ComputeDB  # noqa: E402
from cloudra.tools.core.conformer_capture import CandidateCapture  # noqa: E402


def stateful_molecule(open_shell=False):
    mol = Chem.AddHs(Chem.MolFromSmiles(
        '[13CH2:7][C@H:8](F)[O-].[Na+]' if open_shell else '[13CH3:7][C@H:8](F)[O-].[Na+]'))
    mol.SetProp('source_note', 'input molecular state')
    for atom in mol.GetAtoms():
        atom.SetProp('cloudra_atom_id', f'input-{atom.GetIdx()}')
        atom.SetProp('origin', f'original atom {atom.GetIdx()}')
    mol.GetBondWithIdx(0).SetProp('origin', 'original bond')
    for cid in (3, 7):
        conf = Chem.Conformer(mol.GetNumAtoms())
        conf.SetId(cid)
        conf.SetProp('geometry_note', f'conformer {cid}')
        for index in range(mol.GetNumAtoms()):
            conf.SetAtomPosition(index, (index + cid / 10, cid, -0.123456789123))
        mol.AddConformer(conf, assignId=False)
    return mol


def assert_original_state(mol):
    assert mol.GetProp('source_note') == 'input molecular state'
    assert mol.GetAtomWithIdx(0).GetIsotope() == 13
    assert mol.GetAtomWithIdx(0).GetAtomMapNum() == 7
    assert mol.GetAtomWithIdx(0).GetProp('origin') == 'original atom 0'
    assert mol.GetBondWithIdx(0).GetProp('origin') == 'original bond'
    assert mol.GetAtomWithIdx(3).GetFormalCharge() == -1
    assert mol.GetAtomWithIdx(4).GetFormalCharge() == 1
    assert mol.GetConformer().GetProp('geometry_note') == 'conformer 7'
    assert mol.GetConformer().GetAtomPosition(0).z == -0.123456789123
    assert len(Chem.GetMolFrags(mol)) == 2


def test_capture_and_database_restore_keep_selected_full_molecule(tmp_path):
    from cloudra.services.conformer_store import list_candidates, put_candidate

    source = stateful_molecule()
    before = source.ToBinary(Chem.PropertyPickleOptions.AllProps)
    db = ComputeDB(data_dir=tmp_path / 'data')
    capture = CandidateCapture(catalog_id='catalog', project_id='project', owner_id='owner',
        output_dir=str(tmp_path / 'archive'), sink=lambda row: put_candidate(db, row))
    candidate = capture.capture(source, 7, generator='supplied')

    assert_original_state(candidate.mol)
    assert candidate.mol.GetNumConformers() == 1
    assert candidate.atom_ids[0] == 'input-0'
    assert source.ToBinary(Chem.PropertyPickleOptions.AllProps) == before
    restored = list_candidates(ComputeDB.from_path(db.path), 'catalog', project_id='project', owner_id='owner')[0]
    assert_original_state(restored.mol)
    restored.mol.GetAtomWithIdx(0).SetProp('origin', 'changed detached result')
    assert candidate.mol.GetAtomWithIdx(0).GetProp('origin') == 'original atom 0'


def test_unresolved_frame_stays_explicitly_atom_only_through_archive(tmp_path):
    from cloudra.tools.core.conformer_catalog import CandidateRecord

    capture = CandidateCapture(catalog_id='catalog', project_id='project', owner_id='owner', output_dir=str(tmp_path))
    candidate = capture.capture_unresolved_frame(['Na', 'O'], [[0, 0, 0], [2.2, 0, 0]],
        generator='coordinate frame', parameters={'source_artifact': 'native.xyz'})
    restored = CandidateRecord.model_validate_json(candidate.model_dump_json())
    assert restored.mol.GetNumBonds() == 0
    assert restored.mol.GetProp('cloudra_graph_status') == 'unresolved'
    assert restored.qualification.status == 'unknown'


@pytest.mark.parametrize('open_shell', [False, True])
def test_catalog_selection_and_ts_checkpoint_keep_graph_without_perception(tmp_path, monkeypatch, open_shell):
    from rdkit.Chem import rdDetermineBonds

    from cloudra.services.conformer_store import put_candidate, put_region_snapshot
    from cloudra.tools.core.conformer_catalog import Qualification
    from cloudra.tools.core.conformer_regions import RegionConfig, partition_candidates
    from cloudra.tools.core.ts_candidate_pipeline import use_catalog_source
    from cloudra.tools.core.ts_inputs import CatalogConformer
    from cloudra.tools.core.ts_process import TsProcessRecord, _bound_input_structure
    from tests.test_ts_stage_inputs import record_fixture

    db = ComputeDB().init()
    capture = CandidateCapture(catalog_id='catalog', project_id='project', owner_id='owner',
        output_dir=str(tmp_path / 'archive'), sink=lambda row: put_candidate(db, row),
        multiplicity=2 if open_shell else 1)
    candidate = capture.capture(stateful_molecule(open_shell), 7, generator='supplied',
        qualification=Qualification(status='qualified'))
    snapshot = partition_candidates([candidate], RegionConfig(descriptor_specs=[]))
    put_region_snapshot(db, snapshot, project_id='project', owner_id='owner')
    record = record_fixture(tmp_path / 'run')
    record.input.reaction.reactant_smiles = '[13CH2:7][C@H:8](F)[O-].[Na+]' if open_shell else '[13CH3:7][C@H:8](F)[O-].[Na+]'
    record.input.reaction.charge = 0
    record.input.reaction.multiplicity = 2 if open_shell else 1

    def no_perception(*_args, **_kwargs):
        pytest.fail('known catalog graph was re-perceived')

    monkeypatch.setattr(rdDetermineBonds, 'DetermineBonds', no_perception)
    use_catalog_source(record, CatalogConformer(kind='catalog', catalog_id='catalog', candidate_id=candidate.candidate_id), 'reactant')
    checkpoint = TsProcessRecord.model_validate_json(record.model_dump_json())
    _, bound, _ = _bound_input_structure(checkpoint, 'reactant', require_identity=False)
    assert_original_state(bound)
    assert bound.GetAtomWithIdx(0).GetNumRadicalElectrons() == int(open_shell)
