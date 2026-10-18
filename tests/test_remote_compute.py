import asyncio
import json

import pytest

from cloudra.infra.ssh_transport import SshError
from cloudra.persistence.database import ComputeDB
from cloudra.runtime.remote_compute import (
    build_remote_runner_script,
    probe_remote_shell_handle,
    recover_remote_slurm_handle,
    remote_calculator_argv,
    run_remote_compute,
)
from cloudra.services.compute_store import aget_compute_job, ainsert_compute_job


async def _fast_sleep(_seconds: float) -> None:
    # sleep(0)：跳过真实等待，但仍让出事件循环（poller 循环里的同行协程才能跑）
    await asyncio.sleep(0)


class FakeTransport:
    """SshTransport 同签名假实现：poll 响应脚本化，push/pull 记录调用。"""

    def __init__(self, poll_tokens=(), pull_action=None):
        self.poll_tokens = list(poll_tokens)
        self.pull_action = pull_action
        # 脚本耗尽后重复最后一个 token：远端终态是黏性的（退出文件/sacct 行
        # 不会在下一轮 poll 变回 RUNNING）
        self._last_token = "RUNNING"
        self.commands: list[str] = []
        self.pushes: list[tuple] = []
        self.pulls = 0

    def run(self, remote_cmd, *, timeout=30, **_kwargs):
        self.commands.append(remote_cmd)
        return (0, "", "")

    def checked(self, remote_cmd, *, timeout=30, **_kwargs):
        self.commands.append(remote_cmd)
        if "nohup" in remote_cmd:
            return "4321\n"
        if "sbatch" in remote_cmd:
            return "98765;cluster\n"
        if ".cloudra-exit" in remote_cmd or "sacct" in remote_cmd:
            if self.poll_tokens:
                self._last_token = self.poll_tokens.pop(0)
            token = self._last_token
            if isinstance(token, Exception):
                raise token
            return f"{token}\n"
        return ""

    def push_dir(self, local_dir, remote_dir, *, excludes=(), **_kwargs):
        self.pushes.append(("dir", str(local_dir), remote_dir, tuple(excludes)))

    def push_files(self, local_paths, remote_dir, **_kwargs):
        self.pushes.append(("files", [str(p) for p in local_paths], remote_dir))

    def pull_dir(self, remote_dir, local_dir, **_kwargs):
        self.pulls += 1
        if self.pull_action is not None:
            self.pull_action(remote_dir, local_dir)
        elif self._last_token in {"EXIT:0", "COMPLETED|0:0"}:
            from pathlib import Path

            Path(local_dir, "mol.out").write_text("normal termination of xtb\n", encoding="utf-8")


def _connection() -> dict:
    return {
        "type": "ssh",
        "host": "login.hpc.example.edu",
        "user": "cloudray",
        "port": 22,
        "remote_root": "/scratch/cloudray",
    }


async def _insert_running(
    tmp_path, *, scheduler="ssh_local", jobtype="xtb", handle=None, options_extra=None
):
    db = await ComputeDB().ainit()
    input_file = tmp_path / "mol.xyz"
    input_file.write_text("2\n\nH 0 0 0\nH 0 0 1\n", encoding="utf-8")
    options = {"type": scheduler, "connection": _connection(), "poll_seconds": 1}
    if options_extra:
        options.update(options_extra)
    job_id = await ainsert_compute_job(
        db,
        conversation_id="conv-test",
        session_id=None,
        path=str(input_file),
        state="running",
        jobtype=jobtype,
        node_id="remote-a",
        scheduler=scheduler,
        scheduler_options=json.dumps(options, ensure_ascii=False),
        priority=0,
        req_cpus=1,
        req_memory_mb=None,
        charge=0,
        multiplicity=1,
        xtb_task="sp",
        xtb_solvent=None,
    )
    if handle:
        from cloudra.services.compute_store import amark_slurm_submitted

        await amark_slurm_submitted(db, job_id, handle, "")
    return db, job_id, input_file


def test_runner_script_writes_pid_and_exit_files_without_set_e():
    script = build_remote_runner_script(
        "mol.xyz", "xtb", 7, {"type": "ssh_local"}, workdir="/scratch/u/cloudra-7"
    )
    assert "set -e" not in script
    assert "cd /scratch/u/cloudra-7" in script
    assert "echo $$ > .cloudra-runner-7.pid" in script
    assert ".cloudra-pid-7" not in script
    assert "echo \"$rc\" > .cloudra-exit-7" in script
    assert "> .cloudra/calc-7.out.log 2>&1 &" in script
    assert "bash calculator.sh mol.xyz xtb" in script


