from pathlib import Path

import pytest


def test_internal_task_rejects_arbitrary_commands_and_parameters():
    from cloudra.runtime.chem_task import ChemTask

    with pytest.raises(ValueError):
        ChemTask(task="shell", command=["echo", "anything"], cpus=1)
    with pytest.raises(ValueError):
        ChemTask(task="xtb_path", reactant_xyz="a", product_xyz="b", cpus=1, extra_args=["--anything"])


@pytest.mark.parametrize("declared,effective", [(None, 100), (7, 7)])
def test_helper_path_preserves_runner_default_and_has_no_timeout(tmp_path, monkeypatch, declared, effective):
    from cloudra.runtime import chem_task
    from cloudra.tools.core.xtb_path_runner import XtbPathResult

    observed = []

    def fake(request):
        observed.append(request)
        return XtbPathResult(run_dir=str(tmp_path), returncode=1, termination_reason="failed")

    monkeypatch.setattr("cloudra.tools.core.xtb_path_runner.run_xtb_path", fake)
    manifest = tmp_path / "task.json"
    manifest.write_text(
        chem_task.ChemTask(
            task="xtb_path", reactant_xyz="1\nfake\nH 0 0 0\n", product_xyz="1\nfake\nH 1 0 0\n", cpus=2, refinement_runs=declared
        ).model_dump_json()
    )
    assert chem_task.run_task(str(manifest)) == 1
    assert observed[0].timeout is None
    assert observed[0].refinement_runs == effective
    data, success = chem_task.read_task_result(str(manifest))
    assert success is False and data["result"]["returncode"] == 1
    assert data["result"]["termination_reason"] == "failed"
    manifest.write_text(manifest.read_text().replace('"cpus":2', '"cpus":1'))
    with pytest.raises(ValueError, match="digest"):
        chem_task.read_task_result(str(manifest))


def test_engine_gate_reads_same_typed_helper_result(tmp_path):
    import json

    from cloudra.infra.slurm import _engine_success_from_log
    from cloudra.runtime.chem_task import ChemTask, result_path
    from cloudra.tools.core.conformer_catalog import content_digest

    manifest = tmp_path / "task.json"
    task = ChemTask(task="xtb_path", reactant_xyz="x", product_xyz="y", cpus=1)
    manifest.write_text(task.model_dump_json())
    Path(result_path(str(manifest))).write_text(
        json.dumps(
            {
                "manifest_digest": content_digest(task.model_dump()),
                "result": {"returncode": 0, "termination_reason": "path_not_converged"},
                "process_exit_code": 0,
            }
        )
    )
    assert _engine_success_from_log("chem_task", str(manifest)) is True


@pytest.mark.asyncio
async def test_guard_uses_typed_result_even_without_native_log(tmp_path):
    import json

    from cloudra.infra.compute_utils import get_log_path
    from cloudra.runtime.chem_task import ChemTask, result_path
    from cloudra.runtime.monitor import _parse_log
    from cloudra.tools.core.conformer_catalog import content_digest

    manifest = tmp_path / "task.json"
    task = ChemTask(task="xtb_path", reactant_xyz="x", product_xyz="y", cpus=1)
    manifest.write_text(task.model_dump_json())
    Path(result_path(str(manifest))).write_text(
        json.dumps(
            {"manifest_digest": content_digest(task.model_dump()), "result": {"returncode": 1}, "process_exit_code": 1}
        )
    )
    assert get_log_path(str(manifest), "chem_task") == str(manifest)
    data, success = await _parse_log(manifest, 1, job_type="chem_task")
    assert success is False and data["process_exit_code"] == 1


def test_native_optimizer_records_nonconvergence_without_fallback_or_limits(tmp_path, monkeypatch):
    import subprocess

    from cloudra.runtime import chem_task

    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        kwargs["stdout"].write("FAILED TO CONVERGE GEOMETRY OPTIMIZATION\n")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", run)
    path = tmp_path / "opt.json"
    path.write_text(
        chem_task.ChemTask(task="xtb_opt", reactant_xyz="1\nsynthetic\nH 0 0 0\n", cpus=1).model_dump_json()
    )
    assert chem_task.run_task(str(path)) == 0
    data, _ = chem_task.read_task_result(str(path))
    assert data["result"]["optimization_converged"] is False
    assert "--opt" in calls[0][0]
    assert "timeout" not in calls[0][1]
    assert "--iterations" not in calls[0][0]
    assert len(calls) == 1


def test_sampling_task_returns_all_raw_choices_without_optimizer(tmp_path, monkeypatch):
    pytest.importorskip("rdkit", reason="requires RDKit (chem extra)")
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from cloudra.runtime.chem_task import ChemTask, read_task_result, run_task
    from cloudra.tools.core.conformer_selection import SamplingRequest

    mol = Chem.AddHs(Chem.MolFromSmiles("CCCC"))

    def forbidden(*args, **kwargs):
        pytest.fail("supplemental sampling optimized unselected candidates")

    monkeypatch.setattr(AllChem, "MMFFOptimizeMoleculeConfs", forbidden)
    task = ChemTask(
        task="rdkit_sampling",
        reactant_xyz="",
        cpus=1,
        mol_block=Chem.MolToMolBlock(mol),
        sampling=SamplingRequest(method="ETKDGv3", count=3, seed=71),
    )
    manifest = tmp_path / "sampling.json"
    manifest.write_text(task.model_dump_json())
    assert run_task(str(manifest)) == 0
    result, _ = read_task_result(str(manifest))
    assert len(result["result"]["frames"]) == 3
    assert result["result"]["method"] == "ETKDGv3"


