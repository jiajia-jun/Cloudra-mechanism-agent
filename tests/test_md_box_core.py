import shutil

import pytest


def test_declared_2d_sdf_requires_a_3d_conformer(tmp_path, rdkit_chemistry):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.md_box import _read_template

    ethanol = Chem.AddHs(Chem.MolFromSmiles('CCO'))
    AllChem.Compute2DCoords(ethanol)
    path = tmp_path / 'ethanol.sdf'
    with Chem.SDWriter(str(path)) as writer:
        writer.write(ethanol)

    with pytest.raises(ValueError, match='3D conformer'):
        _read_template(path)


def test_monatomic_ion_template_needs_only_one_position(tmp_path, rdkit_chemistry):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.md_box import _read_template

    sodium = Chem.MolFromSmiles('[Na+]')
    AllChem.Compute2DCoords(sodium)
    path = tmp_path / 'sodium.mol'
    Chem.MolToMolFile(sodium, str(path))

    atoms, _ = _read_template(path)
    assert atoms.get_chemical_symbols() == ['Na']


def test_packmol_candidate_file_without_convergence_is_not_published(tmp_path, monkeypatch):
    from cloudra.tools.core.md_box import build_md_box

    binary = tmp_path / 'packmol'
    binary.write_text(
        '#!/bin/sh\n'
        "printf '1\\nCandidate\\nAr 2 2 2\\n' > packed.xyz\n"
        "printf 'Unable to satisfy packing constraints\\n'\n",
        encoding='utf-8',
    )
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(binary.parent), prepend=':')
    structure = tmp_path / 'argon.xyz'
    structure.write_text('1\nArgon\nAr 0 0 0\n', encoding='utf-8')
    output_dir = tmp_path / 'box'

    with pytest.raises(ValueError, match='Unable to satisfy packing constraints') as error:
        build_md_box(
            [{'structure_path': str(structure), 'count': 1}], output_dir,
            initial_density_g_cm3=None, box_lengths_angstrom=(10, 10, 10),
            min_distance_angstrom=2, seed=17,
        )

    assert 'minimum distance 2 Å, seed 17' in str(error.value)
    assert not output_dir.exists()


def test_packmol_success_with_a_clash_across_the_cell_is_not_published(tmp_path, monkeypatch):
    from cloudra.tools.core.md_box import build_md_box

    binary = tmp_path / 'packmol'
    binary.write_text(
        '#!/bin/sh\n'
        "printf '2\\nPacked\\nAr 0.2 2 2\\nAr 9.8 2 2\\n' > packed.xyz\n"
        "printf 'Version 21.2.3\\nPeriodic boundary condition activated:\\nSuccess!\\n'\n",
        encoding='utf-8',
    )
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(binary.parent), prepend=':')
    structure = tmp_path / 'argon.xyz'
    structure.write_text('1\nArgon\nAr 0 0 0\n', encoding='utf-8')
    output_dir = tmp_path / 'box'

    with pytest.raises(ValueError, match='minimum distance'):
        build_md_box(
            [{'structure_path': str(structure), 'count': 2}], output_dir,
            initial_density_g_cm3=None, box_lengths_angstrom=(10, 10, 10),
            min_distance_angstrom=2, seed=17,
        )

    assert not output_dir.exists()


def test_one_rigid_copy_warns_when_near_its_periodic_image(tmp_path, monkeypatch):
    from cloudra.tools.core.md_box import build_md_box

    binary = tmp_path / 'packmol'
    binary.write_text(
        '#!/bin/sh\n'
        "printf '2\\nPacked\\nAr 0.3 2 2\\nAr 9.7 2 2\\n' > packed.xyz\n"
        "printf 'Version 21.2.3\\nPeriodic boundary condition activated:\\nSuccess!\\n'\n",
        encoding='utf-8',
    )
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', str(binary.parent), prepend=':')
    structure = tmp_path / 'elongated.xyz'
    structure.write_text('2\nRigid pair\nAr 0 0 0\nAr 9.4 0 0\n', encoding='utf-8')
    result = build_md_box(
        [{'structure_path': str(structure), 'count': 1}], tmp_path / 'box',
        initial_density_g_cm3=None, box_lengths_angstrom=(10, 10, 10),
        min_distance_angstrom=2, seed=17,
    )

    assert result['minimum_observed_distance_angstrom'] is None
    assert any('elongated.xyz' in warning and '0.6 Å' in warning for warning in result['warnings'])


def test_density_warning_preserves_reference_without_reported_pressure(tmp_path, rdkit_chemistry):
    if shutil.which('packmol') is None:
        pytest.skip('requires the optional Packmol executable')

    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.core.md_box import build_md_box

    molecule = Chem.AddHs(Chem.MolFromSmiles('CC#N'))
    assert AllChem.EmbedMolecule(molecule, randomSeed=17) == 0
    structure = tmp_path / 'acetonitrile.mol'
    Chem.MolToMolFile(molecule, str(structure))
    result = build_md_box(
        [{'structure_path': str(structure), 'count': 3}], tmp_path / 'box',
        initial_density_g_cm3=0.25, box_lengths_angstrom=None,
        min_distance_angstrom=2, seed=17,
    )

    assert result['density_reference']['pressure_kpa'] is None
    assert len(result['warnings']) == 1
    assert 'pressure' in result['warnings'][0]
