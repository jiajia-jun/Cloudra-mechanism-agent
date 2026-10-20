"""远端计算执行器：``ssh_local`` / ``ssh_slurm`` 作业的看守 poller（唯一实现）。

形状对齐 ``infra/slurm.py:run_slurm_compute``：认领进程内 async 轮询即看守，
远端不起 guard。ssh_local 使用随任务发送的独立 Python 3.11+ owner（不安装
cloudra），与本地共享进程归属和取消实现；ssh_slurm 仍只需 bash + 引擎 + rsync。
生命周期：

    stage   rsync 推整棵本地 workdir（VASP 的 INCAR/POSCAR 等邻接文件必须同行；
            排除 .cloudra/ 与 .g16_scratch/ 运行时缓存）+ 单独推内置
            calculator.sh（绝不落进 workdir——compute.allow_local_calculator
            开启时它会被误拾为本地执行入口）；Gaussian/ORCA 只在执行副本中
            重定位原生文件路径，路径映射及原始输入另存本地运行时收据
    submit  ssh_slurm → 远端 sbatch（job-name 锚点 cloudra-<id>）；
            ssh_local → nohup 直跑 runner 脚本，句柄按 ``shell:<pid>`` 落账
    poll    sacct over ssh / 远端退出文件 + pid 探活；scheduler_state 回写账本
    终态    rsync 拉回远端全部产物到隔离收据，再按映射发布无冲突的新产物
            （保留原始输入、依赖和旧产物；有界重试），本地跑
            ``infra/slurm.py:_engine_success_from_log`` 引擎文本闸门复核，
            afinalize_compute_job CAS 落账本

取消只走账本 cancel_requested。ssh_local 的 owner 消费取消请求文件，
终止自己启动的计算家族，写出退出文件后账本才确认取消；ssh_slurm 发出
scancel 后等待调度终态。传输错误按瞬态容忍（下一轮重试）；重启恢复由 scheduler 对账器
调本模块的 recover/probe 函数找回句柄后重挂 poller。
"""

from __future__ import annotations

import asyncio
import filecmp
import hashlib
import json
import logging
import os
import shlex
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

from cloudra.infra.compute_utils import (
    XtbParams,
    _default_calculator_path,
    _gaussian_include_reference,
    _orca_code_mask,
    _orca_file_references,
    _orca_file_tokens,
    _orca_geometry_output_paths,
    get_log_path,
)
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
from cloudra.persistence.fs_utils import atomic_write_text
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
    是 poller 的终态信号，缺它即使 runner 消失也保留在途状态。calculator
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
    ]
    # The same standalone owner as local execution reserves its fresh session.
    # This shell waits for its receipt; it never guesses ownership from a PID.
    lines.extend([
        "python3 .cloudra/calc_lock_wrapper.py "
        f"{shlex.quote(f'.cloudra/calc-{task_id}.lock')} -- "
        f"{shlex.join(calculator_cmd or remote_calculator_argv(input_name, job_type, xtb_params))}"
        f" > {shlex.quote(capture)} 2>&1",
        "rc=$?",
        f"echo \"$rc\" > {shlex.quote(f'.cloudra-exit-{task_id}')}",
        "",
    ])
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
    """Request cancellation; sacct or the owning runner must still confirm exit."""
    try:
        if kind == "ssh_slurm":
            transport.checked(f"scancel {handle}", timeout=30)
        else:
            # The live owner consumes the request and records actual family exit.
            # Repeating a request after an SSH interruption is harmless.
            cancel_file = shlex.quote(f"{remote_dir}/.cloudra/calc-{task_id}.cancel")
            transport.checked(f"touch {cancel_file}", timeout=30)
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


def _same_existing_file(left: Path, right: Path) -> bool:
    return left.is_file() and right.is_file() and left.samefile(right)


def _check_native_receipt_aliases(receipt: Path, workdir: Path) -> None:
    """Execution receipts must own their paths and file bytes before any write."""
    parent = receipt
    while parent != workdir:
        if parent.is_symlink():
            raise ValueError(f'native receipt contains a symlink directory: {parent}')
        parent = parent.parent
    for path in (receipt, *receipt.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'native receipt contains a symlink: {path}')
        if path.is_file() and path.stat().st_nlink > 1:
            raise ValueError(f'native receipt contains a hard-linked file: {path}')


