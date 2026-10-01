import pytest

from tests.test_conformer_catalog import make_candidate


def test_periodic_dihedral_distance():
    from cloudra.tools.core.conformer_regions import periodic_difference

    assert periodic_difference(179, -179) == 2


def test_local_reaction_difference_survives_small_global_rmsd(tmp_path):
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates

    near = make_candidate(tmp_path)
    far = make_candidate(tmp_path, geometry_ref='', positions=[[0, 0, 0], [2.1, 0, 0]])
    config = RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1', 'O1'], tolerance=0.5)])
    snapshot = partition_candidates([near, far], config)
    assert len(snapshot.regions) == 2
    assert partition_candidates([far, near], config).revision == snapshot.revision


def test_symmetry_relabel_preserves_region(tmp_path):
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates

    a = make_candidate(tmp_path)
    b = make_candidate(tmp_path, atom_ids=['O1', 'C1'], symbols=['O', 'C'],
                       positions=[[1.4, 0, 0], [0, 0, 0]], generator='renumbered')
    config = RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1', 'O1'])])
    assert len(partition_candidates([a, b], config).regions) == 1


def test_missing_or_degenerate_descriptor_never_merges_silently(tmp_path):
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates

    a = make_candidate(tmp_path)
    b = make_candidate(tmp_path, generator='second')
    config = RegionConfig(descriptor_specs=[DescriptorSpec(kind='dihedral', stable_atom_ids=['C1', 'O1', 'X', 'Y'])])
    snapshot = partition_candidates([a, b], config)
    assert len(snapshot.regions) == 2
    assert all(desc.missing for desc in snapshot.descriptors.values())


def test_energy_change_does_not_change_region(tmp_path):
    from cloudra.tools.core.conformer_catalog import EnergyObservation
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates

    config = RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1', 'O1'])])
    a = make_candidate(tmp_path)
    b = make_candidate(tmp_path, energies=[EnergyObservation(value=100, unit='kcal/mol', method_fingerprint='m',
                                                            species_key=a.species_key)])
    assert partition_candidates([a], config).revision == partition_candidates([b], config).revision


def test_repartition_keeps_old_snapshot(tmp_path):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.conformer_store import get_region_snapshot, put_candidate, put_region_snapshot
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates

    db = ComputeDB(data_dir=tmp_path / 'data')
    a, b = make_candidate(tmp_path), make_candidate(tmp_path, generator='second', geometry_ref='',
                                                  positions=[[0, 0, 0], [2, 0, 0]])
    for c in [a, b]:
        put_candidate(db, c)
    old = partition_candidates([a, b], RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1', 'O1'], tolerance=0.5)]))
    new = partition_candidates([a, b], RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1', 'O1'], tolerance=1)]), previous=old)
    for snapshot in [old, new]:
        put_region_snapshot(db, snapshot, project_id='project', owner_id='owner')
    saved = get_region_snapshot(db, 'cat', old.revision, project_id='project', owner_id='owner')
    assert len(saved.regions) == 2
    assert len(new.regions) == 1
    assert new.previous_revision == old.revision
    assert set(new.region_mapping) == set(old.regions)


def test_optimized_children_share_region_keep_two_parents(tmp_path):
    from cloudra.tools.core.conformer_regions import DescriptorSpec, RegionConfig, partition_candidates

    a = make_candidate(tmp_path, parent_id='p1', generator='opt')
    b = make_candidate(tmp_path, parent_id='p2', generator='opt')
    snapshot = partition_candidates([a, b], RegionConfig(descriptor_specs=[DescriptorSpec(kind='distance', stable_atom_ids=['C1', 'O1'])]))
    assert len(snapshot.regions) == 1
    assert set(next(iter(snapshot.regions.values())).member_ids) == {a.candidate_id, b.candidate_id}


def test_collinear_dihedral_is_missing(tmp_path):
    from cloudra.tools.core.conformer_regions import DescriptorSpec, describe_candidate

    c = make_candidate(tmp_path, geometry_ref='', atom_ids=['a','b','c','d'], fragment_ids=['f']*4,
                       symbols=['C']*4, positions=[[0,0,0],[1,0,0],[2,0,0],[3,0,0]])
    result = describe_candidate(c, [DescriptorSpec(kind='dihedral', stable_atom_ids=['a','b','c','d'])])
    assert not result.values
    assert list(result.missing.values()) == ['degenerate geometry']


def test_invalid_descriptor_rejected():
    from cloudra.tools.core.conformer_regions import DescriptorSpec

    with pytest.raises(ValueError):
        DescriptorSpec(kind='distance', stable_atom_ids=['a'], tolerance=0)


def test_key_torsion_prefers_heavy_neighbors_and_explains_relevance():
    pytest.importorskip("rdkit", reason="requires RDKit (chem extra)")
    from rdkit import Chem

    from cloudra.tools.core.conformer_regions import build_descriptor_specs
    mol=Chem.AddHs(Chem.MolFromSmiles('CCCC'))
    for atom in mol.GetAtoms():
        atom.SetProp('cloudra_atom_id',('z' if atom.GetAtomicNum()!=1 else 'a')+str(atom.GetIdx()))
    specs=build_descriptor_specs(mol,['z1'],[])
    torsion=next(s for s in specs if s.kind=='dihedral' and {'z1','z2'}<=set(s.stable_atom_ids))
    assert all(a.startswith('z') for a in torsion.stable_atom_ids)
    assert 'reaction' in torsion.reason