def test_helper_result_artifacts_follow_remote_directory_pullback(tmp_path, monkeypatch):
    import shutil

    from cloudra.runtime import chem_task

    remote = tmp_path / "remote"
    local = tmp_path / "local"
    remote.mkdir()
    manifest = remote / "opt.json"
    manifest.write_text(chem_task.ChemTask(task="xtb_opt", reactant_xyz="x", cpus=1).model_dump_json())
    artifact = remote / "native_optimization_runs" / "one" / "engine.out"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("synthetic output")
    monkeypatch.setattr(
        chem_task,
        "_run_native_optimization",
        lambda *args: dict(returncode=0, log_file=str(artifact), optimized_xyz=str(artifact.with_name("xtbopt.xyz"))),
    )
    assert chem_task.run_task(str(manifest)) == 0
    shutil.copytree(remote, local)
    shutil.rmtree(remote)
    data, _ = chem_task.read_task_result(str(local / "opt.json"))
    assert Path(data["result"]["log_file"]) == local / "native_optimization_runs" / "one" / "engine.out"
    assert Path(data["result"]["log_file"]).read_text() == "synthetic output"


def test_calculator_uses_cloudra_interpreter_for_rdkit_sampling(tmp_path, monkeypatch):
    import os
    import subprocess

    pytest.importorskip("rdkit", reason="requires RDKit (chem extra)")
    from rdkit import Chem

    from cloudra.infra.compute_utils import build_calculator_cmd
    from cloudra.runtime.chem_task import ChemTask, read_task_result
    from cloudra.tools.core.conformer_selection import SamplingRequest

    graph = Chem.AddHs(Chem.MolFromSmiles("CC"))
    manifest = tmp_path / "sampling.json"
    manifest.write_text(
        ChemTask(
            task="rdkit_sampling",
            reactant_xyz="",
            cpus=1,
            mol_block=Chem.MolToMolBlock(graph),
            sampling=SamplingRequest(method="ETKDGv3", count=2, seed=9),
        ).model_dump_json()
    )
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    ok, argv, error = build_calculator_cmd(str(manifest), "chem_task")
    assert ok, error
    result = subprocess.run(argv, cwd=tmp_path, env=dict(os.environ), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data, _ = read_task_result(str(manifest))
    assert len(data["result"]["frames"]) == 2


def test_calculator_can_execute_staged_source_bundle_without_installed_cloudra(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    pytest.importorskip("rdkit", reason="requires RDKit (chem extra)")
    from rdkit import Chem

    from cloudra.infra.compute_utils import _default_calculator_path
    from cloudra.runtime.chem_task import ChemTask, read_task_result
    from cloudra.runtime.remote_compute import _stage_chem_runtime
    from cloudra.tools.core.conformer_selection import SamplingRequest

    graph = Chem.AddHs(Chem.MolFromSmiles("CC"))
    manifest = tmp_path / "sampling.json"
    manifest.write_text(
        ChemTask(
            task="rdkit_sampling",
            reactant_xyz="",
            cpus=1,
            mol_block=Chem.MolToMolBlock(graph),
            sampling=SamplingRequest(method="ETKDGv3", count=2, seed=9),
        ).model_dump_json()
    )
    bundle = tmp_path / _stage_chem_runtime(tmp_path)
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    result = subprocess.run(
        ["/bin/bash", _default_calculator_path(), str(manifest), "chem_task", sys.executable, str(bundle)],
        cwd=tmp_path,
        env=dict(os.environ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(read_task_result(str(manifest))[0]["result"]["frames"]) == 2


@pytest.mark.parametrize('kind', ['xtb_gradient', 'xtb_hessian'])
def test_native_evaluation_units_and_fixed_runtime_contract(tmp_path, monkeypatch, kind):
    import subprocess

    import numpy as np

    from cloudra.runtime import chem_task
    from cloudra.tools.core.constrained_optimization import BOHR_ANGSTROM
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        folder = Path(kwargs['cwd'])
        kwargs['stdout'].write('| TOTAL ENERGY -1.0 Eh\nnormal termination of xtb\n')
        if '--grad' in argv:
            (folder / 'gradient').write_text('$grad\ncycle = 1 SCF energy = -1.0\n0 0 0 h\n0 0 1.4 h\n1D-1 0 0\n-1D-1 0 0\n$end\n')
        else:
            (folder / 'hessian').write_text('$hessian\n' + '\n'.join(' '.join(str(x) for x in row) for row in np.eye(6)) + '\n$end\n')
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, 'run', run)
    task = chem_task.ChemTask(task=kind, reactant_xyz='2\nsynthetic\nH 0 0 0\nH 0 0 0.7408480952642\n', cpus=1)
    manifest = tmp_path / 'evaluation.json'
    manifest.write_text(task.model_dump_json())
    assert chem_task.run_task(str(manifest)) == 0
    data, _ = chem_task.read_task_result(str(manifest))
    result = data['result']
    assert result['evaluation_valid'] is True
    assert result['method_fingerprint'] == 'GFN2-xTB'
    if kind == 'xtb_gradient':
        assert result['gradient_hartree_per_angstrom'][0][0] == pytest.approx(0.1 / BOHR_ANGSTROM)
        assert result['raw_gradient_unit'] == 'Ha/Bohr'
    else:
        assert result['hessian_hartree_per_angstrom2'][0][0] == pytest.approx(1 / BOHR_ANGSTROM ** 2)
        assert result['raw_hessian_unit'] == 'Ha/Bohr^2'
    assert 'timeout' not in calls[0][1]
    assert '--iterations' not in calls[0][0] and '--opt' not in calls[0][0]