def test_remote_calculator_argv_uses_shipped_calculator():
    from cloudra.infra.compute_utils import XtbParams

    assert remote_calculator_argv("a.inp", "orca") == ["bash", "calculator.sh", "a.inp", "orca"]
    argv = remote_calculator_argv(
        "mol.xyz", "xtb", XtbParams(charge=-1, multiplicity=2, task="opt", cpus=4)
    )
    assert argv[:4] == ["bash", "calculator.sh", "mol.xyz", "xtb"]
    assert "--chrg" in argv and "-1" in argv
    assert "--uhf" in argv and "1" in argv
    assert "--task" in argv and "opt" in argv
    assert "--parallel" in argv and "4" in argv


@pytest.mark.asyncio
async def test_ssh_local_happy_path_stages_polls_and_finalizes(tmp_path):
    db, job_id, input_file = await _insert_running(tmp_path)
    transport = FakeTransport(poll_tokens=["RUNNING", "EXIT:0"])

    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )

    assert rc == 0
    row = await aget_compute_job(db, job_id)
    assert row["state"] == "done"
    assert row["scheduler_job_id"] == "shell:4321"
    # stage：整棵 workdir + 单独推内置 calculator.sh
    assert transport.pushes[0][0] == "dir"
    assert transport.pushes[0][2] == "/scratch/cloudray/cloudra-%d" % job_id
    assert ".cloudra/" in transport.pushes[0][3]
    assert transport.pushes[1][0] == "files"
    assert transport.pushes[1][1][0].endswith("calculator.sh")
    # 提交脚本写在本地 workdir（可审计），远端 nohup 拉起
    assert (tmp_path / f".cloudra-run-{job_id}.sh").is_file()
    assert any("nohup" in cmd for cmd in transport.commands)
    assert transport.pulls == 1


@pytest.mark.asyncio
async def test_ssh_local_engine_gate_overrides_zero_exit_code(tmp_path):
    """runner 退出码 0 不够——拉回日志过不了引擎文本闸门照样 failed。"""

    def pull_writes_bad_log(_remote_dir, local_dir):
        from pathlib import Path

        Path(local_dir, "mol.out").write_text("some xtb noise\n", encoding="utf-8")

    db, job_id, _ = await _insert_running(tmp_path)
    transport = FakeTransport(poll_tokens=["EXIT:0"], pull_action=pull_writes_bad_log)

    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )

    assert rc == 1
    row = await aget_compute_job(db, job_id)
    assert row["state"] == "failed"
    assert "engine error termination" in (row["last_error"] or "")


@pytest.mark.asyncio
async def test_ssh_local_engine_gate_confirms_done(tmp_path):
    def pull_writes_good_log(_remote_dir, local_dir):
        from pathlib import Path

        Path(local_dir, "mol.out").write_text(
            "          * total energy  -1.0 Eh\nnormal termination of xtb\n",
            encoding="utf-8",
        )

    db, job_id, _ = await _insert_running(tmp_path)
    transport = FakeTransport(poll_tokens=["EXIT:0"], pull_action=pull_writes_good_log)

    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )
    assert rc == 0
    assert (await aget_compute_job(db, job_id))["state"] == "done"


