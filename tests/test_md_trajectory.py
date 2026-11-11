import shutil
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def gromacs():
    gmx = shutil.which('gmx')
    if gmx is None:
        pytest.skip('requires the optional GROMACS executable')
    return gmx


@pytest.fixture
def trajectory_factory(tmp_path, gromacs):
    def make_trajectory(times, suffix='xtc'):
        source = tmp_path / 'frames.gro'
        _write_gro(source, times, atom_count=12)
        trajectory = tmp_path / f'frames.{suffix}'
        result = subprocess.run(
            [gromacs, 'trjconv', '-f', source.name, '-o', trajectory.name],
            input='System\n', text=True, capture_output=True, cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        return trajectory

    return make_trajectory


def _write_gro(path, times, atom_count):
    atoms = ''.join(
        f'{1:5d}{"SOL":<5}{"OW":>5}{index:5d}{index * 0.1:8.3f}{0.0:8.3f}{0.0:8.3f}\n'
        for index in range(1, atom_count + 1)
    )
    path.write_text(''.join(
        f'frame t= {time}\n{atom_count:5d}\n{atoms}   3.00000   3.00000   3.00000\n' for time in times
    ))


@pytest.fixture
def topology_factory(tmp_path, gromacs):
    def make_topology(atom_count):
        _write_gro(tmp_path / 'topology.gro', (0,), atom_count)
        (tmp_path / 'probe.mdp').write_text('integrator = steep\nnsteps = 1\n')
        (tmp_path / 'system.top').write_text(
            '[ defaults ]\n1 2 no 1.0 1.0\n[ atomtypes ]\nO 8 15.999 0.0 A 0.30 0.65\n'
            '[ moleculetype ]\nTest 1\n[ atoms ]\n'
            + ''.join(f'{index} O 1 SOL OW 1 0.0 15.999\n' for index in range(1, atom_count + 1))
            + '[ bonds ]\n1 2 1 0.2 1000\n[ system ]\nTest\n[ molecules ]\nTest 1\n'
        )
        topology = tmp_path / 'probe.tpr'
        run = subprocess.run(
            [gromacs, 'grompp', '-f', 'probe.mdp', '-p', 'system.top', '-c', 'topology.gro', '-o', topology.name],
            text=True, capture_output=True, cwd=tmp_path,
        )
        assert run.returncode == 0, run.stderr
        return topology

    return make_topology


@pytest.mark.asyncio
@pytest.mark.parametrize(('times', 'interval'), [
    ((1.5, 2.0, 2.5), 0.5),
    ((1.5, 2.0, 2.125, 2.5), None),
    ((1.5,), None),
    (tuple(1.5 + index * 0.25 for index in range(22)), 0.25),
])
async def test_md_trajectory_reads_native_coordinate_frame_metadata(tmp_path, trajectory_factory, times, interval):
    from cloudra.tools.Chemtool.md_trajectory import MDTrajectory, MDTrajectoryInput

    trajectory = trajectory_factory(times)
    tool = MDTrajectory(subagent=SimpleNamespace(working_directory=str(tmp_path)))
    result = await tool.tool_call(MDTrajectoryInput(trajectory_path=trajectory.name))

    assert result.is_success, result
    assert result.atom_count == 12
    assert result.frame_count == len(times)
    assert result.first_time_ps == times[0]
    assert result.last_time_ps == times[-1]
    assert result.frame_interval_ps == interval


@pytest.mark.asyncio
@pytest.mark.parametrize(('suffix', 'warning'), [('xtc', 'Incomplete frame'), ('trr', 'Incomplete header')])
async def test_md_trajectory_reports_native_truncation_even_with_complete_earlier_frames(trajectory_factory, suffix, warning):
    from cloudra.tools.Chemtool.md_trajectory import MDTrajectory, MDTrajectoryInput

    trajectory = trajectory_factory((1.5, 2.0, 2.5), suffix=suffix)
    data = trajectory.read_bytes()
    # The three synthetic TRR frames have equal sizes. Retain only the start of the third header.
    trajectory.write_bytes(data[:len(data) // 3 * 2 + 12] if suffix == 'trr' else data[:-10])

    result = await MDTrajectory().tool_call(MDTrajectoryInput(trajectory_path=str(trajectory)))

    assert not result.is_success
    assert result.atom_count == 12
    assert result.frame_count == 2
    assert result.first_time_ps == 1.5
    assert result.last_time_ps == 2.0
    assert any(warning in line for line in result.diagnostics)


@pytest.mark.asyncio
async def test_md_trajectory_reports_native_bond_diagnostics(trajectory_factory, topology_factory):
    from cloudra.tools.Chemtool.md_trajectory import MDTrajectory, MDTrajectoryInput

    trajectory = trajectory_factory((1.5, 2.0))
    topology = topology_factory(12)

    result = await MDTrajectory().tool_call(MDTrajectoryInput(
        trajectory_path=str(trajectory), topology_path=str(topology),
    ))

    assert result.frame_count == 2
    assert sum('Distance between atoms 1 and 2' in line for line in result.diagnostics) == 2


@pytest.mark.asyncio
async def test_md_trajectory_rejects_topology_with_different_atom_count(trajectory_factory, topology_factory):
    from cloudra.tools.Chemtool.md_trajectory import MDTrajectory, MDTrajectoryInput

    trajectory = trajectory_factory((1.5,))
    topology = topology_factory(4)

    result = await MDTrajectory().tool_call(MDTrajectoryInput(
        trajectory_path=str(trajectory), topology_path=str(topology),
    ))

    assert not result.is_success
    assert result.atom_count == 12
    assert '4 atoms' in result.message
