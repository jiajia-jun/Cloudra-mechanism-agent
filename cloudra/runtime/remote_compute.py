"""远端计算执行器：``ssh_local`` / ``ssh_slurm`` 作业的看守 poller（唯一实现）。

形状对齐 ``infra/slurm.py:run_slurm_compute``：认领进程内 async 轮询即看守，
远端**不起 guard、不需要远端 Python/cloudra**（只要求 bash + 引擎 + rsync）。
生命周期：

    stage   rsync 推整棵本地 workdir（VASP 的 INCAR/POSCAR 等邻接文件必须同行；
            排除 .cloudra/ 与 .g16_scratch/ 运行时缓存）+ 单独推内置
            calculator.sh（绝不落进 workdir——compute.allow_local_calculator
            开启时它会被误拾为本地执行入口）
    submit  ssh_slurm → 远端 sbatch（job-name 锚点 cloudra-<id>）；
            ssh_local → nohup 直跑 runner 脚本，句柄按 ``shell:<pid>`` 落账
    poll    sacct over ssh / 远端退出文件 + pid 探活；scheduler_state 回写账本
    终态    rsync 拉回远端目录全部产物到本地输入目录（有界重试），本地跑
            ``infra/slurm.py:_engine_success_from_log`` 引擎文本闸门复核，
            afinalize_compute_job CAS 落账本

取消只走账本 cancel_requested → 远端 scancel（ssh_slurm）/ kill runner 与
其 calculator 子进程（ssh_local，仅显式取消路径；best-effort，账本收口不依赖
远端应答）。传输错误按瞬态容忍（下一轮重试）；重启恢复由 scheduler 对账器
调本模块的 recover/probe 函数找回句柄后重挂 poller。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
from collections.abc import Awaitable, Callable
from pathlib import Path

from cloudra.infra.compute_utils import XtbParams, _default_calculator_path
from cloudra.infra.slurm import (
    SLURM_TERMINAL_FAILURE,
    SLURM_TERMINAL_SUCCESS,
    _engine_success_from_log,
    _is_job_id,
    build_batch_script,
    parse_sacct_job_id,
    parse_sacct_state,
    scheduler_setup_lines,
)
from cloudra.infra.ssh_transport import (
    SshEndpoint,
    SshError,
    pull_dir,
    push_dir,
    push_files,
    run_remote,
    run_remote_checked,
)
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import (
    acancel_compute_job,
    afinalize_compute_job,
    aget_compute_job,
    amark_slurm_submitted,
    aupdate_scheduler_state,
)

logger = logging.getLogger(__name__)

REMOTE_KINDS = ("ssh_local", "ssh_slurm")
_SHELL_HANDLE_PREFIX = "shell:"
# 终态后产物拉回的有界重试次数（传输错误瞬态容忍，但终态收口不能无限等）
_MAX_PULL_ATTEMPTS = 5
# stage/submit 期间远端命令的超时上限
_STAGE_TIMEOUT = 600


class SshTransport:
    """ssh_transport 原语的对象封装：remote_compute 的默认传输。

    测试注入同名方法集的假实现（签名对齐、带 **_kwargs 防加参变红）。
    """

    def __init__(self, endpoint: SshEndpoint) -> None:
        self.endpoint = endpoint

    def run(self, remote_cmd: str, *, timeout: float = 30) -> tuple[int, str, str]:
        return run_remote(self.endpoint, remote_cmd, timeout=timeout)

    def checked(self, remote_cmd: str, *, timeout: float = 30) -> str:
        return run_remote_checked(self.endpoint, remote_cmd, timeout=timeout)

    def push_dir(
        self, local_dir: str | Path, remote_dir: str, *, excludes: tuple[str, ...] = ()
    ) -> None:
        push_dir(self.endpoint, local_dir, remote_dir, excludes=excludes)

    def push_files(self, local_paths: list[str | Path], remote_dir: str) -> None:
        push_files(self.endpoint, local_paths, remote_dir)

    def pull_dir(self, remote_dir: str, local_dir: str | Path) -> None:
        pull_dir(self.endpoint, remote_dir, local_dir, timeout=_STAGE_TIMEOUT)


def _scheduler_options(row: dict) -> dict:
    try:
        parsed = json.loads(row.get("scheduler_options") or "")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def remote_calculator_argv(
    input_name: str, job_type: str, xtb_params: XtbParams | None = None
) -> list[str]:
    """远端 calculator 命令：随作业推送的内置 calculator.sh + 输入副本 basename。"""
    argv = ["bash", "calculator.sh", input_name, job_type]
    if job_type == "xtb":
        argv.extend((xtb_params or XtbParams()).cli_args())
    return argv


def build_remote_runner_script(
    input_name: str,
    job_type: str,
    task_id: int,
    scheduler: dict,
    *,
    xtb_params: XtbParams | None = None,
    workdir: str,
    calculator_cmd: list[str] | None = None,
) -> str:
    """ssh_local 直跑脚本（无 SBATCH 头）。

    刻意不带 ``set -e``：引擎失败也必须写出退出文件——``.cloudra-exit-<id>``
    是 poller 的终态信号，缺它只能按 runner 消失（VANISHED）定性。calculator
    stdout/stderr 统一捕获到 ``.cloudra/calc-<id>.out.log``（拉回后即被
    ``resolve_log_path`` 命中，与本地 guard / Slurm ORCA 捕获同口径）。
    """
    capture = f".cloudra/calc-{task_id}.out.log"
    lines = [
        "#!/bin/bash",
        "set -uo pipefail",
        f"cd {shlex.quote(workdir)}",
        f"echo $$ > {shlex.quote(f'.cloudra-runner-{task_id}.pid')}",
        "mkdir -p .cloudra",
        *scheduler_setup_lines(scheduler),
        f"{shlex.join(calculator_cmd or remote_calculator_argv(input_name, job_type, xtb_params))}"
        f" > {shlex.quote(capture)} 2>&1 &",
        "calc_pid=$!",
        f"echo \"$calc_pid\" > {shlex.quote(f'.cloudra-pid-{task_id}')}",
        "wait $calc_pid",
        "rc=$?",
        f"echo \"$rc\" > {shlex.quote(f'.cloudra-exit-{task_id}')}",
        "",
    ]
    return "\n".join(lines)


def _submit_slurm(transport, remote_dir: str, script_name: str) -> str:
    out = transport.checked(
        f"cd {shlex.quote(remote_dir)} && sbatch --parsable {shlex.quote(script_name)}"
    )
    job_id = out.strip().split(";", 1)[0]
    if not _is_job_id(job_id):
        raise SshError(f"远端 sbatch 返回了无效 job id: {job_id!r}")
    return job_id


def _submit_shell(transport, remote_dir: str, script_name: str, task_id: int) -> str:
    cmd = (
        f"cd {shlex.quote(remote_dir)} && "
        f"nohup bash {shlex.quote(script_name)} "
        f"> {shlex.quote(f'run-{task_id}.log')} 2>&1 < /dev/null & echo $!"
    )
    out = transport.checked(cmd)
    pid = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if not pid.isdigit():
        raise SshError(f"远端 runner 拉起未返回 PID: {out.strip()[:200]!r}")
    return f"{_SHELL_HANDLE_PREFIX}{pid}"


def _query_slurm_state(transport, job_id: str) -> tuple[str, str]:
    out = transport.checked(
        f"sacct --jobs {job_id} --noheader --parsable2 --format=State,ExitCode"
    )
    return parse_sacct_state(out)


def _query_shell_state(
    transport, remote_dir: str, task_id: int, handle: str
) -> tuple[str, str]:
    """远端直跑状态：``(RUNNING|EXIT|VANISHED, exit_code)``。

    退出文件优先于 pid 探活（runner 写完退出文件才退出，顺序无竞态）。
    """
    pid = handle[len(_SHELL_HANDLE_PREFIX):]
    exit_file = shlex.quote(f"{remote_dir}/.cloudra-exit-{task_id}")
    cmd = (
        f"if [ -f {exit_file} ]; then echo EXIT:$(cat {exit_file}); "
        f"elif kill -0 {pid} 2>/dev/null; then echo RUNNING; "
        "else echo VANISHED; fi"
    )
    out = transport.checked(cmd)
    token = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if token.startswith("EXIT:"):
        return "EXIT", token.split(":", 1)[1].strip()
    if token in {"RUNNING", "VANISHED"}:
        return token, ""
    raise SshError(f"远端状态探针返回了无法识别的内容: {token!r}")


def _cancel_remote(transport, kind: str, remote_dir: str, task_id: int, handle: str) -> None:
    """显式取消的远端执行侧（best-effort：账本收口不依赖远端应答）。

    ssh_slurm 走 scancel；ssh_local TERM runner 与其 calculator 子进程
    （pid 文件由 runner 脚本落盘）。只在账本 cancel_requested 后被调用，
    与「任何路径不主动杀未要求取消的计算进程」铁律一致。
    """
    try:
        if kind == "ssh_slurm":
            transport.run(f"scancel {handle}", timeout=30)
        else:
            pid = handle[len(_SHELL_HANDLE_PREFIX):]
            pid_file = shlex.quote(f"{remote_dir}/.cloudra-pid-{task_id}")
            transport.run(
                f"kill -TERM $(cat {pid_file} 2>/dev/null) 2>/dev/null; "
                f"kill -TERM {pid} 2>/dev/null; true",
                timeout=30,
            )
    except SshError:
        logger.warning("remote cancel failed for job %s (%s)", task_id, handle, exc_info=True)


def _row_endpoint(row: dict) -> SshEndpoint:
    return SshEndpoint.from_connection(_scheduler_options(row).get("connection") or {})


def recover_remote_slurm_handle(row: dict) -> str | None:
    """对账用：ssh_slurm 无句柄时按 job-name 从远端 sacct 找回（只认非终态行）。

    传输失败/查不到都返回 None（同本地 ``query_job_by_name`` 口径：找不回就跳过，
    绝不盲重投——sacct 记账有延迟，查不到不等于没提交）。
    """
    try:
        endpoint = _row_endpoint(row)
        rc, out, _stderr = run_remote(
            endpoint,
            f"sacct --name cloudra-{int(row['id'])} --noheader --parsable2 "
            "--format=JobID,State",
            timeout=30,
        )
    except (SshError, TypeError, ValueError, KeyError):
        return None
    if rc != 0:
        return None
    return parse_sacct_job_id(out)


def probe_remote_shell_handle(row: dict) -> str | None:
    """对账用：ssh_local 无句柄时探远端 runner pid 文件。

    返回 ``shell:<pid>``（runner 已起跑）或 None（runner 确认未起跑——pid 文件
    是 runner 脚本的第一条写操作，查不到即可安全重投）。传输失败抛 SshError
    （无法判定，调用方跳过本轮）。
    """
    endpoint = _row_endpoint(row)
    task_id = int(row["id"])
    pid_file = shlex.quote(f"{endpoint.job_dir(task_id)}/.cloudra-runner-{task_id}.pid")
    _rc, out, _stderr = run_remote(endpoint, f"cat {pid_file} 2>/dev/null || true")
    pid = out.strip().splitlines()[-1].strip() if out.strip() else ""
    return f"{_SHELL_HANDLE_PREFIX}{pid}" if pid.isdigit() else None


def _stage_chem_runtime(workdir: Path) -> str:
    """Stage trusted application source; dependencies remain the node runtime's."""
    import hashlib
    import io
    import zipfile
    package = Path(_default_calculator_path()).resolve().parent
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(package.rglob('*.py')):
            if '__pycache__' in source.parts:
                continue
            info = zipfile.ZipInfo(str(Path('cloudra') / source.relative_to(package)))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())
    body = stream.getvalue()
    name = '.cloudra-chem-runtime-' + hashlib.sha256(body).hexdigest() + '.zip'
    target = workdir / name
    if not target.exists():
        target.write_bytes(body)
    elif target.read_bytes() != body:
        raise ValueError('trusted chemistry runtime bundle changed')
    return name