@pytest.mark.asyncio
async def test_ssh_local_cancel_requested_is_delivered_to_owning_runner(tmp_path):
    db, job_id, _ = await _insert_running(tmp_path, handle="shell:4321")
    transport = FakeTransport(poll_tokens=["RUNNING", "RUNNING", "EXIT:143"])

    async def flip_after_delay():
        await asyncio.sleep(0)
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE compute_jobs SET state='cancel_requested' WHERE id=?",
                (job_id,),
            )
            await con.commit()

    flipper = asyncio.create_task(flip_after_delay())
    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )
    await flipper

    assert rc == 1
    row = await aget_compute_job(db, job_id)
    assert row["state"] == "cancelled"
    assert any("touch " in cmd and ".cloudra-cancel-" in cmd for cmd in transport.commands)
    assert not any("kill -TERM" in cmd for cmd in transport.commands)


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduler", ["ssh_local", "ssh_slurm"])
@pytest.mark.parametrize("jobtype", ["xtb", "shell"])
async def test_remote_cancel_keeps_capacity_until_confirmed_exit(tmp_path, scheduler, jobtype):
    """A failed cancellation request is retried; only execution evidence releases capacity."""
    db, job_id, _ = await _insert_running(
        tmp_path, scheduler=scheduler, jobtype=jobtype,
        handle="shell:4321" if scheduler == "ssh_local" else "98765",
    )
    async with db.aconnect() as con:
        await con.execute("UPDATE compute_jobs SET state='cancel_requested' WHERE id=?", (job_id,))
        await con.commit()

    class CancellingTransport(FakeTransport):
        attempts = 0

        def checked(self, command, **kwargs):
            if "scancel" in command or "touch " in command:
                self.commands.append(command)
                self.attempts += 1
                if self.attempts == 1:
                    raise SshError("cancel request interrupted")
                return ""
            return super().checked(command, **kwargs)

    tokens = ["RUNNING", "EXIT:143"] if scheduler == "ssh_local" else ["RUNNING|0:0", "CANCELLED|0:15"]
    transport = CancellingTransport(poll_tokens=tokens)
    pending = []

    async def observe_pending(_seconds):
        from cloudra.services.compute_store import compute_inflight_usage_by_node

        pending.append((await aget_compute_job(db, job_id))["state"])
        usage = await asyncio.to_thread(
            compute_inflight_usage_by_node, db,
            default_node_id="remote-a", fair_share_mb={"remote-a": 1024},
        )
        assert usage["remote-a"]["slots"] == 1
        await asyncio.sleep(0)

    assert await run_remote_compute(job_id, db.path, transport=transport, sleep=observe_pending) == 1
    assert pending == ["cancel_requested"]
    assert transport.attempts == 2
    assert not any("kill -TERM" in command for command in transport.commands)
    assert (await aget_compute_job(db, job_id))["state"] == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduler", ["ssh_local", "ssh_slurm"])
async def test_remote_scientific_job_needs_native_termination_log(tmp_path, scheduler):
    db, job_id, _ = await _insert_running(tmp_path, scheduler=scheduler)
    token = "EXIT:0" if scheduler == "ssh_local" else "COMPLETED|0:0"
    transport = FakeTransport(poll_tokens=[token], pull_action=lambda *_args: None)

    assert await run_remote_compute(job_id, db.path, transport=transport, sleep=_fast_sleep) == 1
    row = await aget_compute_job(db, job_id)
    assert row["state"] == "failed"
    assert "native" in row["last_error"].lower()


@pytest.mark.asyncio
async def test_ssh_local_pull_back_retry_then_failed(tmp_path):
    def always_fail(_remote_dir, _local_dir):
        raise SshError("rsync boom")

    db, job_id, _ = await _insert_running(tmp_path)
    transport = FakeTransport(poll_tokens=["EXIT:0"], pull_action=always_fail)

    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )
    assert rc == 1
    row = await aget_compute_job(db, job_id)
    assert row["state"] == "failed"
    assert "pull-back" in (row["last_error"] or "")
    assert transport.pulls == 5


@pytest.mark.asyncio
async def test_ssh_local_vanished_runner_does_not_prove_calculator_exit(tmp_path):
    db, job_id, _ = await _insert_running(tmp_path)
    transport = FakeTransport(poll_tokens=["VANISHED", "EXIT:0"])
    pending = []

    async def observe_pending(_seconds):
        pending.append((await aget_compute_job(db, job_id))["state"])
        assert transport.pulls == 0

    rc = await run_remote_compute(
        job_id, db.path, sleep=observe_pending, transport=transport
    )
    assert rc == 0
    assert pending == ["running"]
    row = await aget_compute_job(db, job_id)
    assert row["state"] == "done"


@pytest.mark.asyncio
async def test_ssh_local_transient_transport_error_is_tolerated(tmp_path):
    db, job_id, _ = await _insert_running(tmp_path)
    transport = FakeTransport(
        poll_tokens=[SshError("ssh boom"), "RUNNING", "EXIT:0"]
    )
    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )
    assert rc == 0
    assert (await aget_compute_job(db, job_id))["state"] == "done"


@pytest.mark.asyncio
async def test_ssh_local_reattach_skips_resubmit(tmp_path):
    """已有句柄（重启重挂）只续 poll，绝不重 stage/重提交。"""
    db, job_id, _ = await _insert_running(tmp_path, handle="shell:4321")
    transport = FakeTransport(poll_tokens=["EXIT:0"])

    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )
    assert rc == 0
    assert not transport.pushes
    assert not any("nohup" in cmd for cmd in transport.commands)


