from types import SimpleNamespace

import pytest

from cloudra.infra.slurm import (
    SlurmError,
    _engine_success_from_log,
    _is_environment_name,
    _is_job_id,
    _is_memory,
    _is_time_limit,
    build_batch_script,
    cancel_job,
    query_job,
    query_job_by_name,
    submit_batch,
)


def test_slurm_validators_use_explicit_token_rules():
    assert _is_environment_name("OMPI_MCA_slots")
    assert not _is_environment_name("9BAD")
    assert _is_job_id("12345_7")
    assert not _is_job_id("123;rm")
    assert _is_memory("32G")
    assert not _is_memory("0G")
    assert _is_time_limit("1-02:03:04")
    assert not _is_time_limit("1-2:3:4")


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
    directive_positions = [
        script.index(line)
        for line in script.splitlines()
        if line.startswith("#SBATCH ")
    ]
    assert max(directive_positions) < script.index("set -euo pipefail")
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


def test_batch_script_loads_configured_environment_modules(tmp_path, monkeypatch):
    input_file = tmp_path / "h2.inp"
    input_file.write_text("! HF STO-3G\n", encoding="utf-8")
    monkeypatch.setattr(
        "cloudra.infra.slurm.build_calculator_cmd",
        lambda path, job_type, **_kwargs: (
            True,
            ["/bin/bash", "/opt/cloudra/calculator.sh", path, job_type],
            "",
        ),
    )

    script = build_batch_script(
        input_file,
        "orca",
        7,
        {
            "type": "slurm",
            "modules": ["apps/orca/5.0.2/hpcx-2.7.4-gcc-7.3.1"],
            "environment": {
                "OMPI_MCA_rmaps_base_oversubscribe": "1",
                "OMPI_MCA_hwloc_base_binding_policy": "none",
            },
        },
    )

    source = ". /etc/profile.d/modules.sh"
    load = "module load apps/orca/5.0.2/hpcx-2.7.4-gcc-7.3.1"
    oversubscribe = "export OMPI_MCA_rmaps_base_oversubscribe=1"
    binding = "export OMPI_MCA_hwloc_base_binding_policy=none"
    capture = ".cloudra/calc-7.out.log"
    calculator = "/opt/cloudra/calculator.sh"
    assert source in script
    assert load in script
    assert oversubscribe in script
    assert binding in script
    assert "mkdir -p .cloudra" in script
    assert f"> {capture} 2>&1" in script
    assert (
        script.index(source)
        < script.index(load)
        < script.index(oversubscribe)
        < script.index(binding)
        < script.index(calculator)
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


def test_query_job_normalizes_cancelled_by_and_empty_sacct(monkeypatch):
    def fake_run(command, **kwargs):
        jobs = command[command.index("--jobs") + 1]
        if jobs == "9":
            return SimpleNamespace(returncode=0, stdout="CANCELLED by 1000|0:0\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="\n", stderr="")

    monkeypatch.setattr("cloudra.infra.slurm.subprocess.run", fake_run)
    assert query_job("9") == ("CANCELLED", "0:0")
    assert query_job("8") == ("", "")


def test_query_job_by_name_skips_terminal_rows(monkeypatch):
    """找回句柄必须跳过历史 COMPLETED，以免把旧作业当成还在跑。"""

    def fake_run(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="111|COMPLETED\n222|RUNNING\n",
            stderr="",
        )

    monkeypatch.setattr("cloudra.infra.slurm.subprocess.run", fake_run)
    assert query_job_by_name("cloudra-9") == "222"


def test_engine_success_from_log_uses_cp2k_text_markers(tmp_path):
    inp = tmp_path / "h2.inp"
    inp.write_text("&GLOBAL\n", encoding="utf-8")
    (tmp_path / "h2.out").write_text(
        " ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]              -1.0\n"
        " PROGRAM FAILED\n",
        encoding="utf-8",
    )
    assert _engine_success_from_log("cp2k", str(inp)) is False
    (tmp_path / "h2.out").write_text(
        " ENERGY| Total FORCE_EVAL ( QS ) energy [a.u.]              -1.0\n"
        " PROGRAM ENDED IN 0.13 SECONDS\n",
        encoding="utf-8",
    )
    assert _engine_success_from_log("cp2k", str(inp)) is True


def test_engine_success_from_log_uses_xtb_and_vasp_markers(tmp_path):
    xyz = tmp_path / "mol.xyz"
    xyz.write_text("2\n\nH 0 0 0\nH 0 0 1\n", encoding="utf-8")
    (tmp_path / "mol.out").write_text("some xtb noise\n", encoding="utf-8")
    assert _engine_success_from_log("xtb", str(xyz)) is False
    (tmp_path / "mol.out").write_text(
        "          * total energy  -1.0 Eh\n"
        "normal termination of xtb\n",
        encoding="utf-8",
    )
    assert _engine_success_from_log("xtb", str(xyz)) is True

    poscar = tmp_path / "POSCAR"
    poscar.write_text("H\n", encoding="utf-8")
    (tmp_path / "POSCAR.out").write_text(
        "                 General timing and accounting informations for this job:\n",
        encoding="utf-8",
    )
    assert _engine_success_from_log("vasp", str(poscar)) is True

@pytest.mark.parametrize("time_limit", ["02:03:04", "2:03:04", "1-02:03:04"])
def test_time_limit_accepts_clock_with_optional_days(tmp_path, time_limit):
    script = build_batch_script(
        tmp_path / "h2.gjf", "gaussian", 1,
        {"time_limit": time_limit}, calculator_cmd=["true"],
    )
    assert f"#SBATCH --time={time_limit}" in script


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (_is_memory, "٣٢G"),
        (_is_memory, "０G"),
        (_is_time_limit, "١-02:03:04"),
        (_is_time_limit, "1-٠٢:03:04"),
        (_is_time_limit, "1-02:٠٣:04"),
        (_is_time_limit, "1-02:03:٠٤"),
        (_is_job_id, "١٢٣"),
        (_is_job_id, "123_٧"),
        (_is_environment_name, "ÉNV"),
        (_is_environment_name, "ENVé"),
        (_is_environment_name, "ENV²"),
    ],
)
def test_slurm_validators_reject_non_ascii_tokens(validator, value):
    assert not validator(value)
