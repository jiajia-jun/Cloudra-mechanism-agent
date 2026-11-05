from pathlib import Path

import pytest

pytest.importorskip('rdkit')
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402


def test_raw_geometry_saved_before_mmff(tmp_path, monkeypatch):
    from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema

    def forbidden(*args, **kwargs):
        pytest.fail('regions generation must not optimize all candidates')
    monkeypatch.setattr(AllChem, 'MMFFOptimizeMoleculeConfs', forbidden)
    tool = ConformerSearch()
    request = ConformerSearch_input_schema(smiles='CCCC', output_dir=str(tmp_path), num_confs=4,
                                           catalog_mode='regions')
    result = tool._run_regions(request, str(tmp_path))
    assert result.is_success
    assert result.catalog_id
    assert result.region_snapshot_path
    import json
    archived = json.loads(Path(result.catalog_path).read_text())
    assert len(archived['candidates']) == 4
    assert all(c['state'] == 'generated' and not c['energies'] for c in archived['candidates'])


def test_archive_precedes_energy_and_rmsd_filters(tmp_path):
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.conformer_catalog import EnergyObservation

    mol = Chem.AddHs(Chem.MolFromSmiles('CCCC'))
    AllChem.EmbedMultipleConfs(mol, numConfs=3, randomSeed=42)
    captured = []
    capture = CandidateCapture(catalog_id='c', project_id='p', owner_id='o', output_dir=str(tmp_path), sink=captured.append)
    parents = [capture.capture(mol, cid, generator='ETKDG', seed=42) for cid in range(3)]
    for cid, energy in enumerate([0, 100, 100]):
        capture.capture(mol, cid, generator='MMFF', parent_id=parents[cid].candidate_id, state='optimized',
                        energies=[EnergyObservation(value=energy,unit='kcal/mol',method_fingerprint='MMFF',species_key=parents[cid].species_key)])
    assert len(captured) == 6
    assert sum(c.state == 'generated' for c in captured) == 3
    assert [c.energies[0].value for c in captured if c.energies] == [0,100,100]


def test_independent_sampler_reproducible_and_no_collision():
    import numpy as np

    from cloudra.tools.core.complex_assembly import AssemblyParameters, sample_independent_placements

    mol = Chem.AddHs(Chem.MolFromSmiles('O.O.O'))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    groups = [list(group) for group in Chem.GetMolFrags(mol)]
    result = sample_independent_placements(mol, groups, seed=42, count=3, parameters=AssemblyParameters())
    repeat = sample_independent_placements(mol, groups, seed=42, count=3, parameters=AssemblyParameters())
    assert result[0].positions == repeat[0].positions
    assert result[0].fragment_transforms[1] != result[0].fragment_transforms[2]
    for placement in result:
        positions = np.asarray(placement.positions)
        assert min(np.linalg.norm(positions[i]-positions[j]) for g in range(3) for h in range(g+1,3)
                   for i in groups[g] for j in groups[h]) >= 1 - 1e-8


def test_legacy_output_unchanged():
    from cloudra.tools.Chemtool.conformer_search import ConformerSearch_input_schema

    assert ConformerSearch_input_schema(smiles='CCCC').catalog_mode == 'legacy'


def test_guided_rejected_candidates_keep_reason(tmp_path):
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.preorganization import search_guided
    from cloudra.tools.core.structure_builder import StructureInput

    capture = CandidateCapture(catalog_id='c', project_id='p', owner_id='o', output_dir=str(tmp_path))
    search_guided(structure=StructureInput(kind='smiles', value='CCCC'), output_dir=str(tmp_path / 'guided'),
                  ring_order=[], distance_filters=[{'atoms':[1,4],'min_ang':3,'max_ang':4}],
                  num_confs=3, candidate_sink=capture)
    assert sum(c.state == 'generated' for c in capture.records) > 0
    assert any(c.parent_id for c in capture.records)
    assert all(c.qualification.status != 'unknown' for c in capture.records if c.parent_id)


