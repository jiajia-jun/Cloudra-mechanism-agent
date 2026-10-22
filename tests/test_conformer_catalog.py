"""Archive behavior against real temporary compute.db, no engine calls."""
import shutil

import pytest

from cloudra.persistence.database import ComputeDB


def make_candidate(tmp_path, **overrides):
    Chem = pytest.importorskip('rdkit.Chem', reason='requires RDKit (chem extra)')

    from cloudra.tools.core.conformer_catalog import CandidateRecord

    geometry = tmp_path / 'seed.xyz'
    geometry.write_text('2\nsynthetic geometry\nC 0 0 0\nO 1.4 0 0\n')
    symbols = overrides.pop('symbols', ['C', 'O'])
    atom_ids = overrides.pop('atom_ids', ['C1', 'O1'])
    fragment_ids = overrides.pop('fragment_ids', ['f1', 'f1'])
    rw = Chem.RWMol()
    for symbol in symbols:
        rw.AddAtom(Chem.Atom(symbol))
    mol = rw.GetMol()
    conf = Chem.Conformer(len(symbols))
    for index, point in enumerate(overrides.pop('positions', [[0, 0, 0], [1.4, 0, 0]])):
        conf.SetAtomPosition(index, point)
        mol.GetAtomWithIdx(index).SetProp('cloudra_atom_id', atom_ids[index])
        mol.GetAtomWithIdx(index).SetProp('cloudra_fragment_id', fragment_ids[index])
    mol.AddConformer(conf)
    fields = dict(catalog_id='cat', project_id='project', owner_id='owner', species_key='CO:neutral:singlet',
                  mol=mol, geometry_ref=str(geometry), generator='fixture', seed=42)
    fields.update(overrides)
    return CandidateRecord(**fields)


def test_candidate_id_survives_move_and_retry(tmp_path):
    from cloudra.services.conformer_store import list_candidates, put_candidate

    db = ComputeDB(data_dir=tmp_path / 'data')
    first = make_candidate(tmp_path)
    moved = tmp_path / 'moved.xyz'
    shutil.copyfile(first.geometry_ref, moved)
    second = make_candidate(tmp_path, geometry_ref=str(moved))
    assert first.candidate_id == second.candidate_id
    assert put_candidate(db, first) == put_candidate(db, second)
    assert len(list_candidates(db, 'cat', project_id='project', owner_id='owner')) == 1


def test_optimization_child_preserves_parent(tmp_path):
    from cloudra.services.conformer_store import list_candidates, put_candidate

    db = ComputeDB(data_dir=tmp_path / 'data')
    parent = make_candidate(tmp_path)
    put_candidate(db, parent)
    child = make_candidate(tmp_path, parent_id=parent.candidate_id, positions=[[0, 0, 0], [1.2, 0, 0]],
                           geometry_ref='', generator='optimization', job_ids=[17])
    put_candidate(db, child)
    rows = list_candidates(db, 'cat', project_id='project', owner_id='owner')
    assert len(rows) == 2
    assert next(r for r in rows if r.candidate_id == parent.candidate_id).positions[1][0] == 1.4
    assert next(r for r in rows if r.parent_id).job_ids == [17]


def test_failed_candidate_keeps_artifacts(tmp_path):
    from cloudra.services.conformer_store import list_candidates, put_candidate
    from cloudra.tools.core.conformer_catalog import Qualification

    db = ComputeDB(data_dir=tmp_path / 'data')
    row = make_candidate(tmp_path, state='failed', qualification=Qualification(status='rejected', reasons=['SCF failed']))
    put_candidate(db, row)
    saved = list_candidates(db, 'cat', project_id='project', owner_id='owner')[0]
    assert saved.energies == []
    assert saved.qualification.reasons == ['SCF failed']
    assert saved.geometry_ref.endswith('seed.xyz')


def test_identity_variants_stay_separate(tmp_path):
    assert make_candidate(tmp_path).candidate_id != make_candidate(tmp_path, species_key='CO:charged:doublet').candidate_id


def test_cross_method_energy_not_comparable():
    from cloudra.tools.core.conformer_catalog import EnergyObservation, relative_energies

    observations = {
        'a': EnergyObservation(value=-1, unit='Ha', method_fingerprint='xtb', species_key='s'),
        'b': EnergyObservation(value=-1, unit='Ha', method_fingerprint='mmff', species_key='s'),
    }
    with pytest.raises(ValueError, match='comparable'):
        relative_energies(observations)


def test_energy_units_normalized_and_missing_not_zero():
    from cloudra.tools.core.conformer_catalog import EnergyObservation, relative_energies

    assert relative_energies({'a': EnergyObservation(value=0, unit='kcal/mol', method_fingerprint='m', species_key='s', convergence='converged'),
                              'b': EnergyObservation(value=4.184, unit='kJ/mol', method_fingerprint='m', species_key='s', convergence='converged')}) == {'a': 0, 'b': 1}
    with pytest.raises(ValueError, match='finite'):
        EnergyObservation(value=float('nan'), unit='Ha', method_fingerprint='m', species_key='s', convergence='converged')


def test_archive_rejects_changed_geometry_and_foreign_parent(tmp_path):
    from cloudra.services.conformer_store import put_candidate

    db = ComputeDB(data_dir=tmp_path / 'data')
    row = make_candidate(tmp_path)
    from pathlib import Path
    Path(row.geometry_ref).write_text('modified')
    with pytest.raises(ValueError, match='geometry'):
        put_candidate(db, row)
    orphan = make_candidate(tmp_path, parent_id='missing')
    with pytest.raises(ValueError, match='parent'):
        put_candidate(db, orphan)


def test_catalog_requires_matching_owner(tmp_path):
    from cloudra.services.conformer_store import list_candidates, put_candidate

    db = ComputeDB(data_dir=tmp_path / 'data')
    put_candidate(db, make_candidate(tmp_path))
    with pytest.raises(ValueError, match='owner'):
        list_candidates(db, 'cat', project_id='project', owner_id='stranger')


def test_reinitializing_old_database_keeps_jobs(tmp_path):
    from cloudra.services.conformer_store import put_candidate

    db = ComputeDB(data_dir=tmp_path / 'data').init()
    with db.connect() as con:
        con.execute("INSERT INTO compute_jobs (conversation_id,state,path) VALUES ('existing','running','original')")
    put_candidate(ComputeDB.from_path(db.path), make_candidate(tmp_path))
    with db.connect() as con:
        assert con.execute('SELECT state,path FROM compute_jobs').fetchall() == [('running', 'original')]


def test_energy_without_convergence_evidence_is_unknown():
    from cloudra.tools.core.conformer_catalog import EnergyObservation
    observation = EnergyObservation(value=-1, unit='Ha', method_fingerprint='fixture', species_key='fixture')
    assert observation.convergence == 'unknown'
