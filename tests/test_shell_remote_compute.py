import asyncio
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from cloudra.infra.compute_utils import resolve_log_path
from cloudra.infra.slurm import build_batch_script, run_slurm_compute
from cloudra.infra.ssh_transport import SshEndpoint, check_remote_environment
from cloudra.persistence.database import ComputeDB
from cloudra.runtime.remote_compute import build_remote_runner_script, run_remote_compute
from cloudra.services.compute_store import (
    aget_compute_job,
    ainsert_compute_job,
    amark_slurm_submitted,
)


async def _no_delay(_seconds):
    await asyncio.sleep(0)


async def _running_shell(tmp_path, scheduler):
    db = await ComputeDB().ainit()
    input_file = tmp_path / "train.sh"
    input_file.write_text("echo training\n", encoding="utf-8")
    options = {
        "type": scheduler,
        "connection": {
            "type": "ssh",
            "host": "test.invalid",
            "user": "test",
            "port": 22,
            "remote_root": "/scratch/test",
        },
    }
    job_id = await ainsert_compute_job(
        db,
        conversation_id="shell-test",
        session_id=None,
        path=str(input_file),
        state="running",
        jobtype="shell",
        node_id="shell-node",
        scheduler=scheduler,
        scheduler_options=json.dumps(options),
    )
    if scheduler == "slurm":
        await amark_slurm_submitted(db, job_id, "123", "")
    return db, job_id, input_file


def _unexpected_chemistry(*_args, **_kwargs):
    raise AssertionError("shell jobs must not parse chemistry logs")


