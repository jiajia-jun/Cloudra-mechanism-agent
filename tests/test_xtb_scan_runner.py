"""Native xTB scan contract against the documented ammonia example."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

AMMONIA = """4
ammonia geometry from xTB PES scan documentation
N -0.00990404770994 -0.01698500657667 -0.00712107610609
H 0.00434306677482 0.00733732515324 1.00490910707310
H 0.94901246801925 0.00720047578638 -0.33083175918033
H -0.46827248708413 0.82547620563705 -0.33095427178668
"""

ETHANE = """8
ethane geometry from xTB PES scan documentation
C -0.01503441120750 0.04820403778911 -0.01075686629161
H -0.02618280545732 0.12324247717853 1.07751478989514
H 1.02025706611374 0.10521724412205 -0.34995019287160
H -0.56108089374185 0.89840506905011 -0.42160774836772
C -0.65104926960692 -1.26213120711759 -0.46045958867132
H -1.67328207424848 -1.33815676349645 -0.08720971228148
H -0.67543548798470 -1.32088660386766 -1.54947400918083
H -0.08161812386697 -2.11204925365809 -0.08140067223057
"""


@pytest.mark.usefixtures('rdkit_chemistry')
@pytest.mark.parametrize('electronic_character,multiplicity', [('closed_shell', 1), ('open_shell', 3)])
def test_standalone_native_scan_manifest_preserves_declared_electronic_character(
    tmp_path, electronic_character, multiplicity,
):
    from cloudra.runtime.chem_task import ChemTask
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    manifest = tmp_path / 'declared-state-scan.json'
    result = TsGuess()._xtb_scan_prepare(TsGuess_input_schema(basis_set='', mode='scan_prepare', engine='xtb',
        method='GFN2-xTB', input_text=AMMONIA, output_path=str(manifest), nproc=1,
        charge=0, multiplicity=multiplicity, electronic_character=electronic_character,
        force_constant=.5, scans=[{'atoms': [1, 2], 'scan_start': 1., 'scan_end': 1.1, 'scan_steps': 2}]))
    assert result.is_success
    task = ChemTask.model_validate_json(manifest.read_text())
    assert task.electronic_character == electronic_character
    assert task.multiplicity == multiplicity


@pytest.mark.usefixtures('rdkit_chemistry')
def test_standalone_native_scan_refuses_explicit_open_shell_singlet_before_manifest(tmp_path):
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    manifest = tmp_path / 'unsupported-singlet.json'
    with pytest.raises(ValueError) as error:
        TsGuess()._xtb_scan_prepare(TsGuess_input_schema(basis_set='', mode='scan_prepare', engine='xtb',
            method='GFN2-xTB', input_text=AMMONIA, output_path=str(manifest), nproc=1,
            charge=0, multiplicity=1, electronic_character='open_shell', force_constant=.5,
            scans=[{'atoms': [1, 2], 'scan_start': 1., 'scan_end': 1.1, 'scan_steps': 2}]))
    assert 'open-shell singlet' in str(error.value)
    assert not manifest.exists()


@pytest.mark.skipif(shutil.which('xtb') is None, reason='native xTB is unavailable')
@pytest.mark.asyncio
async def test_standalone_scan_prepares_typed_manifest_submits_only_scan_and_parses_native_result(tmp_path):
    from cloudra.persistence.database import ComputeDB
    from cloudra.runtime.chem_task import ChemTask, run_task
    from cloudra.tools.Chemtool.submit_compute_job import SubmitComputeJob, SubmitComputeJob_input_schema
    from cloudra.tools.Chemtool.ts_guess import TsGuess, TsGuess_input_schema

    manifest = tmp_path / 'scan-task.json'
    guess = TsGuess()
    prepared = guess._scan_prepare(TsGuess_input_schema(basis_set='', mode='scan_prepare', engine='xtb',
        method='GFN2-xTB', input_text=AMMONIA, output_path=str(manifest), nproc=1, charge=0, multiplicity=1,
        force_constant=0.5, scans=[{'atoms': [1, 2], 'scan_start': 1.0, 'scan_end': 1.1, 'scan_steps': 2}]))
    assert prepared.is_success and prepared.input_file_path == str(manifest)
    task = ChemTask.model_validate_json(manifest.read_text())
    assert task.task == 'xtb_scan' and task.scan.scans[0].atoms == [0, 1]
    tool = SubmitComputeJob()
    object.__setattr__(tool, 'subagent', SimpleNamespace(conversation_id='project', working_directory=str(tmp_path)))
    submission = await tool.tool_call(SubmitComputeJob_input_schema(input_file=str(manifest),
        job_type='chem_task', is_async=True), None)
    assert submission.is_success, submission.message
    with ComputeDB().connect() as con:
        row = con.execute('SELECT jobtype, path, req_cpus FROM compute_jobs WHERE id=?',
                          (submission.job_id,)).fetchone()
    assert tuple(row) == ('chem_task', str(manifest), 1)
    assert run_task(str(manifest)) == 0
    parsed = guess._scan_parse(TsGuess_input_schema(mode='scan_parse', engine='xtb', log_path=str(manifest)))
    assert parsed.is_success and parsed.scan_has_internal_peak is False
    assert 'electronic_hartree' in parsed.profile_table and 'No interior' in parsed.verdicts[0]


@pytest.mark.asyncio
async def test_public_chem_task_submission_rejects_internal_task_before_ledger(tmp_path):
    from cloudra.runtime.chem_task import ChemTask
    from cloudra.tools.Chemtool.submit_compute_job import SubmitComputeJob, SubmitComputeJob_input_schema

    manifest = tmp_path / 'internal.json'
    manifest.write_text(ChemTask(task='xtb_opt', reactant_xyz=AMMONIA, cpus=1).model_dump_json())
    tool = SubmitComputeJob()
    object.__setattr__(tool, 'subagent', SimpleNamespace(conversation_id='project', working_directory=str(tmp_path)))
    result = await tool.tool_call(SubmitComputeJob_input_schema(input_file=str(manifest),
        job_type='chem_task', is_async=True), None)
    assert not result.is_success and 'only xtb_scan' in result.message


@pytest.mark.skipif(shutil.which("xtb") is None, reason="native xTB is unavailable")
def test_native_xtb_scan_records_converged_points_and_unbiased_energy(tmp_path):
    from cloudra.runtime.chem_task import ChemTask, read_task_result, run_task

    task = ChemTask(task="xtb_scan", reactant_xyz=AMMONIA, cpus=1,
                    charge=0, multiplicity=1, scan={
        "kind": "scan", "calculation": {"engine": "xtb", "method": "GFN2-xTB", "basis_set": ""},
        "scans": [{"coord_type": "bond", "atoms": [0, 1],
                   "scan_start": 1.0, "scan_end": 1.1, "scan_steps": 2}],
        "force_constant": 0.5,
    })
    manifest = tmp_path / "scan-task.json"
    manifest.write_text(task.model_dump_json())
    assert run_task(str(manifest)) == 0
    data, ok = read_task_result(str(manifest))
    assert ok
    result = data["result"]
    assert result["normal_termination"] is True
    assert result["scan_status"] == "complete"
    assert len(result["points"]) == 2
    assert [point["targets"][0] for point in result["points"]] == [1.0, 1.1]
    assert all(point["geometry_converged"] is True and point["scc_converged"] is True
               for point in result["points"])
    assert all(point["energy_kind"] == "electronic" and point["energy_hartree"] is not None
               and point["bias_energy_hartree"] is not None for point in result["points"])
    assert result["points"][0]["actual_coordinates"][0] != 1.0
    assert "xtb version" in result["engine_version"]
    assert json.loads(manifest.read_text())["scan"]["force_constant"] == 0.5
    Path(result['scan_xyz_path']).write_text('4\ntruncated\n')
    with pytest.raises(ValueError, match='digest'):
        read_task_result(str(manifest))


@pytest.mark.skipif(shutil.which('xtb') is None, reason='native xTB is unavailable')
def test_native_scan_never_promotes_missing_frame_or_point_convergence(tmp_path):
    from cloudra.runtime.chem_task import ChemTask, read_task_result, run_task
    from cloudra.tools.core.xtb_scan_runner import parse_xtb_scan

    task = ChemTask(task='xtb_scan', reactant_xyz=AMMONIA, cpus=1,
        scan={'kind': 'scan', 'calculation': {'engine': 'xtb', 'method': 'GFN2-xTB', 'basis_set': ''},
              'scans': [{'atoms': [0, 1], 'scan_start': 1., 'scan_end': 1.1, 'scan_steps': 2}],
              'force_constant': .5})
    manifest = tmp_path / 'scan-task.json'
    manifest.write_text(task.model_dump_json())
    assert run_task(str(manifest)) == 0
    result = read_task_result(str(manifest))[0]['result']
    directory = Path(result['log_file']).parent
    trajectory = Path(result['scan_xyz_path'])
    original = trajectory.read_text()
    trajectory.write_text('\n'.join(original.splitlines()[:6]) + '\n')
    incomplete = parse_xtb_scan(task, directory, 0)
    assert incomplete['scan_status'] == 'incomplete' and not incomplete['usable_as_guess']
    trajectory.write_text(original)
    log = Path(result['log_file'])
    prefix, marker, scan_text = log.read_text().partition('RELAXED SCAN')
    assert marker
    log.write_text(prefix + marker + scan_text.replace('GEOMETRY OPTIMIZATION CONVERGED',
                                                       'GEOMETRY OPTIMIZATION NOT CONVERGED', 1))
    unconverged = parse_xtb_scan(task, directory, 0)
    assert unconverged['scan_status'] == 'incomplete'
    assert any(not point['geometry_converged'] for point in unconverged['points'])


@pytest.mark.skipif(shutil.which("xtb") is None, reason="native xTB is unavailable")
@pytest.mark.parametrize("mode,expected", [("concerted", 2), ("sequential", 4)])
def test_native_two_coordinate_modes_keep_segment_targets(tmp_path, mode, expected):
    from cloudra.runtime.chem_task import ChemTask, read_task_result, run_task

    task = ChemTask(task="xtb_scan", reactant_xyz=AMMONIA, cpus=1,
                    charge=0, multiplicity=1, scan={
        "kind": "scan", "calculation": {"engine": "xtb", "method": "GFN2-xTB", "basis_set": ""},
        "scans": [
            {"coord_type": "bond", "atoms": [0, 1], "scan_start": 1.0,
             "scan_end": 1.1, "scan_steps": 2},
            {"coord_type": "angle", "atoms": [1, 0, 2], "scan_start": 108.0,
             "scan_end": 105.0, "scan_steps": 2},
        ],
        "mode": mode, "force_constant": 0.5,
    })
    manifest = tmp_path / "scan-task.json"
    manifest.write_text(task.model_dump_json())
    assert run_task(str(manifest)) == 0
    data, ok = read_task_result(str(manifest))
    assert ok
    result = data["result"]
    assert result["scan_status"] == "complete"
    assert len(result["points"]) == expected
    assert result["points"][0]["targets"][0] == 1.0
    assert result["points"][-1]["targets"][1] == 105.0
    if mode == "sequential":
        assert [point["segment"] for point in result["points"]] == [1, 1, 2, 2]
        assert all(point["targets"][0] == 1.1 for point in result["points"][2:])


@pytest.mark.skipif(shutil.which("xtb") is None, reason="native xTB is unavailable")
def test_native_dihedral_scan_can_hand_off_only_an_internal_peak(tmp_path):
    from cloudra.runtime.chem_task import ChemTask, read_task_result, run_task

    task = ChemTask(task='xtb_scan', reactant_xyz=ETHANE, cpus=1, charge=0, multiplicity=1,
        scan={'kind': 'scan', 'calculation': {'engine': 'xtb', 'method': 'GFN2-xTB', 'basis_set': ''},
              'scans': [{'coord_type': 'dihedral', 'atoms': [7, 4, 0, 3],
                         'scan_start': 60.0, 'scan_end': 180.0, 'scan_steps': 3}],
              'force_constant': 0.05})
    manifest = tmp_path / 'dihedral-task.json'
    manifest.write_text(task.model_dump_json())
    assert run_task(str(manifest)) == 0
    result = read_task_result(str(manifest))[0]['result']
    assert result['scan_status'] == 'complete'
    assert result['usable_as_guess'] is True
    assert result['candidates'][0]['point_index'] == 2
    assert result['candidate_path'] == result['points'][1]['frame_path']
    assert [round(point['actual_coordinates'][0]) for point in result['points']] == [60, 120, 180]
