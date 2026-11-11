"""Exercise the public MD box tool and reload its periodic coordinates."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from ase.io import read
from pydantic import ValidationError

from cloudra.tools import get_tools_lst


@pytest.fixture
def packmol():
    if not shutil.which('packmol'):
        pytest.skip('requires the optional Packmol executable')


def test_md_box_is_registered_for_the_md_role():
    tools = {entry.tool_name: entry for entry in get_tools_lst()}
    assert 'md_box' in tools
    entry = tools['md_box']
    assert 'md' in entry.registration.role_allowlist
    assert set(entry.input_json_schema()['required']) == {'components', 'output_dir'}


@pytest.mark.parametrize('box_options', [
    {},
    {'box_lengths_angstrom': [10, 10, 10], 'initial_density_g_cm3': 1.0},
    {'box_lengths_angstrom': [10, 10, 0]},
    {'initial_density_g_cm3': 0.0},
])
def test_md_box_requires_exactly_one_positive_box_specification(box_options):
    from cloudra.tools.Chemtool.md_box import MDBoxInput

    with pytest.raises(ValidationError):
        MDBoxInput(
            components=[{'structure_path': 'water.xyz', 'count': 4}],
            output_dir='box',
            **box_options,
        )


@pytest.mark.asyncio
async def test_md_box_packs_exact_component_counts_in_requested_periodic_cell(tmp_path, packmol):
    from cloudra.tools.Chemtool.md_box import MDBox, MDBoxInput

    (tmp_path / 'argon.xyz').write_text('1\nargon\nAr 0 0 0\n')
    (tmp_path / 'neon.xyz').write_text('1\nneon\nNe 0 0 0\n')
    tool = MDBox(subagent=SimpleNamespace(working_directory=str(tmp_path)))
    result = await tool.tool_call(MDBoxInput(
        components=[
            {'structure_path': 'argon.xyz', 'count': 4},
            {'structure_path': 'neon.xyz', 'count': 2},
        ],
        box_lengths_angstrom=[10.0, 11.0, 12.0],
        output_dir='box',
        seed=42,
    ), None)

    assert result.is_success, result
    coordinates_path = Path(result.coordinates_path)
    report_path = Path(result.report_path)
    assert coordinates_path.parent == report_path.parent == tmp_path / 'box'
    atoms = read(coordinates_path, format='extxyz')
    assert atoms.get_chemical_symbols().count('Ar') == 4
    assert atoms.get_chemical_symbols().count('Ne') == 2
    assert len(atoms) == 6
    assert atoms.pbc.all()
    assert atoms.cell.array == pytest.approx(np.diag([10.0, 11.0, 12.0]))

    pair_distances = atoms.get_all_distances(mic=True)[np.triu_indices(len(atoms), k=1)]
    assert min(pair_distances) >= 2.0 - 1e-5
    assert result.minimum_observed_distance_angstrom == pytest.approx(min(pair_distances), abs=1e-5)

    report = json.loads(report_path.read_text())
    assert report['seed'] == 42
    assert report['box_lengths_angstrom'] == [10.0, 11.0, 12.0]
    assert [component['count'] for component in report['components']] == [4, 2]
    assert [component['concentration_mol_l'] for component in report['components']] == pytest.approx(
        [5.03194, 2.51597], rel=1e-5,
    )
    assert result.initial_density_g_cm3 == pytest.approx(0.251787, rel=1e-4)


@pytest.mark.asyncio
async def test_md_box_reports_density_reference_and_keeps_packing_result(tmp_path, packmol, rdkit_chemistry):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.tools.Chemtool.md_box import MDBox, MDBoxInput

    water = Chem.AddHs(Chem.MolFromSmiles('O'))
    assert AllChem.EmbedMolecule(water, randomSeed=42) == 0
    source = tmp_path / 'water.sdf'
    with Chem.SDWriter(str(source)) as writer:
        writer.write(water)

    result = await MDBox().tool_call(MDBoxInput(
        components=[{'structure_path': str(source), 'count': 8}],
        initial_density_g_cm3=0.25,
        output_dir=str(tmp_path / 'dilute-water'),
        seed=42,
    ), None)

    assert result.is_success, result
    atoms = read(result.coordinates_path, format='extxyz')
    assert atoms.pbc.all()
    assert len(atoms) == 24
    assert atoms.cell.lengths() == pytest.approx([9.856, 9.856, 9.856], rel=1e-3)
    assert result.initial_density_g_cm3 == pytest.approx(0.25)
    assert result.density_reference['density_g_cm3'] == pytest.approx(1.0, rel=0.02)
    assert result.warnings

    oxygen = np.flatnonzero(atoms.numbers == 8)
    hydrogen = np.flatnonzero(atoms.numbers == 1)
    distances = atoms.get_all_distances(mic=True)
    assert len(oxygen) == 8
    assert len(hydrogen) == 16
    assert ((distances[np.ix_(oxygen, hydrogen)] < 1.1).sum(axis=1) == 2).all()
    assert result.minimum_observed_distance_angstrom >= 2.0 - 1e-5


@pytest.mark.asyncio
async def test_md_box_missing_structure_cannot_publish_a_success(tmp_path):
    from cloudra.tools.Chemtool.md_box import MDBox, MDBoxInput

    output_dir = tmp_path / 'box'
    with pytest.raises(RuntimeError, match='absent.xyz'):
        await MDBox().safe_call(MDBoxInput(
            components=[{'structure_path': str(tmp_path / 'absent.xyz'), 'count': 4}],
            box_lengths_angstrom=[10.0, 10.0, 10.0],
            output_dir=str(output_dir),
        ), None)
    assert not output_dir.exists()