def test_guided_warning_stays_qualified_and_survives_archive(tmp_path, monkeypatch):
    from cloudra.tools.core import preorganization
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.conformer_catalog import CandidateRecord
    from cloudra.tools.core.structure_builder import StructureInput

    real_qualify = preorganization.qualify_geometry
    warning = 'Warning: test inferred contact; molecular graph unchanged'

    def qualify_with_warning(*args, **kwargs):
        passed, reasons, distances, warnings = real_qualify(*args, **kwargs)
        return passed, reasons, distances, [*warnings, warning]

    monkeypatch.setattr(preorganization, 'qualify_geometry', qualify_with_warning)
    capture = CandidateCapture(catalog_id='c', project_id='p', owner_id='o', output_dir=str(tmp_path),
        sink=lambda record: (tmp_path / f'{record.candidate_id}.json').write_text(record.model_dump_json()))
    result = preorganization.search_guided(
        structure=StructureInput(kind='smiles', value='CCCC'), output_dir=str(tmp_path / 'guided'),
        ring_order=[], distance_filters=[{'atoms': [1, 4], 'min_ang': 3, 'max_ang': 4}],
        num_confs=3, candidate_sink=capture)

    assert result.status == 'ok', result.message
    qualified = [record for record in capture.records if record.qualification.status == 'qualified']
    assert qualified
    for record in qualified:
        restored = CandidateRecord.model_validate_json((tmp_path / f'{record.candidate_id}.json').read_text())
        assert restored.state == 'optimized'
        assert restored.qualification.status == 'qualified'
        assert warning in restored.qualification.reasons


def test_rdkit_archive_keeps_all_raw_and_optimized_before_screening(tmp_path):
    from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema
    from cloudra.tools.core.conformer_capture import CandidateCapture

    capture = CandidateCapture(catalog_id='c', project_id='p', owner_id='o', output_dir=str(tmp_path))
    result = ConformerSearch()._run_rdkit(ConformerSearch_input_schema(smiles='CCCC', num_confs=4),
                                        str(tmp_path), candidate_sink=capture)
    assert result.is_success
    assert sum(c.state == 'generated' for c in capture.records) == 4
    assert sum(c.parent_id is not None for c in capture.records) == 4


def test_regions_generates_multicomponent_raw_choices(tmp_path):
    from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema

    result = ConformerSearch()._run_regions(ConformerSearch_input_schema(smiles='O.O',num_confs=2,
                                          catalog_mode='regions',output_dir=str(tmp_path)),str(tmp_path))
    assert result.is_success, result.message
    assert result.catalog_id


def test_regions_preserve_raw_multicomponent_diversity_and_placement_lineage(tmp_path):
    import json

    import numpy as np

    from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema
    from cloudra.tools.core.conformer_catalog import CandidateRecord
    result = ConformerSearch()._run_regions(ConformerSearch_input_schema(smiles='CCCC.O', num_confs=6, random_seed=42, catalog_mode='regions'), str(tmp_path))
    assert result.is_success, result.message
    records = [CandidateRecord.model_validate(row) for row in json.loads(Path(result.catalog_path).read_text())['candidates']]
    raw = {c.candidate_id: c for c in records if c.generator == 'ETKDGv3'}
    placed = [c for c in records if c.generator == 'independent_rigid_fragments']
    assert len(raw) == len(placed) == 6
    for child in placed:
        parent = raw[child.parent_id]
        a, b = np.asarray(parent.positions), np.asarray(child.positions)
        for fragment in set(parent.fragment_ids):
            indices = [i for i, fid in enumerate(parent.fragment_ids) if fid == fragment]
            assert np.allclose(np.linalg.norm(a[indices,None]-a[None,indices],axis=-1), np.linalg.norm(b[indices,None]-b[None,indices],axis=-1))
        assert child.parameters['fragment_transforms']


@pytest.mark.parametrize('smiles', ['O', 'O.O'])
def test_regions_export_usable_geometries_without_unplaced_parent_files(tmp_path, smiles):
    import json

    from cloudra.persistence.database import ComputeDB
    from cloudra.services.conformer_store import list_candidates
    from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema
    from cloudra.tools.core.conformer_catalog import CandidateRecord

    result = ConformerSearch()._run_regions(
        ConformerSearch_input_schema(smiles=smiles, num_confs=2, catalog_mode='regions'), str(tmp_path),
    )
    assert result.is_success, result.message
    records = [CandidateRecord.model_validate(row)
               for row in json.loads(Path(result.catalog_path).read_text())['candidates']]
    parents = [record for record in records if record.parent_id is None]
    children = [record for record in records if record.parent_id is not None]
    assert len(parents) == 2
    if children:
        # The molecular snapshots preserve lineage; unplaced fragments must not
        # also become ordinary XYZ inputs that discard that context (#224).
        assert len(children) == 2
        assert all(not parent.geometry_ref and not parent.artifact_hash for parent in parents)
        assert all(not (tmp_path / 'catalog_geometries' / f'{parent.candidate_id}.xyz').exists()
                   for parent in parents)
        exported = children
    else:
        exported = parents
    assert all(record.geometry_ref and Path(record.geometry_ref).is_file() for record in exported)
    assert len(list((tmp_path / 'catalog_geometries').glob('*.xyz'))) == 2
    saved = list_candidates(ComputeDB(), result.catalog_id,
                            project_id=records[0].project_id, owner_id=records[0].owner_id)
    assert {record.candidate_id: record.immutable_payload() for record in saved} == {
        record.candidate_id: record.immutable_payload() for record in records
    }


