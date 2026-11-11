"""Exercise the registered periodic geometry tool on real structure files."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from ase import Atoms
from ase.io import read, write
from pydantic import ValidationError

from cloudra.tools import get_tools_lst


@pytest.fixture
def crystal(tmp_path):
    atoms = Atoms(
        'NaCl', scaled_positions=[(0, 0, 0), (0.5, 0.5, 0.4)],
        cell=[(4, 0, 0), (1, 5, 0), (1, 0, 6)], pbc=True,
    )
    write(tmp_path / 'bulk.extxyz', atoms, format='extxyz')
    return atoms


def model_tool(tmp_path):
    entry = next((entry for entry in get_tools_lst() if entry.tool_name == 'periodic_model'), None)
    assert entry is not None, 'periodic_model must be registered'
    assert {'coordinator', 'dft'} <= entry.registration.role_allowlist
    return entry.instantiate(subagent=SimpleNamespace(working_directory=str(tmp_path)))


async def run_model(tmp_path, operation, *, source='bulk.extxyz', output=None):
    tool = model_tool(tmp_path)
    return await tool.tool_call(tool.input_schema(input_path=source, operation=operation, output_path=output))


@pytest.mark.asyncio
@pytest.mark.parametrize(('options', 'matrix'), [
    ({'repeat': [2, 1, 3]}, [[2, 0, 0], [0, 1, 0], [0, 0, 3]]),
    ({'matrix': [[2, 1, 0], [0, 1, 0], [0, 0, 1]]}, [[2, 1, 0], [0, 1, 0], [0, 0, 1]]),
    ({'min_lengths_angstrom': [7, None, 13]}, [[2, 0, 0], [0, 1, 0], [0, 0, 3]]),
])
async def test_supercell_sizes_in_input_basis(tmp_path, crystal, options, matrix):
    result = await run_model(tmp_path, {'type': 'supercell', **options}, output='expanded.extxyz')

    expanded = read(result.output_path, format='extxyz')
    assert len(expanded) == round(2 * abs(np.linalg.det(matrix)))
    np.testing.assert_allclose(expanded.cell, np.array(matrix) @ crystal.cell)
    assert result.summary.atom_count == len(expanded)
    assert result.summary.shortest_periodic_translation_angstrom is not None


@pytest.mark.asyncio
async def test_slab_requires_selection_of_distinct_geometric_cuts(tmp_path, crystal):
    operation = {'type': 'slab', 'miller': [0, 0, 1], 'layers': 3, 'vacuum_angstrom': 12}
    preview = await run_model(tmp_path, operation, output='slab.extxyz')
    assert preview.output_path is None
    assert not (tmp_path / 'slab.extxyz').exists()
    assert [candidate.bottom for candidate in preview.terminations] == [{'Na': 1}, {'Cl': 1}]
    assert [candidate.top for candidate in preview.terminations] == [{'Na': 1}, {'Cl': 1}]

    result = await run_model(tmp_path, {**operation, 'termination': 1}, output='slab.extxyz')
    slab = read(result.output_path, format='extxyz')
    np.testing.assert_allclose(slab.cell[:2], crystal.cell[:2])
    assert slab.pbc.tolist() == [True, True, False]
    assert slab.get_chemical_formula() == 'ClNa2'
    assert result.summary.thickness_angstrom == pytest.approx(6)
    assert result.summary.vacuum_angstrom == pytest.approx(12)
    np.testing.assert_allclose(np.sort(slab.positions[:, 2]), [6, 8.4, 12])
    sodium_x = slab.positions[slab.numbers == 11, 0]
    assert abs(sodium_x[1] - sodium_x[0]) == pytest.approx(1)

    expanded = await run_model(
        tmp_path, {'type': 'supercell', 'repeat': [2, 3, 1]}, source='slab.extxyz', output='wide.extxyz',
    )
    assert expanded.summary.atom_count == 18
    assert expanded.summary.vacuum_angstrom == pytest.approx(12)
    invalid = await run_model(
        tmp_path, {'type': 'supercell', 'repeat': [1, 1, 2]}, source='slab.extxyz', output='bad.extxyz',
    )
    assert not invalid.is_success and 'nonperiodic' in invalid.message


@pytest.mark.asyncio
async def test_skew_high_index_slab_has_correct_plane_spacing_and_area(tmp_path, crystal):
    crystal = crystal[:1]
    write(tmp_path / 'bulk.extxyz', crystal, format='extxyz')
    result = await run_model(
        tmp_path, {'type': 'slab', 'miller': [2, -1, 3], 'layers': 4, 'vacuum_angstrom': 10},
        output='slab.extxyz',
    )
    slab = read(result.output_path, format='extxyz')
    spacing = 1 / np.linalg.norm(np.linalg.solve(crystal.cell, [2, -1, 3]))
    np.testing.assert_allclose(np.diff(np.sort(slab.positions[:, 2])), spacing)
    assert np.linalg.norm(np.cross(*slab.cell[:2])) == pytest.approx(crystal.cell.volume / spacing)
    assert slab.cell.lengths()[2] == pytest.approx(3 * spacing + 10)


@pytest.mark.asyncio
async def test_edit_sites_uses_input_file_atom_numbers_for_a_batch(tmp_path, crystal):
    path = tmp_path / 'expanded.extxyz'
    write(path, crystal.repeat((2, 1, 1)), format='extxyz')
    inspected = await run_model(tmp_path, {'type': 'inspect', 'element': 'Cl'}, source=path.name)
    assert [site.atom_index for site in inspected.sites] == [2, 4]

    result = await run_model(tmp_path, {
        'type': 'edit_sites',
        'edits': [
            {'type': 'remove', 'atom_index': 2},
            {'type': 'replace', 'atom_index': 4, 'element': 'Br'},
            {'type': 'add', 'element': 'Li', 'fractional': [1.125, 0.25, 0.25]},
        ],
    }, source=path.name, output='defect.extxyz')

    defect = read(result.output_path, format='extxyz')
    assert defect.get_chemical_symbols() == ['Na', 'Na', 'Br', 'Li']
    np.testing.assert_allclose(defect.get_scaled_positions()[-1], [0.125, 0.25, 0.25])
    assert read(path, format='extxyz').get_chemical_symbols() == ['Na', 'Cl', 'Na', 'Cl']
    assert result.summary.composition == {'Br': 1, 'Li': 1, 'Na': 2}


@pytest.mark.asyncio
async def test_invalid_edit_leaves_no_partial_output(tmp_path, crystal):
    result = await run_model(tmp_path, {
        'type': 'edit_sites',
        'edits': [{'type': 'remove', 'atom_index': 1}, {'type': 'remove', 'atom_index': 3}],
    }, output='defect.extxyz')
    assert not result.is_success and 'Atom 3' in result.message
    assert not (tmp_path / 'defect.extxyz').exists()


@pytest.mark.asyncio
async def test_periodic_model_rejects_in_place_output(tmp_path, crystal):
    source = tmp_path / 'bulk.extxyz'
    original = source.read_bytes()
    result = await run_model(tmp_path, {'type': 'supercell', 'repeat': [2, 1, 1]}, output=source.name)
    assert not result.is_success and 'output' in result.message
    assert source.read_bytes() == original


def test_supercell_options_are_mutually_exclusive(tmp_path):
    tool = model_tool(tmp_path)
    with pytest.raises(ValidationError, match='exactly one'):
        tool.input_schema(
            input_path='bulk.extxyz', output_path='super.extxyz',
            operation={'type': 'supercell', 'repeat': [2, 2, 2], 'min_lengths_angstrom': [10, None, None]},
        )


@pytest.mark.asyncio
async def test_cif_disorder_is_not_silently_ordered(tmp_path):
    (tmp_path / 'bulk.cif').write_text(
        'data_disordered\n_cell_length_a 4\n_cell_length_b 4\n_cell_length_c 4\n'
        '_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n'
        '_space_group_name_H-M_alt "P 1"\n'
        'loop_\n_atom_site_type_symbol\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n'
        '_atom_site_occupancy\nNa 0 0 0 0.5\nCl 0 0 0 0.5\n',
        encoding='utf-8',
    )
    result = await run_model(tmp_path, {'type': 'inspect'}, source='bulk.cif')
    assert not result.is_success and 'occupancy' in result.message


@pytest.mark.asyncio
async def test_slab_can_be_consumed_as_poscar_with_boundary_warning(tmp_path, crystal):
    result = await run_model(
        tmp_path, {'type': 'slab', 'miller': [0, 0, 1], 'layers': 3, 'vacuum_angstrom': 12, 'termination': 1},
        output='vasp/POSCAR',
    )
    assert Path(result.output_path).is_file()
    assert any('periodic' in warning.lower() for warning in result.warnings)
    atoms = read(result.output_path, format='vasp')
    assert atoms.pbc.all()
    assert atoms.cell.lengths()[2] == pytest.approx(18)


@pytest.mark.asyncio
async def test_dft_agent_builds_and_converts_periodic_geometry(tmp_path, crystal):
    from cloudra.runtime_v2.adapters import LegacyToolExecutor
    from cloudra.runtime_v2.commands import CommandBus
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.runtime_v2.invocation import InvocationService
    from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall
    from cloudra.runtime_v2.policies.permission import PermissionStage
    from cloudra.runtime_v2.schemas import Command, InvocationProtocol
    from cloudra.runtime_v2.tool_catalog import tool_declarations, wire_tool_schemas

    core = RuntimeCore(strict_events=True)
    bus = CommandBus(core)
    await bus.execute(Command(type='project.create', payload={'name': 'Periodic', 'workspace_dir': str(tmp_path)}))
    project = next(iter(core.projects.values()))
    spawned = await bus.execute(Command(
        type='agent.spawn', target={'project_id': project.id}, payload={'role_id': 'dft'},
    ))
    agent = spawned.data
    agent.settings.invocation_protocol = InvocationProtocol.TRADITIONAL
    assert 'periodic_model' in {item['function']['name'] for item in wire_tool_schemas(agent, ['*'])}
    assert 'periodic_model(' in tool_declarations(['*'], role_id='dft')
    service = InvocationService(
        event_writer=core.event_writer, stages=[PermissionStage()], tools=LegacyToolExecutor(core),
    )
    context = PipelineContext(
        agent=agent, run_id='periodic', settings_snapshot=agent.settings, capabilities=agent.capabilities,
        inbox_messages=[], emit=lambda *_: None,
    )
    outcome = await service.invoke(context, ToolCall(id='slab', name='periodic_model', arguments={
        'input_path': 'bulk.extxyz',
        'operation': {'type': 'slab', 'miller': [0, 0, 1], 'layers': 4, 'vacuum_angstrom': 12, 'termination': 1},
        'output_path': 'slab.extxyz',
    }))
    assert outcome.result.is_success, outcome.result.summary
    assert outcome.result.data['summary']['pbc'] == [True, True, False]
    outcome = await service.invoke(context, ToolCall(id='convert', name='format_converter', arguments={
        'input_path': 'slab.extxyz', 'input_format': 'extxyz',
        'output_path': 'slab.inc', 'output_format': 'cp2k-geometry',
    }))
    assert outcome.result.is_success, outcome.result.summary
    assert 'PERIODIC XY' in (tmp_path / 'slab.inc').read_text()


@pytest.mark.asyncio
async def test_same_composition_terminations_report_different_geometry(tmp_path):
    atoms = Atoms(
        'Si3', scaled_positions=[(0, 0, 0.1), (0, 0, 0.2), (0, 0, 0.8)],
        cell=[4, 4, 4], pbc=True,
    )
    write(tmp_path / 'bulk.extxyz', atoms, format='extxyz')
    preview = await run_model(tmp_path, {'type': 'slab', 'miller': [0, 0, 1], 'layers': 2, 'vacuum_angstrom': 10})
    assert [cut.bottom for cut in preview.terminations] == [{'Si': 1}] * 3
    assert [cut.cleavage_gap_angstrom for cut in preview.terminations] == pytest.approx([1.2, 0.4, 2.4])
    assert [cut.thickness_angstrom for cut in preview.terminations] == pytest.approx([0.4, 2.4, 1.2])
