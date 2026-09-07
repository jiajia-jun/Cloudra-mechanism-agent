from types import SimpleNamespace

import pytest

from cloudra.infra.slurm import (
    SlurmError,
    build_batch_script,
    cancel_job,
    query_job,
    submit_batch,
)


def test_batch_script_uses_validated_directives_and_shell_quoting(
    tmp_path,
    monkeypatch,
):
    input_file = tmp_path / "h2 molecule.gjf"
    input_file.write_text("# test\n", encoding="utf-8")
    monkeypatch.setattr(
        "cloudra.infra.slurm.build_calculator_cmd",
        lambda path, job_type, **_kwargs: (True, ["/bin/bash", "/opt/cloudra/calculator.sh", path, job_type], ""),
    )
    script = build_batch_script(
        input_file,
        "gaussian",
        42,
        {
            "type": "slurm",
            "partition": "compute-a",
            "account": "chem.lab",
            "time_limit": "1-02:03:04",
            "cpus": 8,
            "memory": "32G",
        },
    )

    assert "#SBATCH --partition=compute-a" in script
    assert "#SBATCH --account=chem.lab" in script
    assert "#SBATCH --time=1-02:03:04" in script
    assert "#SBATCH --cpus-per-task=8" in script
    assert "#SBATCH --mem=32G" in script
    assert "shell=True" not in script
    assert str(input_file) in script


def test_batch_script_rejects_directive_injection(tmp_path, monkeypatch):
    input_file = tmp_path / "h2.gjf"
    input_file.write_text("# test\n", encoding="utf-8")
    monkeypatch.setattr(
        "cloudra.infra.slurm.build_calculator_cmd",
        lambda path, job_type, **_kwargs: (True, ["/bin/bash", "calculator.sh", path, job_type], ""),
    )
    with pytest.raises(SlurmError, match="partition"):
        build_batch_script(
            input_file,
            "gaussian",
            1,
            {"partition": "compute\n#SBATCH --chdir=/tmp"},
        )


def test_slurm_commands_use_argument_arrays_and_validate_job_ids(
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[0] == "sbatch":
            return SimpleNamespace(returncode=0, stdout="12345;cluster\n", stderr="")
        if command[0] == "sacct":
            return SimpleNamespace(returncode=0, stdout="COMPLETED|0:0\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("cloudra.infra.slurm.subprocess.run", fake_run)
    script = tmp_path / "job.sh"
    script.write_text("#!/bin/bash\n", encoding="utf-8")

    assert submit_batch(script) == "12345"
    assert query_job("12345") == ("COMPLETED", "0:0")
    cancel_job("12345")
    assert [call[0][0] for call in calls] == ["sbatch", "sacct", "scancel"]
    assert all(isinstance(call[0], list) for call in calls)
    with pytest.raises(SlurmError, match="job id"):
        cancel_job("123; rm -rf x")