@pytest.mark.asyncio
async def test_ssh_slurm_completed_gates_engine_log(tmp_path):
    db, job_id, _ = await _insert_running(tmp_path, scheduler="ssh_slurm")
    transport = FakeTransport(poll_tokens=["PENDING|0:0", "COMPLETED|0:0"])

    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )
    assert rc == 0
    row = await aget_compute_job(db, job_id)
    assert row["state"] == "done"
    assert row["scheduler_job_id"] == "98765"
    assert any("sbatch" in cmd for cmd in transport.commands)
    # slurm batch 脚本走远端路径覆盖：cd 远端目录、calculator 用 basename
    script = (tmp_path / f".cloudra-slurm-{job_id}.sh").read_text(encoding="utf-8")
    assert f"cd /scratch/cloudray/cloudra-{job_id}" in script
    assert "bash calculator.sh mol.xyz xtb" in script


@pytest.mark.asyncio
async def test_ssh_slurm_failure_state_and_vanished_row(tmp_path):
    db, job_id, _ = await _insert_running(tmp_path, scheduler="ssh_slurm")
    transport = FakeTransport(poll_tokens=["FAILED|1:0"])
    rc = await run_remote_compute(
        job_id, db.path, sleep=_fast_sleep, transport=transport
    )
    assert rc == 1
    assert "Slurm FAILED" in (await aget_compute_job(db, job_id))["last_error"] or ""

    db2, job_id2, _ = await _insert_running(tmp_path, scheduler="ssh_slurm")
    transport2 = FakeTransport(poll_tokens=["RUNNING|0:0", "", "", ""])
    rc2 = await run_remote_compute(
        job_id2, db2.path, sleep=_fast_sleep, transport=transport2
    )
    assert rc2 == 1
    assert "vanished" in (await aget_compute_job(db2, job_id2))["last_error"]


def test_recover_remote_slurm_handle_parses_nonterminal(monkeypatch):
    monkeypatch.setattr(
        "cloudra.runtime.remote_compute.run_remote",
        lambda endpoint, cmd, **kwargs: (0, "111|COMPLETED\n222|RUNNING\n", ""),
    )
    row = {
        "id": 9,
        "scheduler_options": json.dumps({"connection": _connection()}),
    }
    assert recover_remote_slurm_handle(row) == "222"


def test_recover_remote_slurm_handle_tolerates_transport_failure(monkeypatch):
    def boom(endpoint, cmd, **kwargs):
        raise SshError("down")

    monkeypatch.setattr("cloudra.runtime.remote_compute.run_remote", boom)
    row = {"id": 9, "scheduler_options": json.dumps({"connection": _connection()})}
    assert recover_remote_slurm_handle(row) is None


def test_probe_remote_shell_handle_reads_pid_file(monkeypatch):
    monkeypatch.setattr(
        "cloudra.runtime.remote_compute.run_remote",
        lambda endpoint, cmd, **kwargs: (0, "4321\n", ""),
    )
    row = {"id": 9, "scheduler_options": json.dumps({"connection": _connection()})}
    assert probe_remote_shell_handle(row) == "shell:4321"

    monkeypatch.setattr(
        "cloudra.runtime.remote_compute.run_remote",
        lambda endpoint, cmd, **kwargs: (0, "", ""),
    )
    assert probe_remote_shell_handle(row) is None


@pytest.mark.parametrize('kind', ['ssh_local', 'ssh_slurm'])
def test_remote_helper_carries_trusted_runtime_and_code_bundle(tmp_path, kind):
    import sys
    import zipfile

    from cloudra.runtime.remote_compute import _stage_and_submit
    transport = FakeTransport()
    source = tmp_path / 'task.json'
    source.write_text('{}')
    options = {'environment': {'CLOUDRA_CHEM_PYTHON': sys.executable}}
    _handle, script = _stage_and_submit(transport, kind, 1, source, tmp_path,
        '/remote/job', 'chem_task', {}, options)
    text = __import__('pathlib').Path(script).read_text()
    assert sys.executable in text
    bundles = list(tmp_path.glob('.cloudra-chem-runtime-*.zip'))
    assert len(bundles) == 1
    assert bundles[0].name in text
    with zipfile.ZipFile(bundles[0]) as archive:
        assert 'cloudra/runtime/chem_task.py' in archive.namelist()
    assert transport.pushes


def test_remote_helper_requires_explicit_node_python_before_submission(tmp_path):
    from cloudra.runtime.remote_compute import _stage_and_submit
    transport = FakeTransport()
    source = tmp_path / 'task.json'
    source.write_text('{}')
    with pytest.raises(ValueError, match='CLOUDRA_CHEM_PYTHON'):
        _stage_and_submit(transport, 'ssh_local', 1, source, tmp_path, '/remote/job', 'chem_task', {}, {})
    assert not transport.pushes
    assert not any('nohup' in command for command in transport.commands)
