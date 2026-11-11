"""Compare native GROMACS observables with a known rigid translation."""

import math
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(scope='module')
def md_inputs(tmp_path_factory):
    gmx = shutil.which('gmx') or shutil.which('gmx_mpi')
    if gmx is None:
        pytest.skip('requires the optional GROMACS executable')
    path = tmp_path_factory.mktemp('md-observables')

    # Two residues of three atoms. The first pair stays 0.4 nm apart while every atom moves along x.
    coordinates = (
        (1.0, 1.0, 1.0), (1.4, 1.0, 1.0), (1.0, 1.4, 1.0),
        (1.0, 1.0, 1.4), (1.4, 1.0, 1.4), (1.0, 1.4, 1.4),
    )

    def frame(time, moving_atoms=range(1, 7)):
        atoms = ''.join(
            f'{(index - 1) // 3 + 1:5d}{"TST":<5}{"O":>5}{index:5d}'
            f'{x + (0.1 * time if index in moving_atoms else 0):8.3f}{y:8.3f}{z:8.3f}\n'
            for index, (x, y, z) in enumerate(coordinates, 1)
        )
        return f'Frame t= {time}\n    6\n{atoms}   4.00000   4.00000   4.00000\n'

    def run(args, selection=None):
        result = subprocess.run([gmx, *args], input=selection, text=True, capture_output=True, cwd=path)
        assert result.returncode == 0, result.stderr

    (path / 'reference.gro').write_text(frame(0))
    (path / 'trajectory.gro').write_text(''.join(frame(time) for time in range(8)))
    (path / 'single-moving-atom.gro').write_text(''.join(frame(time, moving_atoms=(1,)) for time in range(8)))
    (path / 'probe.mdp').write_text('integrator = steep\nnsteps = 1\n')
    (path / 'system.top').write_text(
        '[ defaults ]\n1 2 no 1.0 1.0\n[ atomtypes ]\nO 8 15.999 0.0 A 0.30 0.65\n'
        '[ moleculetype ]\nTest 1\n[ atoms ]\n'
        + ''.join(f'{index} O {(index - 1) // 3 + 1} TST O {index} 0.0 15.999\n' for index in range(1, 7))
        + '[ system ]\nTest\n[ molecules ]\nTest 1\n'
    )
    (path / 'groups.ndx').write_text('[ FitAtoms ]\n1 2 3\n[ Tracked ]\n1 2 3 4 5 6\n[ PairLeft ]\n1\n[ PairRight ]\n2\n')
    run(['grompp', '-f', 'probe.mdp', '-p', 'system.top', '-c', 'reference.gro', '-o', 'system.tpr'])
    run(['trjconv', '-f', 'trajectory.gro', '-o', 'trajectory.xtc'], 'System\n')
    run(['trjconv', '-f', 'single-moving-atom.gro', '-o', 'single-moving-atom.xtc'], 'System\n')
    run(['trjconv', '-f', 'trajectory.xtc', '-n', 'groups.ndx', '-o', 'subset.xtc'], 'FitAtoms\n')
    return {
        'trajectory_path': str(path / 'trajectory.xtc'),
        'topology_path': str(path / 'system.tpr'),
        'index_path': str(path / 'groups.ndx'),
    }


def _series(result, path, units):
    assert result.is_success, result.message
    assert result.output_path == str(path)
    assert (result.x_unit, result.y_unit) == units
    rows = [tuple(map(float, line.split())) for line in path.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith(('@', '#'))]
    assert result.point_count == len(rows)
    assert all(math.isfinite(value) for row in rows for value in row)
    return tuple(zip(*rows, strict=True))


@pytest.mark.asyncio
async def test_md_rmsd_uses_requested_fit_and_time_window(md_inputs, tmp_path):
    from cloudra.tools.Chemtool.md_structure import MDRMSD, MDRMSDInput

    tool = MDRMSD(subagent=SimpleNamespace(working_directory=str(tmp_path)))
    for fit_group, expected in [('FitAtoms', [0.0] * 4), (None, [0.2, 0.3, 0.4, 0.5])]:
        name = f'{fit_group or "unfitted"}.xvg'
        result = await tool.tool_call(MDRMSDInput(
            **md_inputs, group='Tracked', fit_group=fit_group, start_ps=2, end_ps=5, output_path=name,
        ))
        times, deviations = _series(result, tmp_path / name, ('ps', 'nm'))
        assert times == (2, 3, 4, 5)
        assert deviations == pytest.approx(expected, abs=1e-5)


@pytest.mark.asyncio
async def test_md_rmsd_uses_default_system_group_without_index(md_inputs, tmp_path):
    from cloudra.tools.Chemtool.md_structure import MDRMSD, MDRMSDInput

    output = tmp_path / 'default-group.xvg'
    result = await MDRMSD().tool_call(MDRMSDInput(
        trajectory_path=md_inputs['trajectory_path'], topology_path=md_inputs['topology_path'],
        group='System', fit_group=None, output_path=str(output),
    ))
    times, deviations = _series(result, output, ('ps', 'nm'))
    assert times == tuple(range(8))
    assert deviations[-1] == pytest.approx(0.7, abs=1e-5)