def _stage_native_paths(input_file: Path, workdir: Path, task_id: int, job_type: str) -> Path | None:
    """Build an execution-only input overlay and a durable native path map.

    Native options are copied verbatim. Only declared file destinations and
    dependencies move into the remote job tree; the submitted local input stays
    immutable. The original files and pulled execution copy remain inspectable.
    """
    if job_type not in {'gaussian', 'orca'}:
        return None
    receipt = workdir / '.cloudra' / f'remote-{task_id}'
    _check_native_receipt_aliases(receipt, workdir)
    stage = receipt / 'stage'
    stage.mkdir(parents=True, exist_ok=True)
    original = input_file.read_bytes()
    original_copy = receipt / 'original' / input_file.name
    original_copy.parent.mkdir(parents=True, exist_ok=True)
    if original_copy.exists() and original_copy.read_bytes() != original:
        raise ValueError('submitted native input changed since remote staging')
    original_copy.write_bytes(original)
    text = original.decode('utf-8', errors='surrogateescape')
    files: dict[str, dict] = {}
    geometry_outputs = _orca_geometry_output_paths(str(input_file)) if job_type == 'orca' else set()
    include_paths: set[Path] = set()
    output_paths: set[Path] = set()

    def reject_native_alias(local: Path, role: str) -> None:
        if _same_existing_file(local, input_file):
            raise ValueError('native artifact path aliases the submitted input')
        if not local.is_file() or local.stat().st_nlink < 2:
            return
        if any(_same_existing_file(local, saved) for saved in (workdir / '.cloudra').rglob('*')):
            raise ValueError('native artifact path aliases a runtime receipt file')
        for previous in files.values():
            other = Path(previous['local_path'])
            if local != other and (role == 'dependency' or previous['role'] == 'dependency'):
                if _same_existing_file(local, other):
                    raise ValueError('native file path aliases another native dependency or output')

    def relocate(value: str, role: str, *, directory: bool = False, prefix: bool = False) -> str:
        if not value:
            raise ValueError('empty native file path cannot be staged')
        # Freeze the actual destination before execution, including pre-existing
        # system/user symlinks. Later symlink changes cannot redirect results.
        local = (workdir / value).resolve()
        if local.resolve().is_relative_to((workdir / '.cloudra').resolve()):
            raise ValueError('native file path collides with the runtime receipt directory')
        if local.resolve() == input_file.resolve():
            raise ValueError('native artifact path would overwrite the submitted input')
        reject_native_alias(local, role)
        try:
            relative = local.relative_to(workdir)
        except ValueError:
            digest = hashlib.sha256(str(local).encode()).hexdigest()[:16]
            relative = Path(f'.cloudra-files-{task_id}') / digest / local.name
        if relative.parts and relative.parts[0] == '.cloudra':
            raise ValueError('native file path collides with the runtime receipt directory')
        if relative in {Path('calculator.sh'), Path(f'.cloudra-run-{task_id}.sh'),
                        Path(f'.cloudra-slurm-{task_id}.sh'), Path(f'.cloudra-path-map-{task_id}.json')}:
            raise ValueError('native file path collides with a runtime execution file')
        existing = workdir / relative
        if existing.exists() and existing.resolve() != local:
            raise ValueError('relocated native file path collides with an existing local file')
        if role != 'dependency' and local in include_paths:
            raise ValueError('native output collides with a Gaussian include dependency')
        staged = stage / relative
        if directory:
            staged.mkdir(parents=True, exist_ok=True)
        else:
            staged.parent.mkdir(parents=True, exist_ok=True)
        if role == 'dependency' and not local.is_file():
            raise ValueError(f'native file dependency is missing or not a regular file: {local}')
        if local.exists() and not directory and not prefix:
            if not local.is_file():
                raise ValueError(f'native file path is not a regular file: {local}')
            shutil.copy2(local, staged)
            saved = receipt / 'original-files' / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            if not saved.exists():
                shutil.copy2(local, saved)
        key = str(local)
        previous = files.get(key)
        source_sha256 = None
        if local.is_file() and not prefix:
            with local.open('rb') as stream:
                source_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
        files[key] = {
            'local_path': key,
            'staged_path': relative.as_posix(),
            'role': role if previous is None or previous['role'] == 'dependency' else previous['role'],
            'directory': directory,
            'prefix': prefix,
            'source_sha256': source_sha256,
        }
        if prefix and local.parent.is_dir():
            for child in local.parent.iterdir():
                suffix = child.name[len(local.name):] if child.name.startswith(local.name) else ''
                if not suffix.startswith(('.', '_')) or not child.is_file():
                    continue
                if (child.resolve() == input_file.resolve() or child.suffix.casefold() in {'.out', '.log'}
                        or child.name == 'irc_endpoints.json' or child in geometry_outputs
                        or child.name.endswith(('_IRC_F.xyz', '_IRC_B.xyz', '_IRC_F_trj.xyz', '_IRC_B_trj.xyz',
                                                '_NEB-TS_converged.xyz'))):
                    continue  # Logs and the submitted input are not restart data.
                reject_native_alias(child, 'inout')
                staged_child = staged.with_name(staged.name + suffix)
                shutil.copy2(child, staged_child)
                saved = receipt / 'original-files' / relative.with_name(relative.name + suffix)
                saved.parent.mkdir(parents=True, exist_ok=True)
                if not saved.exists():
                    shutil.copy2(child, saved)
                with child.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                files[str(child)] = {
                    'local_path': str(child), 'staged_path': staged_child.relative_to(stage).as_posix(),
                    'role': 'inout', 'directory': False, 'prefix': False, 'source_sha256': digest,
                }
        return relative.as_posix() + ('/' if directory else '')

    if job_type == 'gaussian':
        in_link0 = True
        produced: set[Path] = set()
        pending_outputs: dict[str, set[Path]] = {}

        def rewrite_gaussian(body: str, active: tuple[Path, ...]) -> str:
            nonlocal in_link0
            lines = []
            for line in body.splitlines(keepends=True):
                stripped = line.lstrip()
                include_reference = _gaussian_include_reference(line)
                if include_reference is not None:
                    path, start, end = include_reference
                    quote = line[start] if line[start] in {'"', "'"} else ''
                    local = (workdir / path).resolve()
                    if local in active:
                        raise ValueError(f'Gaussian include cycle: {local}')
                    if local in output_paths:
                        raise ValueError('Gaussian include dependency collides with a native output')
                    mapped = relocate(path, 'dependency')
                    include_paths.add(local)
                    include = local.read_bytes().decode('utf-8', errors='surrogateescape')
                    rewritten = rewrite_gaussian(include, (*active, local))
                    (stage / mapped).write_bytes(rewritten.encode('utf-8', errors='surrogateescape'))
                    line = line[:start] + quote + mapped + quote + line[end:]
                    lines.append(line)
                    continue
                if stripped.strip().casefold() == '--link1--':
                    for outputs in pending_outputs.values():
                        produced.update(outputs)
                    pending_outputs.clear()
                    in_link0 = True
                elif stripped.startswith('#'):
                    in_link0 = False
                key, separator, value = stripped.partition('=')
                directive = key.strip().casefold()
                roles = {'%chk': 'inout', '%oldchk': 'dependency', '%rwf': 'inout',
                         '%fchk': 'output', '%int': 'inout', '%d2e': 'inout'}
                if in_link0 and separator and directive in roles:
                    bare = value.strip()
                    quote = bare[0] if bare and bare[0] in {'"', "'"} else ''
                    if quote:
                        if not bare.endswith(quote):
                            raise ValueError('unterminated Gaussian file path')
                        bare = bare[1:-1]
                    role = roles[directive]
                    if directive == '%rwf':
                        parts = bare.split(',')
                        outputs = set()
                        for index in range(0, len(parts), 2):
                            path = parts[index].strip()
                            parts[index] = relocate(path, role, directory=path.endswith('/'))
                            output_paths.add((workdir / path).resolve())
                            outputs.add((workdir / path).resolve())
                        pending_outputs[directive] = outputs
                        mapped = ','.join(parts)
                    else:
                        local = (workdir / bare).resolve()
                        # Only preceding Link1 steps can supply a missing input.
                        effective_role = 'inout' if role == 'dependency' and local in produced else role
                        mapped = relocate(bare, effective_role)
                        if role != 'dependency':
                            output_paths.add(local)
                            pending_outputs[directive] = {local}
                    start = len(line) - len(value.lstrip())
                    end = len(line.rstrip())
                    line = line[:start] + quote + mapped + quote + line[end:]
                lines.append(line)
            return ''.join(lines)

        text = rewrite_gaussian(text, (input_file.resolve(),))
    else:
        replacements = []
        code = _orca_code_mask(text)
        boundaries = [start for start, end, value in _orca_file_tokens(text)
                      if value and value.casefold() == '$new_job'
                      and not code[code.rfind('\n', 0, start) + 1:start].strip()
                      and not text[start:end].startswith(('"', "'"))]
        current_job = 0
        current_base = None
        produced_bases: set[Path] = set()
        for keyword, path, start, end in _orca_file_references(text):
            job = sum(boundary < start for boundary in boundaries)
            if job != current_job:
                if current_base is not None:
                    produced_bases.add(current_base)
                current_base = None
                current_job = job
            raw = text[start:end]
            prefix = keyword == '%base'
            local = (workdir / path).resolve()
            generated = any(local.parent == base.parent and local.name.startswith((base.name + '.', base.name + '_'))
                            for base in produced_bases)
            role = 'output' if prefix else 'inout' if generated else 'dependency'
            mapped = relocate(path, role, prefix=prefix)
            if prefix:
                current_base = local
            quote = raw[0] if raw[0] in {'"', "'"} else ''
            if not quote and any(c.isspace() or c in {'#', '=', '\\', '"', "'"} for c in mapped):
                quote = '"'
            if quote == "'" and "'" in mapped:
                quote = '"'
            if quote == '"':
                mapped = mapped.replace('\\', '\\\\').replace('"', '\\"')
            replacements.append((start, end, quote + mapped + quote))
        for start, end, mapped in sorted(replacements, reverse=True):
            text = text[:start] + mapped + text[end:]
    (stage / input_file.name).write_bytes(text.encode('utf-8', errors='surrogateescape'))
    staged_files = {}
    for directory, directories, filenames in os.walk(workdir, followlinks=False):
        directories[:] = [name for name in directories if name not in {'.cloudra', '.g16_scratch'}]
        for name in filenames:
            path = Path(directory) / name
            if path.is_file() and not path.is_symlink():
                with path.open('rb') as stream:
                    staged_files[path.relative_to(workdir).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = {'input_file': str(input_file), 'job_type': job_type,
                'input_sha256': hashlib.sha256(original).hexdigest(),
                'files': list(files.values()), 'staged_files': staged_files}
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'
    (receipt / 'path-map.json').write_text(manifest_text, encoding='utf-8')
    (stage / f'.cloudra-path-map-{task_id}.json').write_text(manifest_text, encoding='utf-8')
    return stage


def _pull_remote_artifacts(transport, remote_dir: str, workdir: Path, input_file: Path, task_id: int,
                           job_type: str | None = None) -> None:
    """Pull to a receipt first, then publish outputs without replacing the input.

    Every downloaded byte stays in results, including the relocated execution
    input. Replaced local artifacts are retained alongside the receipt.
    """
    receipt = workdir / '.cloudra' / f'remote-{task_id}'
    try:
        _check_native_receipt_aliases(receipt, workdir)
    except ValueError as exc:
        raise SshError(str(exc)) from exc
    results = receipt / 'results'
    results.mkdir(parents=True, exist_ok=True)
    transport.pull_dir(remote_dir, str(results))
    manifest_path = receipt / 'path-map.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {'files': []}
    bundled_files = set()
    if (job_type or manifest.get('job_type')) == 'orca':
        from cloudra.tools.core.orca_frames import snapshot_irc_endpoints

        native = results / Path(get_log_path(str(input_file), 'orca')).name
        captured = results / '.cloudra' / f'calc-{task_id}.out.log'
        source = native if native.is_file() and native.stat().st_size else captured
        if source.is_file():
            snapshot_irc_endpoints(str(source), source.parent)
        archive = source.parent / 'irc_endpoints.json'
        if archive.is_file():
            endpoints = json.loads(archive.read_text())['endpoints']
            bundled_files = {(archive.parent / item['filename']).relative_to(results).as_posix()
                             for item in endpoints.values() if item.get('filename')}
    protected = {input_file.resolve()}
    protected.update(Path(item['local_path']).resolve() for item in manifest['files'] if item['role'] == 'dependency')
    protected.update(path.resolve() for directory in (receipt / 'original', receipt / 'original-files')
                     for path in directory.rglob('*') if path.is_file())
    if manifest_path.is_file():
        protected.add(manifest_path.resolve())
    staged_files = manifest.get('staged_files', {})
    baselines = {str(workdir / name): digest for name, digest in staged_files.items()}
    baselines.update({item['local_path']: item['source_sha256'] for item in manifest['files']
                      if not item['directory'] and not item['prefix']})
    protected.update((workdir / name).resolve() for name in staged_files if Path(name).suffix.casefold() in {'.gjf', '.com', '.inp'})

    def publish(source: Path, target: Path) -> None:
        relative = source.relative_to(results)
        if (relative in {Path('irc_endpoints.json'), Path('.cloudra/irc_endpoints.json')}
                or relative.as_posix() in bundled_files):
            return  # Derived receipt metadata is never a native output to publish.
        if target.resolve() in protected or source.is_symlink():
            return
        if target.is_symlink():
            raise SshError(f'artifact conflicts with local symlink; retained in {results}: {target}')
        if any(_same_existing_file(target, source_path) for source_path in protected):
            raise SshError(f'artifact aliases a protected local file through a hard link; retained in {results}: {target}')
        parent = target.parent
        while parent != parent.parent:
            if parent.is_symlink():
                raise SshError(f'artifact conflicts with parent symlink; retained in {results}: {target}')
            parent = parent.parent
        if 'staged_files' in manifest:
            baseline = baselines.get(str(target))
            with source.open('rb') as stream:
                incoming = hashlib.file_digest(stream, 'sha256').hexdigest()
            if incoming == baseline:
                return  # This is an unchanged staged file, not an output.
            current = None
            if target.is_file():
                with target.open('rb') as stream:
                    current = hashlib.file_digest(stream, 'sha256').hexdigest()
            if current != baseline and current != incoming:
                raise SshError(f'local/remote artifact conflict; retained in {results}: {target}')
        if target.exists():
            if target.is_file() and filecmp.cmp(source, target, shallow=False):
                return
            digest = hashlib.sha256(str(target).encode()).hexdigest()
            backup = receipt / 'replaced' / digest / target.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                if target.is_dir():
                    shutil.copytree(target, backup, symlinks=True)
                else:
                    shutil.copy2(target, backup, follow_symlinks=False)
            if target.is_dir():
                raise SshError(f'artifact file conflicts with local directory; retained in {results}: {target}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for source in results.rglob('*'):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(results)
        if (relative in {Path('calculator.sh'), Path('.cloudra/calc_lock_wrapper.py')}
                or relative.parts[0].startswith('.cloudra-files-')
                or relative.parts[:2] == ('.cloudra', f'remote-{task_id}')):
            continue
        publish(source, workdir / relative)
    for item in manifest['files']:
        if item['role'] == 'dependency':
            continue
        source = results / item['staged_path']
        target = Path(item['local_path'])
        if item['directory']:
            for child in source.rglob('*'):
                if child.is_file() and not child.is_symlink():
                    publish(child, target / child.relative_to(source))
        elif item['prefix']:
            for child in source.parent.iterdir():
                if child.name.startswith(source.name) and child.is_file() and not child.is_symlink():
                    publish(child, target.with_name(target.name + child.name[len(source.name):]))
        elif source.is_file() and not source.is_symlink():
            publish(source, target)

    if (job_type or manifest.get('job_type')) in {'gaussian', 'orca'}:
        from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

        engine = job_type or manifest['job_type']
        native = results / Path(get_log_path(str(input_file), engine)).name
        captured = results / '.cloudra' / f'calc-{task_id}.out.log'
        selected = native if native.is_file() and native.stat().st_size else captured
        if selected.is_file():
            write_irc_endpoint_artifacts(selected)


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
    if kind == "ssh_local":
        transport.checked(
            shlex.join(["python3", "-c", "import fcntl,sys; assert sys.version_info >= (3,11), 'ssh_local requires Python 3.11+ for its calculation owner'"]),
            timeout=30,
        )
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
    if script_path == input_file or _same_existing_file(script_path, input_file):
        raise ValueError('runtime execution script would replace the submitted input')
    native_stage = _stage_native_paths(input_file, workdir, task_id, job_type)
    atomic_write_text(str(script_path), script, mode=0o700)
    excludes = ('.cloudra/', '.g16_scratch/')
    if native_stage:
        excludes += (input_file.name, Path(get_log_path(str(input_file), job_type)).name, f'state_{task_id}.json',
                     'irc_endpoints.json')
    if job_type == 'orca':
        excludes += ('*_IRC_F.xyz', '*_IRC_B.xyz', '*_IRC_F_trj.xyz', '*_IRC_B_trj.xyz',
                     '*_im[0-9]*.xyz', '*_NEB-TS_converged.xyz')
    transport.push_dir(workdir, remote_dir, excludes=excludes)
    transport.push_files([_default_calculator_path()], remote_dir)
    if kind == "ssh_local":
        owner_dir = remote_dir + "/.cloudra"
        transport.checked("mkdir -p " + shlex.quote(owner_dir), timeout=30)
        transport.push_files([Path(__file__).with_name("calc_lock_wrapper.py")], owner_dir)
    if native_stage:
        transport.push_dir(native_stage, remote_dir)
    if kind == "ssh_slurm":
        return _submit_slurm(transport, remote_dir, script_name), str(script_path)
    return _submit_shell(transport, remote_dir, script_name, task_id), str(script_path)


def _terminal_verdict(engine_ok: bool | None, base_error: str | None) -> tuple[str, str | None]:
    """A scientific job needs native termination evidence, not a scheduler exit code."""
    if engine_ok is True:
        return "done", None
    if engine_ok is False:
        return "failed", base_error or "engine error termination"
    return "failed", base_error or "native termination log unavailable"


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
    if row["state"] not in {"running", "cancel_requested"}:
        return 0 if row["state"] == "done" else 1
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
        # No handle is not proof that a previous submission never started.
        if row["state"] == "cancel_requested":
            return 1
        # 正常认领路径（ready → running 无句柄）与对账安全重投路径
        # （ssh_local 探明远端无 runner）共用：stage 幂等（rsync 覆盖）。
        # Native relative paths belong to the submitted input directory, just
        # as at admission and in the local calculator. Resolving a file symlink
        # here would silently switch its include/restart dependencies.
        input_file = input_file.absolute()
        await asyncio.to_thread(input_file.stat)
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
        if current and current["state"] not in {"running", "cancel_requested"}:
            return 0 if current["state"] == "done" else 1
        if current and current["state"] == "cancel_requested":
            await asyncio.to_thread(
                _cancel_remote, transport, kind, remote_dir, task_id, handle
            )
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

        latest = await aget_compute_job(db, task_id)
        if latest and latest["state"] == "cancel_requested":
            exited = (state in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE
                      if kind == "ssh_slurm" else state == "EXIT")
            if exited:
                await acancel_compute_job(db, task_id)
                return 1
            # Request acceptance, missing accounting and a vanished runner do not
            # establish child-process exit. Keep the request and capacity pending.
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
            if state in {"RUNNING", "VANISHED"}:
                # A missing observer is not an execution receipt: its engine
                # children may still be alive. Retain capacity until real exit.
                await sleep(poll_seconds)
                continue

        # 终态：拉回全部产物（有界重试），shell 只认退出码，其余引擎复核日志。
        try:
            await asyncio.to_thread(_pull_remote_artifacts, transport, remote_dir, workdir, input_file, task_id, job_type)
        except (SshError, OSError, ValueError) as exc:
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
        if job_type == "shell":
            succeeded = not base_error and exit_code == ("0:0" if kind == "ssh_slurm" else "0")
            final = "done" if succeeded else "failed"
            last_error = None if succeeded else base_error or f"shell exit code {exit_code or 'unknown'}"
        else:
            engine_ok = await asyncio.to_thread(
                _engine_success_from_log, job_type, str(input_file), task_id
            )
            final, last_error = _terminal_verdict(engine_ok, base_error)
        wrote = await afinalize_compute_job(db, task_id, final, last_error=last_error)
        if not wrote:
            latest = await aget_compute_job(db, task_id)
            if latest and latest["state"] in {"cancelled", "cancel_requested"}:
                # The query already confirmed actual execution exit.
                await acancel_compute_job(db, task_id)
                return 1
        # 终态通知由 ComputeNotifyBroker 轮询 compute_jobs 表补投，不再发 IPC
        return 0 if final == "done" else 1
