"""Shell jobs execute in their directory and retain exit status across guard recovery."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloudra.infra.compute_utils import calc_lock_path, check_job_type, resolve_log_path
from cloudra.infra.flocks import is_lock_held
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import get_compute_job, insert_compute_job

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="requires Bash")


def _job(db, script):
    return insert_compute_job(
        db, node_id="node-local", conversation_id="shell-test", session_id="s1",
        path=str(script), state="running", jobtype="shell", scheduler="local",
    )


@pytest.fixture
def no_dag_review(monkeypatch):
    async def enqueue(*_args):
        pass

    monkeypatch.setattr("cloudra.dag.controller.enqueue_compute_review", enqueue)


def test_shell_requires_bash_only(tmp_path):
    ok, message = check_job_type("shell", str(tmp_path))
    assert ok, message


@pytest.mark.parametrize("exit_code", [0, 23])
@pytest.mark.asyncio
async def test_shell_guard_runs_script_and_reports_exit_code(tmp_path, no_dag_review, exit_code):
    from cloudra.runtime.monitor import run_guard

    workdir = tmp_path / "shell task 中文"
    workdir.mkdir()
    (workdir / "config.txt").write_text("training configuration\n")
    script = workdir / "run training.sh"
    script.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        "cat config.txt > result.txt\n"
        "printf 'stdout from script\\n'\n"
        "printf 'stderr from script\\n' >&2\n"
        f"exit {exit_code}\n"
    )
    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, script)

    await asyncio.wait_for(run_guard(
        job_id, str(script), "shell-test", 1, db.path, job_type="shell",
    ), timeout=15)

    row = await asyncio.to_thread(get_compute_job, db, job_id)
    assert row["state"] == ("done" if exit_code == 0 else "failed"), row["last_error"]
    assert (workdir / "result.txt").read_text() == "training configuration\n"
    result = json.loads((workdir / f"state_{job_id}.json").read_text())
    assert result["exit_code"] == exit_code
    log = Path(resolve_log_path(str(script), "shell", job_id)).read_text()
    assert "stdout from script" in log
    assert "stderr from script" in log
    if exit_code:
        assert "23" in row["last_error"]


@pytest.mark.parametrize("exit_code", [0, 19])
@pytest.mark.asyncio
async def test_shell_adopt_recovers_persisted_exit_code_without_rerunning(
    tmp_path, no_dag_review, exit_code,
):
    from cloudra.runtime.monitor import run_adopt

    script = tmp_path / "run.sh"
    script.write_text(f"printf 'once\\n' >> runs.txt\nexit {exit_code}\n")
    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, script)
    lock = calc_lock_path(str(tmp_path), job_id)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "cloudra.runtime.calc_lock_wrapper", lock, "--",
        shutil.which("bash"), str(script), cwd=str(tmp_path), start_new_session=True,
    )
    assert await asyncio.wait_for(proc.wait(), timeout=15) == exit_code

    await run_adopt(job_id, str(script), "shell-test", 1, db.path, job_type="shell")

    row = await asyncio.to_thread(get_compute_job, db, job_id)
    assert row["state"] == ("done" if exit_code == 0 else "failed"), row["last_error"]
    result = json.loads((tmp_path / f"state_{job_id}.json").read_text())
    assert result["exit_code"] == exit_code
    assert (tmp_path / "runs.txt").read_text() == "once\n"


@pytest.mark.asyncio
async def test_quiet_shell_success_needs_no_chemical_log(tmp_path, no_dag_review):
    from cloudra.runtime.monitor import run_guard

    script = tmp_path / "quiet.sh"
    script.write_text("exit 0\n")
    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, script)
    await asyncio.wait_for(run_guard(
        job_id, str(script), "shell-test", 1, db.path, job_type="shell",
    ), timeout=15)
    assert (await asyncio.to_thread(get_compute_job, db, job_id))["state"] == "done"


@pytest.mark.asyncio
async def test_shell_adopt_missing_exit_code_does_not_assume_success(tmp_path, no_dag_review):
    from cloudra.runtime.monitor import run_adopt

    script = tmp_path / "run.sh"
    script.write_text("exit 0\n")
    script.with_suffix(".out").write_text("Normal termination of Gaussian\n")
    db = await ComputeDB().ainit()
    job_id = await asyncio.to_thread(_job, db, script)
    await run_adopt(job_id, str(script), "shell-test", 1, db.path, job_type="shell")
    row = await asyncio.to_thread(get_compute_job, db, job_id)
    assert row["state"] == "failed"
    assert "exit" in row["last_error"].lower()


@pytest.mark.asyncio
async def test_wrapper_holds_lock_even_when_script_closes_inherited_descriptors(tmp_path):
    """An adopt guard must not observe a free calc lock before the exit receipt exists."""
    script = tmp_path / "close_fds.py"
    script.write_text(
        "import os, pathlib, time\n"
        "os.closerange(3, 256)\n"
        "pathlib.Path('started').touch()\n"
        "while not pathlib.Path('finish').exists(): time.sleep(0.02)\n"
    )
    lock = calc_lock_path(str(tmp_path), 1)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "cloudra.runtime.calc_lock_wrapper", lock, "--",
        sys.executable, str(script), cwd=str(tmp_path), start_new_session=True,
    )
    try:
        async with asyncio.timeout(10):
            while not await asyncio.to_thread((tmp_path / "started").exists):
                await asyncio.sleep(0.02)
        assert await asyncio.to_thread(is_lock_held, lock)
    finally:
        await asyncio.to_thread((tmp_path / "finish").touch)
        await asyncio.wait_for(proc.wait(), timeout=10)
    receipt = json.loads(Path(lock).with_suffix(".exit.json").read_text())
    assert receipt["exit_code"] == 0


@pytest.mark.parametrize("exit_code", [0, 17])
@pytest.mark.asyncio
async def test_sync_shell_submit_returns_real_execution_result(tmp_path, exit_code):
    from cloudra.tools.Chemtool.submit_compute_job import (
        SubmitComputeJob,
        SubmitComputeJob_input_schema,
    )

    script = tmp_path / "run.sh"
    script.write_text(f"printf 'result\\n' > result.txt\nexit {exit_code}\n")
    tool = SubmitComputeJob(subagent=SimpleNamespace(
        conversation_id="shell-test", working_directory=str(tmp_path),
    ))
    result = await asyncio.wait_for(tool.tool_call(
        SubmitComputeJob_input_schema(input_file=script.name, job_type="shell"), session=None,
    ), timeout=15)

    assert result.job_id > 0, result.message
    assert result.state == ("done" if exit_code == 0 else "failed"), result.message
    assert result.is_success == (exit_code == 0)
    assert (tmp_path / "result.txt").read_text() == "result\n"
    row = await asyncio.to_thread(get_compute_job, ComputeDB(), result.job_id)
    assert row["state"] == result.state