def _stage_and_submit(
    transport,
    kind: str,
    task_id: int,
    input_file: Path,
    workdir: Path,
    remote_dir: str,
    job_type: str,
    row: dict,
    options: dict,
) -> tuple[str, str]:
    """推 stage 并远端提交；返回 ``(句柄, 本地脚本路径)``。"""
    xtb_params = XtbParams.from_row(row) if job_type == "xtb" else None
    calc_argv = remote_calculator_argv(input_file.name, job_type, xtb_params)
    if job_type == "chem_task":
        python = (options.get('environment') or {}).get('CLOUDRA_CHEM_PYTHON')
        if not isinstance(python, str) or not Path(python).is_absolute():
            raise ValueError('remote chem_task requires trusted node environment CLOUDRA_CHEM_PYTHON as an absolute interpreter path')
        transport.checked(shlex.join([python, '-c', 'import pydantic,numpy,rdkit']), timeout=30)
        calc_argv.extend([python, _stage_chem_runtime(workdir)])
    if kind == "ssh_slurm":
        script = build_batch_script(
            input_file,
            job_type,
            task_id,
            options,
            xtb_params=xtb_params,
            calculator_cmd=calc_argv,
            workdir=remote_dir,
        )
        script_name = f".cloudra-slurm-{task_id}.sh"
    else:
        script = build_remote_runner_script(
            input_file.name,
            job_type,
            task_id,
            options,
            xtb_params=xtb_params,
            workdir=remote_dir,
            calculator_cmd=calc_argv,
        )
        script_name = f".cloudra-run-{task_id}.sh"
    script_path = workdir / script_name
    script_path.write_text(script, encoding="utf-8")
    os.chmod(script_path, 0o700)
    transport.push_dir(workdir, remote_dir, excludes=(".cloudra/", ".g16_scratch/"))
    transport.push_files([_default_calculator_path()], remote_dir)
    if kind == "ssh_slurm":
        return _submit_slurm(transport, remote_dir, script_name), str(script_path)
    return _submit_shell(transport, remote_dir, script_name, task_id), str(script_path)