@pytest.mark.parametrize("exit_code", [0, 7])
def test_shell_slurm_script_captures_output_and_preserves_exit(tmp_path, exit_code):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("requires bash")
    input_file = tmp_path / "train job.sh"
    input_file.write_text(
        f"echo training\necho diagnostic >&2\npwd > artifact.txt\nexit {exit_code}\n",
        encoding="utf-8",
    )
    batch = tmp_path / "batch.sh"
    batch.write_text(
        build_batch_script(
            input_file, "shell", 42, {}, calculator_cmd=[bash, str(input_file)]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run([bash, str(batch)], capture_output=True, text=True, check=False)

    assert completed.returncode == exit_code
    assert (tmp_path / "artifact.txt").read_text().strip() == str(tmp_path)
    captured = (tmp_path / ".cloudra" / "calc-42.out.log").read_text()
    assert "training" in captured
    assert "diagnostic" in captured
    assert resolve_log_path(str(input_file), job_type="shell", task_id=42) == str(
        tmp_path / ".cloudra" / "calc-42.out.log"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "exit_code", "expected"),
    [
        ("COMPLETED", "0:0", "done"),
        ("COMPLETED", "7:0", "failed"),
        ("COMPLETED", "0:9", "failed"),
        ("FAILED", "0:0", "failed"),
    ],
)
async def test_shell_local_slurm_uses_state_and_exit_code(
    tmp_path, monkeypatch, state, exit_code, expected
):
    db, job_id, _ = await _running_shell(tmp_path, "slurm")
    monkeypatch.setattr("cloudra.infra.slurm.query_job", lambda _job_id: (state, exit_code))
    monkeypatch.setattr("cloudra.infra.slurm._engine_success_from_log", _unexpected_chemistry)

    rc = await run_slurm_compute(job_id, db.path, scheduler={}, sleep=_no_delay)

    row = await aget_compute_job(db, job_id)
    assert row["state"] == expected
    assert rc == (0 if expected == "done" else 1)
    if expected == "failed":
        assert exit_code in row["last_error"]


class _Transport:
    def __init__(self, token):
        self.token = token
        self.staged = None

    def checked(self, command, **_kwargs):
        if "sbatch" in command:
            return "123\n"
        if "nohup" in command:
            return "456\n"
        if "sacct" in command or ".cloudra-exit-" in command:
            return self.token + "\n"
        return ""

    def push_dir(self, local_dir, remote_dir, **_kwargs):
        self.staged = (str(local_dir), remote_dir)

    def push_files(self, *_args, **_kwargs):
        pass

    def pull_dir(self, _remote_dir, local_dir):
        Path(local_dir, "checkpoint.txt").write_text("saved", encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scheduler", "token", "expected"),
    [
        ("ssh_local", "EXIT:0", "done"),
        ("ssh_local", "EXIT:7", "failed"),
        ("ssh_slurm", "COMPLETED|0:0", "done"),
        ("ssh_slurm", "COMPLETED|7:0", "failed"),
        ("ssh_slurm", "COMPLETED|0:9", "failed"),
        ("ssh_slurm", "FAILED|0:0", "failed"),
    ],
)
async def test_shell_remote_returns_artifacts_and_uses_exit_code(
    tmp_path, monkeypatch, scheduler, token, expected
):
    db, job_id, _ = await _running_shell(tmp_path, scheduler)
    transport = _Transport(token)
    monkeypatch.setattr("cloudra.runtime.remote_compute._engine_success_from_log", _unexpected_chemistry)

    rc = await run_remote_compute(job_id, db.path, transport=transport, sleep=_no_delay)

    row = await aget_compute_job(db, job_id)
    assert row["state"] == expected
    assert rc == (0 if expected == "done" else 1)
    assert transport.staged == (str(tmp_path), f"/scratch/test/cloudra-{job_id}")
    assert (tmp_path / "checkpoint.txt").read_text() == "saved"


def test_shell_remote_environment_only_requires_execution_and_transport(monkeypatch):
    endpoint = SshEndpoint(host="test.invalid", user="test", port=22, remote_root="/scratch/test")
    monkeypatch.setattr("cloudra.infra.ssh_transport.shutil.which", lambda _name: "/bin/rsync")

    def probe(_endpoint, bins):
        # No chemistry engine or Python distribution is needed for admission.
        assert set(bins) == {"bash", "rsync"}
        return True, []

    monkeypatch.setattr("cloudra.infra.ssh_transport.check_remote_bins", probe)
    assert check_remote_environment(endpoint, "shell", slurm=False) == (True, "")


class _LocalCommandTransport:
    """Run the remote control commands against isolated, real local processes."""

    def checked(self, command, **_kwargs):
        completed = subprocess.run(
            ["bash", "-c", command], check=True, capture_output=True, text=True, timeout=3,
        )
        return completed.stdout

    def run(self, command, **_kwargs):
        completed = subprocess.run(
            ["bash", "-c", command], check=False, capture_output=True, text=True, timeout=3,
        )
        return completed.returncode, completed.stdout, completed.stderr

    def pull_dir(self, *_args):
        pass


async def _wait_until(predicate):
    deadline = asyncio.get_running_loop().time() + 5
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("isolated process did not reach the expected state")
        await asyncio.sleep(0.02)


def _start_training_runner(workdir, task_id, background=False, jobtype="shell"):
    workdir.mkdir(parents=True)
    training = workdir / "train.py"
    training.write_text(
        "import os, signal, time\n"
        "from pathlib import Path\n"
        "def stop(*_args):\n"
        "    Path('stopping').touch()\n"
        "    while not Path('allow-stop').exists(): time.sleep(0.02)\n"
        "    Path('stopped').touch()\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "Path('child.pid').write_text(str(os.getpid()))\n"
        "while True: time.sleep(0.02)\n",
        encoding="utf-8",
    )
    script = workdir / "train.sh"
    script.write_text(
        f"{shlex.quote(sys.executable)} train.py{' &' if background else ''}\necho finished\n",
        encoding="utf-8",
    )
    runner = workdir / "runner.sh"
    runner.write_text(
        build_remote_runner_script(
            script.name, jobtype, task_id, {}, workdir=str(workdir),
            calculator_cmd=["bash", str(script)],
        ),
        encoding="utf-8",
    )
    return subprocess.Popen(
        ["bash", str(runner)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _cleanup_training_runner(workdir, process):
    (workdir / "allow-stop").touch()
    pid_file = workdir / "child.pid"
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text()), signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=3)


@pytest.mark.asyncio
@pytest.mark.parametrize("background", [False, True], ids=["foreground", "background"])
@pytest.mark.parametrize("jobtype", ["shell", "xtb"])
async def test_remote_cancel_waits_for_owned_group_and_leaves_other_job_running(tmp_path, background, jobtype):
    if shutil.which("bash") is None:
        pytest.skip("requires bash")
    db, job_id, _ = await _running_shell(tmp_path, "ssh_local")
    remote_root = tmp_path / "remote"
    workdir = remote_root / f"cloudra-{job_id}"
    other_workdir = remote_root / "other-job"
    row = await aget_compute_job(db, job_id)
    options = json.loads(row["scheduler_options"])
    options["connection"]["remote_root"] = str(remote_root)
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET scheduler_options=?, jobtype=? WHERE id=?",
            (json.dumps(options), jobtype, job_id),
        )
        await con.commit()
    process = await asyncio.to_thread(_start_training_runner, workdir, job_id, background, jobtype)
    other = await asyncio.to_thread(_start_training_runner, other_workdir, 999)
    poller = None
    try:
        await _wait_until(lambda: (workdir / "child.pid").exists() and (other_workdir / "child.pid").exists())
        await amark_slurm_submitted(db, job_id, f"shell:{process.pid}", "")

        async def short_sleep(_seconds):
            await asyncio.sleep(0.02)

        poller = asyncio.create_task(
            run_remote_compute(job_id, db.path, transport=_LocalCommandTransport(), sleep=short_sleep)
        )
        async with db.aconnect() as con:
            await con.execute("UPDATE compute_jobs SET state='cancel_requested' WHERE id=?", (job_id,))
            await con.commit()
        await _wait_until(lambda: poller.done() or (workdir / "stopping").exists())

        assert (await aget_compute_job(db, job_id))["state"] == "cancel_requested"
        assert (workdir / "stopping").exists(), "TERM must reach the Python child through its owned job group"
        assert not (workdir / f".cloudra-exit-{job_id}").exists()
        assert not (other_workdir / "stopping").exists()
        os.kill(int((other_workdir / "child.pid").read_text()), 0)

        (workdir / "allow-stop").touch()
        assert await asyncio.wait_for(poller, timeout=5) == 1
        assert (await aget_compute_job(db, job_id))["state"] == "cancelled"
        assert (workdir / "stopped").exists()
        assert (workdir / f".cloudra-exit-{job_id}").exists()
        with pytest.raises(ProcessLookupError):
            os.kill(int((workdir / "child.pid").read_text()), 0)
        assert other.poll() is None
    finally:
        if poller is not None and not poller.done():
            poller.cancel()
            await asyncio.gather(poller, return_exceptions=True)
        await asyncio.to_thread(_cleanup_training_runner, workdir, process)
        await asyncio.to_thread(_cleanup_training_runner, other_workdir, other)
