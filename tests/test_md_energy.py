"""Exercise the public MD energy tool against a small native GROMACS file."""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(scope='module')
def energy_file(tmp_path_factory):
    gmx = shutil.which('gmx') or shutil.which('gmx_mpi')
    if not gmx:
        pytest.skip('requires the optional GROMACS executable')

    directory = tmp_path_factory.mktemp('md-energy')
    (directory / 'argon.gro').write_text(
        'Argon test fixture\n4\n'
        '    1ARG     Ar    1   0.500   0.500   0.500\n'
        '    2ARG     Ar    2   0.900   0.500   0.500\n'
        '    3ARG     Ar    3   1.500   1.500   1.500\n'
        '    4ARG     Ar    4   1.900   1.500   1.500\n'
        '   2.50000   2.50000   2.50000\n'
    )
    (directory / 'argon.top').write_text(
        '[ defaults ]\n1 2 no 1 1\n'
        '[ atomtypes ]\nAr 39.948 0.0 A 0.34 0.997\n'
        '[ moleculetype ]\nARG 1\n'
        '[ atoms ]\n1 Ar 1 ARG Ar 1 0.0 39.948\n'
        '[ system ]\nArgon test fixture\n'
        '[ molecules ]\nARG 4\n'
    )
    (directory / 'argon.mdp').write_text(
        'integrator=md\nnsteps=5\ndt=0.002\nnstcalcenergy=1\nnstenergy=1\n'
        'cutoff-scheme=Verlet\nrlist=0.8\nrcoulomb=0.8\nrvdw=0.8\n'
        'gen_vel=yes\ngen_temp=120\ngen_seed=17\n'
    )
    for arguments in (
        ['grompp', '-f', 'argon.mdp', '-c', 'argon.gro', '-p', 'argon.top', '-o', 'argon.tpr'],
        ['mdrun', '-deffnm', 'argon', '-ntomp', '1'],
    ):
        completed = subprocess.run([gmx, *arguments], cwd=directory, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    return directory / 'argon.edr'


@pytest.fixture
def md_energy(energy_file, tmp_path):
    from cloudra.tools.Chemtool.md_energy import MDEnergy, MDEnergyInput

    shutil.copyfile(energy_file, tmp_path / 'argon.edr')
    tool = MDEnergy(subagent=SimpleNamespace(working_directory=str(tmp_path)))

    async def extract(terms, **interval):
        return await tool.tool_call(MDEnergyInput(
            energy_path='argon.edr', terms=terms, output_path='energy.xvg', **interval,
        ), None)

    return extract


@pytest.mark.asyncio
async def test_md_energy_aligns_statistics_with_native_xvg_columns(md_energy, tmp_path):
    result = await md_energy(['Temperature', 'Potential'], start_ps=0.002, end_ps=0.008)

    assert result.is_success, result.message
    assert Path(result.output_path) == tmp_path / 'energy.xvg'
    assert [row.term for row in result.statistics] == ['Potential', 'Temperature']
    assert [row.unit for row in result.statistics] == ['kJ/mol', 'K']
    potential, temperature = result.statistics
    assert temperature.average > 0 > potential.average
    assert all(row.error_estimate is None and row.rmsd >= 0 for row in result.statistics)
    assert result.frame_count == 4
    assert result.first_time_ps == pytest.approx(0.002)
    assert result.last_time_ps == pytest.approx(0.008)

    lines = Path(result.output_path).read_text().splitlines()
    legends = [line.rsplit('"', 2)[1] for line in lines if line.startswith('@ s') and 'legend' in line]
    assert legends == ['Potential', 'Temperature']
    points = [list(map(float, line.split())) for line in lines if line and not line.startswith(('#', '@'))]
    assert len(points) == result.frame_count
    assert all(len(point) == 3 and point[1] < 0 < point[2] for point in points)


@pytest.mark.asyncio
async def test_md_energy_rejects_partially_valid_selection_without_publishing(md_energy, tmp_path):
    result = await md_energy(['Potential', 'Not-A-Real-Term'])

    assert not result.is_success
    assert 'Not-A-Real-Term' in result.message
    assert not (tmp_path / 'energy.xvg').exists()


@pytest.mark.asyncio
async def test_md_energy_rejects_interval_without_frames_without_publishing(md_energy, tmp_path):
    result = await md_energy(['Potential'], start_ps=1.0, end_ps=2.0)

    assert not result.is_success
    assert not (tmp_path / 'energy.xvg').exists()


@pytest.mark.asyncio
async def test_md_energy_rejects_incomplete_edr_frame_without_publishing(md_energy, tmp_path):
    source = tmp_path / 'argon.edr'
    source.write_bytes(source.read_bytes()[:-1])

    result = await md_energy(['Potential'])

    assert not result.is_success
    assert 'Incomplete' in result.message
    assert not (tmp_path / 'energy.xvg').exists()