def _terminal_verdict(
    kind: str, state: str, exit_code: str, engine_ok: bool | None, base_error: str | None
) -> tuple[str, str | None]:
    """终态判定：引擎文本闸门是权威（与本地 guard / Slurm COMPLETED 复核同口径）。

    engine_ok=True → done；False → failed。None（没有可判定日志）时回落调度侧
    信号：ssh_slurm 保持 sacct 结论（同本地 slurm 口径），ssh_local 看 runner
    退出码（0 → done；非 0 / runner 消失 → failed）。
    """
    if engine_ok is True:
        return "done", None
    if engine_ok is False:
        if base_error:
            return "failed", base_error
        reason = (
            "engine error termination (Slurm COMPLETED)"
            if kind == "ssh_slurm"
            else "engine error termination"
        )
        return "failed", reason
    if base_error:
        return "failed", base_error
    if kind == "ssh_slurm":
        return "done", None
    if exit_code == "0":
        return "done", None
    return "failed", f"remote runner exit code {exit_code or 'unknown'}"


async def run_remote_compute(
    task_id: int,
    db_path: str,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    transport=None,
) -> int:
    """执行一条已认领的 ssh_local/ssh_slurm 作业；到达终态并落库后返回。"""
    db = ComputeDB.from_path(db_path)
    row = await aget_compute_job(db, task_id)
    if not row:
        raise SshError(f"compute job {task_id} 不存在")
    kind = (row["scheduler"] or "").strip()
    if kind not in REMOTE_KINDS:
        raise SshError(f"compute job {task_id} 不是远端作业: {kind!r}")
    options = _scheduler_options(row)
    endpoint = SshEndpoint.from_connection(options.get("connection") or {})
    transport = transport or SshTransport(endpoint)
    job_type = (row["jobtype"] or "").strip()
    input_file = Path(row["path"]).expanduser()
    remote_dir = endpoint.job_dir(task_id)
    handle = (row["scheduler_job_id"] or "").strip()

    if not handle:
        # 正常认领路径（ready → running 无句柄）与对账安全重投路径
        # （ssh_local 探明远端无 runner）共用：stage 幂等（rsync 覆盖）。
        input_file = input_file.resolve(strict=True)
        workdir = input_file.parent
        handle, script_path = await asyncio.to_thread(
            _stage_and_submit,
            transport,
            kind,
            task_id,
            input_file,
            workdir,
            remote_dir,
            job_type,
            row,
            options,
        )
        await amark_slurm_submitted(db, task_id, handle, script_path)

    workdir = input_file.parent
    poll_seconds = min(max(float(options.get("poll_seconds", 15)), 1), 300)
    last_observed = ""
    empty_after_seen = 0
    pull_failures = 0
    while True:
        current = await aget_compute_job(db, task_id)
        if current and current["state"] in {"cancelled", "cancel_requested"}:
            await asyncio.to_thread(
                _cancel_remote, transport, kind, remote_dir, task_id, handle
            )
            await acancel_compute_job(db, task_id)
            return 1
        try:
            if kind == "ssh_slurm":
                state, exit_code = await asyncio.to_thread(
                    _query_slurm_state, transport, handle
                )
            else:
                state, exit_code = await asyncio.to_thread(
                    _query_shell_state, transport, remote_dir, task_id, handle
                )
        except SshError:
            await sleep(poll_seconds)
            continue

        base_error: str | None = None
        if kind == "ssh_slurm":
            if not state:
                if last_observed:
                    empty_after_seen += 1
                    if empty_after_seen >= 3:
                        await afinalize_compute_job(
                            db,
                            task_id,
                            "failed",
                            last_error="Slurm accounting row vanished after "
                            f"{last_observed}",
                        )
                        return 1
                await sleep(poll_seconds)
                continue
            empty_after_seen = 0
            last_observed = state
            await aupdate_scheduler_state(db, task_id, state)
            if state not in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE:
                await sleep(poll_seconds)
                continue
            if state in SLURM_TERMINAL_FAILURE:
                base_error = f"Slurm {state} ({exit_code})"
        else:
            await aupdate_scheduler_state(
                db, task_id, f"EXIT:{exit_code}" if state == "EXIT" else state
            )
            if state == "RUNNING":
                await sleep(poll_seconds)
                continue
            if state == "VANISHED":
                base_error = (
                    "remote runner vanished before writing its exit file "
                    "(node reboot or SIGKILL)"
                )

        # 终态：拉回全部产物（有界重试），再本地跑引擎文本闸门复核
        try:
            await asyncio.to_thread(transport.pull_dir, remote_dir, str(workdir))
        except SshError as exc:
            pull_failures += 1
            if pull_failures < _MAX_PULL_ATTEMPTS:
                await sleep(poll_seconds)
                continue
            await afinalize_compute_job(
                db,
                task_id,
                "failed",
                last_error=(
                    f"artifact pull-back failed after {_MAX_PULL_ATTEMPTS} "
                    f"attempts: {exc}"
                )[:500],
            )
            return 1
        engine_ok = await asyncio.to_thread(
            _engine_success_from_log, job_type, str(input_file), task_id
        )
        final, last_error = _terminal_verdict(
            kind, state, exit_code, engine_ok, base_error
        )
        wrote = await afinalize_compute_job(db, task_id, final, last_error=last_error)
        if not wrote:
            latest = await aget_compute_job(db, task_id)
            if latest and latest["state"] in {"cancelled", "cancel_requested"}:
                await asyncio.to_thread(
                    _cancel_remote, transport, kind, remote_dir, task_id, handle
                )
                await acancel_compute_job(db, task_id)
                return 1
        # 终态通知由 ComputeNotifyBroker 轮询 compute_jobs 表补投，不再发 IPC
        return 0 if final == "done" else 1