def test_capture_symmetry_equivalent_renumbering_preserves_descriptors(tmp_path):
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.conformer_regions import RegionConfig, build_descriptor_specs, partition_candidates
    mol = Chem.AddHs(Chem.MolFromSmiles('CCCC'))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    hydrogens = [n.GetIdx() for n in mol.GetAtomWithIdx(0).GetNeighbors() if n.GetAtomicNum() == 1]
    order = list(range(mol.GetNumAtoms()))
    order[hydrogens[0]], order[hydrogens[1]] = order[hydrogens[1]], order[hydrogens[0]]
    renamed = Chem.RenumberAtoms(mol, order)
    capture = CandidateCapture(catalog_id='c', project_id='p', owner_id='o', output_dir=str(tmp_path))
    a = capture.capture(mol, 0, generator='fixture')
    b = capture.capture(renamed, 0, generator='renumbered')
    snapshot = partition_candidates([a,b], RegionConfig(descriptor_specs=build_descriptor_specs(mol, [], [])))
    assert len(snapshot.regions) == 1


def test_regions_tool_exports_exploratory_proposals_only_when_requested(tmp_path):
    import json

    from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema
    request=ConformerSearch_input_schema(smiles='CCCC',num_confs=8,catalog_mode='regions',statistical_partition={'seed':42,'resamples':16})
    result=ConformerSearch()._run_regions(request,str(tmp_path))
    assert result.is_success
    data=json.loads(__import__('pathlib').Path(result.statistical_evidence_path).read_text())
    assert data['inference_kind']=='exploratory' and data['formal_p_value'] is None
    assert data['proposals']
    assert json.loads(__import__('pathlib').Path(result.region_snapshot_path).read_text())['partition_method']=='fixed_tolerance_baseline'


def test_component_embedding_and_optimization_are_archived_with_stable_ids(tmp_path):
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.structure_builder import (
        BuildStrategy,
        PreparationRequest,
        StructureInput,
        prepare_structure,
    )
    capture=CandidateCapture(catalog_id='cat',project_id='project',owner_id='owner',output_dir=str(tmp_path/'catalog'))
    prepared=prepare_structure(PreparationRequest(structure=StructureInput(kind='smiles',value='CCO.O'),output_dir=str(tmp_path/'build'),strategy=BuildStrategy(embed=True,optimize=True)),candidate_sink=capture)
    assert prepared.components
    parents=[c for c in capture.records if c.generator=='component_ETKDGv3']
    children=[c for c in capture.records if c.generator.startswith('component_') and c.parent_id]
    assert len(parents)==2 and len(children)==2
    assert all(set(c.atom_ids)==set(next(p for p in parents if p.candidate_id==c.parent_id).atom_ids) for c in children)
    assert all(c.energies or c.state=='failed' for c in children)


def test_crest_returned_high_energy_frame_is_archived_before_filter(tmp_path,monkeypatch):
    from cloudra.tools.Chemtool.conformer_search import ConformerSearch, ConformerSearch_input_schema
    from cloudra.tools.core.conformer_capture import CandidateCapture
    from cloudra.tools.core.crest_runner import CrestConformer, CrestRunResult
    def fake_run(request):
        rows=request.xyz_text.splitlines()[2:]
        symbols=[r.split()[0] for r in rows]
        xyz=[[float(v) for v in r.split()[1:4]] for r in rows]
        return CrestRunResult(run_dir=str(tmp_path),scientific_success=True,returncode=0,
            conformers=[CrestConformer(frame_index=i,energy_eh=e,symbols=symbols,positions=xyz) for i,e in [(0,-1.),(1,0.)]])
    monkeypatch.setattr('cloudra.tools.Chemtool.conformer_search.run_crest',fake_run)
    capture=CandidateCapture(catalog_id='cat',project_id='project',owner_id='owner',output_dir=str(tmp_path/'archive'))
    result=ConformerSearch()._run_crest(ConformerSearch_input_schema(smiles='CC',backend='crest',energy_window_kcal=1),str(tmp_path/'run'),candidate_sink=capture)
    assert result.is_success
    returned=[c for c in capture.records if c.generator=='CREST_returned_frame']
    assert len(returned)==2 and result.counts['within_window']==1
    assert len([c for c in capture.records if c.generator=='CREST_returned_energy' and c.energies[0].artifact_ref])==2