@pytest.mark.asyncio
@pytest.mark.parametrize(('per_residue', 'count'), [(False, 6), (True, 2)])
async def test_md_rmsf_uses_requested_atom_or_residue_resolution(md_inputs, tmp_path, per_residue, count):
    from cloudra.tools.Chemtool.md_structure import MDRMSF, MDRMSFInput

    output = tmp_path / 'rmsf.xvg'
    result = await MDRMSF().tool_call(MDRMSFInput(
        **md_inputs, group='Tracked', fit=False, per_residue=per_residue, output_path=str(output),
    ))
    indices, fluctuations = _series(result, output, ('index', 'nm'))
    assert indices == tuple(range(1, count + 1))
    assert fluctuations == pytest.approx([0.2291] * count, abs=1e-4)


@pytest.mark.asyncio
async def test_md_rdf_locates_the_known_pair_distance(md_inputs, tmp_path):
    from cloudra.tools.Chemtool.md_transport import MDRDF, MDRDFInput

    output = tmp_path / 'rdf.xvg'
    result = await MDRDF().tool_call(MDRDFInput(
        **md_inputs, reference_group='PairLeft', group='PairRight', bin_width_nm=0.05,
        max_distance_nm=0.8, output_path=str(output),
    ))
    radii, distribution = _series(result, output, ('nm', '1'))
    occupied_radii = [radius for radius, value in zip(radii, distribution, strict=True) if value > 0]
    assert occupied_radii == pytest.approx([0.4], abs=0.025)
    assert radii[1] - radii[0] == pytest.approx(0.05)
    assert max(radii) <= 0.8


@pytest.mark.asyncio
async def test_md_msd_measures_the_known_lag_displacements(md_inputs, tmp_path):
    from cloudra.tools.Chemtool.md_transport import MDMSD, MDMSDInput

    output = tmp_path / 'msd.xvg'
    result = await MDMSD().tool_call(MDMSDInput(
        **md_inputs, group='Tracked', origin_spacing_ps=1, max_lag_ps=4, output_path=str(output),
    ))
    lags, displacements = _series(result, output, ('ps', 'nm^2'))
    assert lags == (0, 1, 2, 3, 4)
    assert displacements == pytest.approx([0.0, 0.01, 0.04, 0.09, 0.16], abs=1e-5)


@pytest.mark.asyncio
async def test_md_msd_uses_all_atoms_of_the_selected_molecule_for_com(md_inputs, tmp_path):
    from cloudra.tools.Chemtool.md_transport import MDMSD, MDMSDInput

    output = tmp_path / 'msd-com.xvg'
    trajectory = Path(md_inputs['trajectory_path']).with_name('single-moving-atom.xtc')
    inputs = dict(md_inputs, trajectory_path=str(trajectory))
    result = await MDMSD().tool_call(MDMSDInput(
        **inputs, group='PairLeft', molecular_com=True, origin_spacing_ps=1, max_lag_ps=4,
        output_path=str(output),
    ))
    lags, displacements = _series(result, output, ('ps', 'nm^2'))
    assert lags == (0, 1, 2, 3, 4)
    assert displacements == pytest.approx([(0.1 * lag / 6) ** 2 for lag in range(5)], abs=1e-7)


@pytest.mark.asyncio
async def test_md_rmsd_requires_an_exact_group_and_leaves_no_output_on_failure(md_inputs, tmp_path):
    from cloudra.tools.Chemtool.md_structure import MDRMSD, MDRMSDInput

    output = tmp_path / 'unknown-group.xvg'
    result = await MDRMSD().tool_call(MDRMSDInput(
        **md_inputs, group='Trac', fit_group=None, output_path=str(output),
    ))
    assert not result.is_success
    assert 'Trac' in result.message
    assert not result.output_path
    assert not output.exists()


@pytest.mark.asyncio
async def test_md_rdf_rejects_a_trajectory_with_different_atom_count(md_inputs, tmp_path):
    from cloudra.tools.Chemtool.md_transport import MDRDF, MDRDFInput

    output = tmp_path / 'mismatched-atoms.xvg'
    subset = Path(md_inputs['trajectory_path']).with_name('subset.xtc')
    inputs = dict(md_inputs, trajectory_path=str(subset))
    result = await MDRDF().tool_call(MDRDFInput(
        **inputs, reference_group='PairLeft', group='PairRight', output_path=str(output),
    ))
    assert not result.is_success
    assert '3 atoms' in result.message and '6 atoms' in result.message
    assert not result.output_path
    assert not output.exists()
