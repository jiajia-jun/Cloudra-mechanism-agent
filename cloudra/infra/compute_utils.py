"""计算任务相关的公共工具函数。"""

import asyncio
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from cloudra.infra.platform_utils import get_bash_path, is_posix
from cloudra.persistence.database import ComputeDB
from cloudra.persistence.fs_utils import atomic_write_json
from cloudra.services.compute_store import aget_compute_job

# 各 job_type 所需的任一外部可执行程序（通过系统 PATH 查找）。
_REQUIRED_BINS = {
    "gaussian": ["g16", "g09", "g26"],
    "vasp": ["vasp_std", "vasp_gam", "vasp_ncl"],
    "orca": ["orca"],
    "cp2k": ["cp2k.popt", "cp2k.ssmp", "cp2k.psmp", "cp2k"],
    "xtb": ["xtb"],
    "chem_task": ["python3"],
    "shell": ["bash"],
}

# guard 轮询间隔（秒）
GUARD_POLL_INTERVAL = 1800
ORCA_NEB_GEOMETRY_INPUTS = frozenset({'neb_end_xyzfile', 'neb_ts_xyzfile'})


# ---------------------------------------------------------------------------
# xtb 显式任务参数（charge/multiplicity/task/solvent + cpus 透传）
# ---------------------------------------------------------------------------

# xtb 运行级别枚举：sp=单点（无 flag）、opt=--opt、hess=--hess、ohess=--ohess。
XTB_TASKS = ("sp", "opt", "hess", "ohess")

# 溶剂名字符白名单：合法名字表随 xtb 版本变化（water/h2o/acetonitrile/...），
# 这里只挡 shell/CLI 危险字符；未知名字由 xtb 运行时报错（fail-loud 不降级）。
_XTB_SOLVENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def validate_xtb_params(
    *,
    job_type: str,
    charge: int,
    multiplicity: int,
    task: str,
    solvent: Optional[str],
) -> Optional[str]:
    """校验 xtb 任务参数；合法返回 None，非法返回 fail-loud 错误消息。

    charge/multiplicity/task/solvent 是 xtb 专属参数（xtb 是 CLI 标志驱动，
    .xyz 坐标文件不携带这些语义）：非 xtb 作业带任一非默认值即拒收，
    绝不静默丢弃（job 130 曾把 charge=-1 的输入跑成中性闭壳层"成功"）。
    """
    if job_type != "xtb":
        if charge != 0 or multiplicity != 1 or task != "sp" or solvent:
            return (
                f"charge/multiplicity/task/solvent are xtb-only run parameters; "
                f"job_type={job_type!r} does not accept them. "
                "For other engines declare charge/multiplicity inside the input file."
            )
        return None
    if task not in XTB_TASKS:
        return (
            f"Unsupported xtb task: {task!r}; supported: {', '.join(XTB_TASKS)}. "
            "Fix the task value and resubmit."
        )
    if not isinstance(multiplicity, int) or isinstance(multiplicity, bool) or multiplicity < 1:
        return f"Invalid xtb multiplicity: {multiplicity!r}; must be an integer >= 1."
    if solvent is not None and not _XTB_SOLVENT_RE.fullmatch(solvent):
        return (
            f"Invalid xtb solvent name: {solvent!r}; only [A-Za-z0-9._-] characters "
            "are accepted (mapped to --alpb NAME)."
        )
    return None


@dataclass(frozen=True)
class XtbParams:
    """一条 xtb 作业的显式运行参数；compute_jobs 行是唯一事实来源。

    multiplicity 换算为 xtb 的 --uhf（uhf = multiplicity - 1，即 α−β 电子数）；
    cpus 来自作业的资源申请（req_cpus），映射 --parallel 并钉住 OMP 线程数。
    """

    charge: int = 0
    multiplicity: int = 1
    task: str = "sp"
    solvent: Optional[str] = None
    cpus: int = 1

    @classmethod
    def from_row(cls, row: Optional[Mapping]) -> "XtbParams":
        """从 compute_jobs dict 行构建；行缺失/字段为空时回落显式缺省。"""
        row = row or {}
        return cls(
            charge=int(row.get("charge") or 0),
            multiplicity=int(row.get("multiplicity") or 1),
            task=str(row.get("xtb_task") or "sp"),
            solvent=row.get("xtb_solvent") or None,
            cpus=int(row.get("req_cpus") or 1),
        )

    def cli_args(self) -> list[str]:
        """calculator.sh 的透传参数（--task 由 calculator.sh 翻译成运行级别 flag）。"""
        args = [
            "--chrg", str(self.charge),
            "--uhf", str(self.multiplicity - 1),
            "--task", self.task,
            "--parallel", str(self.cpus),
        ]
        if self.solvent:
            args += ["--alpb", self.solvent]
        return args


def cloudra_run_dir(workdir: str) -> Path:
    """作业运行时目录（flock 锁文件、guard 日志），确保存在。"""
    run_dir = Path(workdir) / ".cloudra"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def guard_lock_path(workdir: str, task_id: int) -> str:
    return str(cloudra_run_dir(workdir) / f"guard-{task_id}.lock")


def calc_lock_path(workdir: str, task_id: int) -> str:
    return str(cloudra_run_dir(workdir) / f"calc-{task_id}.lock")


def guard_log_path(workdir: str, task_id: int) -> str:
    return str(cloudra_run_dir(workdir) / f"guard-{task_id}.log")


def _default_calculator_path() -> str:
    """返回项目内置的 calculator.sh 绝对路径。"""
    return str(Path(__file__).resolve().parents[1] / "calculator.sh")


def check_job_type(job_type: str, workdir: str) -> tuple[bool, str]:
    """检查系统 PATH 中是否具备执行指定 job_type 所需的任一外部程序。

    Args:
        job_type: 计算任务类型
        workdir: 计算任务的工作目录（仅用于错误信息）

    Returns:
        (is_ok, message): is_ok 为 True 表示环境可用；否则 message 为可读错误信息。
    """
    bins = _REQUIRED_BINS.get(job_type)
    if bins is None:
        return False, f"Unsupported job_type: {job_type}"
    found = [b for b in bins if shutil.which(b)]
    if found:
        return True, ""

    return False, (
        f"PATH is missing the programs required for {job_type} compute; "
        f"install and ensure one of these commands is available: {', '.join(bins)}"
    )


def check_calculator_script(workdir: str) -> tuple[bool, str]:
    """检查 calculator.sh 是否可用。

    工作目录下的 calculator.sh（按任务目录定制）只在
    ``compute.allow_local_calculator`` 显式开启时生效——工作目录是 agent
    可写区，默认忽略可防止 agent 放置的同名脚本被提升为计算执行入口；
    默认直接使用项目内置的 calculator.sh。
    Windows/Android 等没有 shebang 执行语义的环境需要同时找到 bash。

    Returns:
        (is_ok, script_path): is_ok 为 False 时 script_path 为空字符串。
    """
    from cloudra.infra.config import get_config

    bash_path = get_bash_path()
    if bash_path is None:
        return False, ""

    if get_config().compute.allow_local_calculator:
        local_script = os.path.join(workdir, "calculator.sh")
        if os.access(local_script, os.X_OK):
            return True, local_script

    default_script = _default_calculator_path()
    if os.access(default_script, os.X_OK):
        return True, default_script

    return False, ""


def build_calculator_cmd(
    input_file: str,
    job_type: str,
    *,
    xtb_params: Optional[XtbParams] = None,
) -> tuple[bool, list[str], str]:
    """构建 calculator 子进程命令。

    xtb 作业必须带 ``xtb_params``（compute_jobs 行是唯一事实来源），其
    cli_args() 追加在 job_type 之后由 calculator.sh 翻译成 xtb CLI flag。

    Returns:
        (is_ok, cmd, message): is_ok 为 False 时 cmd 为空列表，message 为错误信息。
    """
    workdir = os.path.dirname(input_file)
    bash_path = get_bash_path()
    ok, script_path = check_calculator_script(workdir)
    if bash_path is None or not ok:
        return False, [], (
            f"calculator.sh or a usable bash was not found; confirm the script is installed and bash is on PATH. "
            f"The built-in script is {_default_calculator_path()}; a custom calculator.sh in the working "
            f"directory {workdir} is only honored when compute.allow_local_calculator is enabled."
        )
    cmd = [bash_path, script_path, input_file, job_type]
    if job_type == "xtb":
        cmd.extend((xtb_params or XtbParams()).cli_args())
    elif job_type == "chem_task":
        cmd.extend([sys.executable, str(Path(__file__).resolve().parents[2])])
    return True, cmd, ""


def build_guard_cmd(
    task_id: int,
    input_file: str,
    conv_id: str,
    db_path: str,
    poll_interval: int = GUARD_POLL_INTERVAL,
    job_type: str = "gaussian",
    adopt: bool = False,
) -> list[str]:
    """构建 guard 子进程命令（adopt=True 时构建对账接管用的 adopt guard）。"""
    cmd = [
        sys.executable,
        "-m",
        "cloudra.runtime.monitor",
        "--path",
        input_file,
        "--timeout",
        str(poll_interval),
        "--conv_id",
        conv_id,
        "--task_id",
        str(task_id),
        "--db_path",
        db_path,
        "--job_type",
        job_type,
    ]
    if adopt:
        cmd.append("--adopt")
    return cmd


def spawn_detached(cmd: list[str], log_path: str) -> None:
    """detach 拉起子进程（POSIX start_new_session），stdout/stderr 追加到 log_path。

    调用方（守护进程/对账器）退出不影响子进程；日志落盘替代过去的 DEVNULL，
    保证调度层故障可事后取证。
    """
    log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        popen_kwargs: dict = {
            "stdout": log_fd,
            "stderr": log_fd,
            "stdin": subprocess.DEVNULL,
        }
        if is_posix():
            popen_kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **popen_kwargs)
    finally:
        os.close(log_fd)


async def launch_compute_processes(
    task_id: int,
    input_file: str,
    job_type: str,
    conv_id: str,
    db_path: str,
    *,
    wait_for_calculator: bool = False,
    poll_interval: int = GUARD_POLL_INTERVAL,
) -> tuple[bool, str]:
    """启动 guard 子进程（guard 内部会启动并等待 calculator，不再由调用方轮询）。

    Args:
        task_id: 计算任务在 compute_jobs 表中的 ID
        input_file: 输入文件绝对路径
        job_type: 计算任务类型
        conv_id: 所属 conversation_id
        db_path: 数据库路径
        wait_for_calculator: 是否在当前协程中等待 guard（含 calculator）结束
        poll_interval: 作为 guard 的日志解析超时窗口（至少 60s）

    Returns:
        (is_ok, message): is_ok 为 True 表示子进程已正常启动/完成；
                         为 False 时 message 为错误信息。
    """
    guard_cmd = build_guard_cmd(
        task_id, input_file, conv_id, db_path, poll_interval, job_type=job_type
    )
    workdir = os.path.dirname(input_file)
    log_path = guard_log_path(workdir, task_id)

    try:
        if wait_for_calculator:
            # 同步阻塞模式：等待 guard 完成任务（事件驱动 waitpid）；输出落盘可取证
            log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                guard_proc = await asyncio.create_subprocess_exec(
                    *guard_cmd,
                    stdout=log_fd,
                    stderr=log_fd,
                    stdin=subprocess.DEVNULL,
                )
                await guard_proc.wait()
            finally:
                os.close(log_fd)

            db = ComputeDB.from_path(db_path)
            row = await aget_compute_job(db, task_id)
            final_state = row["state"] if row else None
            if final_state == "done":
                return True, ""
            if final_state == "failed":
                return (
                    False,
                    f"task_id={task_id} compute job failed, or guard could not finish parsing within the window; "
                    f"have the agent read state_{task_id}.json or the raw log to confirm the result.",
                )
            return (
                False,
                f"task_id={task_id} guard exited abnormally without writing a terminal state; check the logs.",
            )

        # 异步后台模式：guard 与 calculator 脱离当前进程会话，独立运行；
        # guard 输出落盘 .cloudra/guard-<id>.log（替代 DEVNULL，故障可取证）。
        spawn_detached(guard_cmd, log_path)
        return True, ""
    except Exception as e:
        return False, f"Failed to start compute subprocess: {e}"


def get_log_path(input_file: str, job_type: str = "gaussian") -> str:
    """根据输入文件路径推导计算软件生成的日志文件路径。

    Gaussian 默认生成与输入文件同名但后缀为 .log 的文件；
    ORCA、CP2K 生成 .out；xtb 主输出由 calculator.sh 重定向到 .out；
    VASP 的日志命名不固定，默认仍按 .out 处理。
    """
    path = Path(input_file)
    if job_type == "chem_task":
        return input_file
    if job_type == "gaussian":
        return str(path.with_suffix(".log"))
    return str(path.with_suffix(".out"))


def _execution_receipt(input_file: str, task_id: int) -> Path:
    return Path(input_file).parent / '.cloudra' / f'execution-{task_id}'


class _OrcaTokenSource(io.StringIO):
    comment_start: int | None = None

    def readline(self, size: int = -1) -> str:
        # shlex consumes the rest of a comment through readline().
        self.comment_start = self.tell() - 1
        return super().readline(size)


def _orca_file_tokens(text: str) -> list[tuple[int, int, str | None]]:
    """Use native shlex rules while retaining each token's original span."""
    tokens = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stream = _OrcaTokenSource(line)
        lexer = shlex.shlex(stream, posix=True, punctuation_chars='=')
        lexer.whitespace_split = True
        lexer.commenters = '#'
        while True:
            # shlex buffers punctuation lookahead outside its input stream.
            start = stream.tell() - len(lexer._pushback_chars)
            while start < len(line) and line[start].isspace():
                start += 1
            stream.comment_start = None
            try:
                value = lexer.get_token()
            except ValueError:
                # Unrelated malformed options remain the engine's input. A
                # file directive consuming this token is diagnosed below.
                tokens.append((offset + start, offset + len(line.rstrip('\r\n')), None))
                break
            if value is None:
                break
            end = (stream.comment_start if stream.comment_start is not None
                   else stream.tell() - len(lexer._pushback_chars))
            if (stream.comment_start is None and lexer.state == ' '
                    and end > start and line[end - 1].isspace()):
                end -= 1
            tokens.append((offset + start, offset + end, value))
        offset += len(line)
    return tokens


def _orca_file_references(text: str) -> list[tuple[str, str, int, int]]:
    """Return native file directives and their decoded paths/original spans."""
    tokens = _orca_file_tokens(text)
    references = []
    consumed = set()
    block = ''
    for index, (token_start, token_end, value) in enumerate(tokens):
        if index in consumed or value is None or text[token_start:token_end].startswith(('"', "'")):
            continue
        keyword = value.casefold()
        line_start = text.rfind('\n', 0, token_start) + 1
        starts_line = not text[line_start:token_start].strip()
        starts_statement = starts_line or (
            index > 0 and (tokens[index - 1][2] or '').casefold() == 'end'
            and not text[tokens[index - 1][0]:tokens[index - 1][1]].startswith(('"', "'")))
        if keyword.startswith('%') and starts_statement:
            block = keyword[1:]
        elif keyword == 'end' or (starts_line and keyword.startswith(('!', '*'))):
            block = ''
        target_index = None
        if keyword in {'%base', '%moinp', '%pointcharges'} and starts_statement:
            target_index = index + 1
        elif keyword in {'hess_filename', 'inhessname'} and block in {'irc', 'geom'}:
            target_index = index + 1
        elif keyword in ORCA_NEB_GEOMETRY_INPUTS and block == 'neb':
            target_index = index + 1
        elif (keyword == '*xyzfile' and starts_line) or (
                keyword == 'xyzfile' and index > 0 and tokens[index - 1][2] == '*'):
            keyword, target_index = 'xyzfile', index + 3
        if target_index is None:
            continue
        if target_index < len(tokens) and tokens[target_index][2] == '=':
            target_index += 1
        if target_index >= len(tokens):
            raise ValueError(f'native {value} file path is missing')
        start, end, path = tokens[target_index]
        if path is None:
            raise ValueError(f'unterminated native file path for {value}')
        consumed.add(target_index)
        references.append((keyword, path, start, end))
    return references


def _orca_geometry_output_paths(input_file: str, *, protect_dependencies: bool = True) -> set[Path]:
    """Known native IRC outputs for the input stem and explicit %base prefixes."""
    source = Path(input_file)
    prefixes = {source.with_suffix('')}
    dependencies = set()
    text = source.read_text(encoding='utf-8', errors='replace') if source.is_file() else ''
    for keyword, value, _start, _end in _orca_file_references(text):
        if keyword == '%base':
            prefixes.add((source.parent / value).resolve())
        elif keyword in ORCA_NEB_GEOMETRY_INPUTS or keyword == 'xyzfile':
            dependencies.add((source.parent / value).resolve())
    outputs = {prefix.with_name(prefix.name + suffix)
               for prefix in prefixes for suffix in ('_IRC_F.xyz', '_IRC_B.xyz', '_IRC_F_trj.xyz', '_IRC_B_trj.xyz', '_NEB-TS_converged.xyz')}
    for prefix in prefixes:
        if not prefix.parent.is_dir():
            continue
        for child in prefix.parent.iterdir():
            lead = prefix.name + '_im'
            if child.name.startswith(lead) and child.suffix == '.xyz' and child.name[len(lead):-4].isdigit():
                outputs.add(child)
    if protect_dependencies and any(output.resolve() in dependencies for output in outputs if output.exists()):
        raise ValueError('native IRC output overlaps an explicit XYZ input dependency')
    return outputs


def prepare_execution_evidence(input_file: str, job_type: str, task_id: int, db: ComputeDB) -> None:
    """Archive prior native output before launch; never infer ownership from mtime.

    The old bytes stay in previous/. A new file at the conventional path is then
    unambiguously this execution, even when its contents equal the previous run.
    A recovered guard reuses the receipt instead of archiving current output.
    """
    if job_type not in {'gaussian', 'orca'}:
        return
    from cloudra.infra.flocks import is_lock_held, locked

    native = Path(get_log_path(input_file, job_type))
    receipt = _execution_receipt(input_file, task_id)
    receipt.mkdir(parents=True, exist_ok=True)
    if native.resolve() == Path(input_file).resolve():
        raise ValueError('native output path is the submitted input; refusing to archive the input')
    # One short local preparation lock also covers distinct inputs sharing an
    # explicit external %base. Engine execution never holds this coordination lock.
    output_lock = Path(db.path).with_suffix('.native-evidence.lock')
    with locked(str(output_lock)):
        metadata = receipt / 'evidence.json'
        if metadata.exists():
            return
        sidecars = _orca_geometry_output_paths(input_file) if job_type == 'orca' else set()
        own_outputs = {path.resolve() for path in sidecars}
        with db.connect() as con:
            rows = con.execute('SELECT id,path,jobtype,state,scheduler,scheduler_job_id FROM compute_jobs WHERE id!=?',
                               (task_id,)).fetchall()
        previous_jobs = []
        for other, path, engine, state, scheduler, handle in rows:
            if not path or engine not in {'gaussian', 'orca'}:
                continue
            shared_output = Path(get_log_path(path, engine)).resolve() == native.resolve()
            workdir = str(Path(path).parent)
            active_owner = state in {'running', 'cancel_requested'} and (
                (Path(workdir).is_dir() and (is_lock_held(calc_lock_path(workdir, other))
                                           or is_lock_held(guard_lock_path(workdir, other))))
                or (_execution_receipt(path, other) / 'evidence.json').is_file()
                or (scheduler != 'local' and handle))
            if not shared_output and active_owner and engine == 'orca' and own_outputs:
                other_outputs = _orca_geometry_output_paths(path, protect_dependencies=False)
                shared_output = bool(own_outputs & {item.resolve() for item in other_outputs})
            if not shared_output:
                continue
            if state in {'running', 'cancel_requested'}:
                if active_owner:
                    raise ValueError(f'native output is owned by active compute job {other}: {native}')
            elif state in {'done', 'failed', 'cancelled'}:
                previous_jobs.append((other, path, engine))
        if native.is_symlink() or (native.exists() and not native.is_file()):
            raise ValueError(f'native output must be a regular file before execution: {native}')
        # Older completed rows may still point at the conventional path. Freeze
        # that evidence before relocating it, so their queries keep the old bytes.
        for other, path, engine in previous_jobs:
            if Path(resolve_log_path(path, engine, other)) == native:
                selected = complete_execution_evidence(path, engine, other)
                state_path = Path(path).parent / f'state_{other}.json'
                if state_path.is_file():
                    state_record = json.loads(state_path.read_text())
                    state_record['log_file'] = selected
                    atomic_write_json(state_path, state_record)
        previous = receipt / 'previous' / native.name
        previous.parent.mkdir(parents=True, exist_ok=True)
        if native.exists():
            native.rename(previous)
        if job_type == 'orca':
            for sidecar in sidecars:
                if not sidecar.is_file():
                    continue
                # Keep external %base outputs distinct without changing their bytes.
                name = sidecar.name if sidecar.parent == native.parent else hashlib.sha256(str(sidecar).encode()).hexdigest()[:16] + '_' + sidecar.name
                shutil.move(str(sidecar), str(previous.parent / name))
        atomic_write_json(metadata, {'input_file': input_file, 'job_type': job_type,
                                     'previous_log': str(previous) if previous.exists() else None,
                                     'geometry_stems': sorted({path.name.removesuffix('_IRC_F.xyz')
                                                               for path in sidecars if path.name.endswith('_IRC_F.xyz')})})


def complete_execution_evidence(input_file: str, job_type: str, task_id: int) -> str:
    """Freeze this execution's selected log and its native IRC endpoint bundle."""
    if job_type not in {'gaussian', 'orca'}:
        return resolve_log_path(input_file, job_type, task_id)
    from cloudra.tools.core.irc_endpoint_artifacts import write_irc_endpoint_artifacts

    receipt = _execution_receipt(input_file, task_id)
    metadata = receipt / 'evidence.json'
    record = json.loads(metadata.read_text()) if metadata.exists() else {}
    if record.get('log_file'):
        write_irc_endpoint_artifacts(record['log_file'])
        return record['log_file']
    native = Path(get_log_path(input_file, job_type))
    captured = Path(input_file).parent / '.cloudra' / f'calc-{task_id}.out.log'
    source = native if native.is_file() and native.stat().st_size else captured
    results = receipt / 'results'
    results.mkdir(parents=True, exist_ok=True)
    target = results / source.name
    if source.is_file():
        shutil.copy2(source, target)
        if job_type == 'orca':
            geometries = _orca_geometry_output_paths(input_file)
            record.update(input_file=input_file, job_type=job_type,
                          geometry_stems=sorted({path.name.removesuffix('_IRC_F.xyz') for path in geometries
                                                 if path.name.endswith('_IRC_F.xyz')}))
            atomic_write_json(metadata, record)
            for geometry in geometries:
                if geometry.is_file():
                    shutil.copy2(geometry, results / geometry.name)
            from cloudra.tools.core.orca_frames import snapshot_irc_endpoints

            snapshot_irc_endpoints(str(target), results)
        write_irc_endpoint_artifacts(target)
    record['log_file'] = str(target)
    atomic_write_json(metadata, record)
    return str(target)


def resolve_log_path(input_file: str, job_type: str = "gaussian", task_id: int | None = None) -> str:
    """解析计算作业的真实日志路径——query_compute_job 与完成通知统一走这里（GH #20）。

    预测路径（引擎惯例后缀）常与 guard 实际解析的日志不一致：部分引擎不自写
    日志文件（如本机 ORCA 6.1.1 macOS 构建把主输出全部写 stdout、从不落 .out），
    guard 会把 calculator stdout 捕获到 ``.cloudra/calc-<id>.out.log`` 并回退解析它，
    实际解析路径记录在 guard state json 的 ``log_file`` 字段。
    远端已有本轮 results 收据时只认收据内的原生日志/捕获，不读取旧本地证据。
    有执行收据时只认其冻结日志；尚未收尾时返回本次 capture。
    没有执行收据的已有记录仍可由其 state json 定位原来的日志。
    """
    if job_type == 'chem_task':
        return input_file
    if input_file and task_id is not None:
        workdir = Path(input_file).parent
        receipt = _execution_receipt(input_file, task_id)
        try:
            evidence = json.loads((receipt / 'evidence.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            evidence = None
        if evidence is not None or receipt.is_dir():
            # An execution receipt never falls back to a later shared output.
            if (evidence or {}).get('log_file'):
                return evidence['log_file']
            native = Path(get_log_path(input_file, job_type))
            if evidence is not None and native.is_file() and native.stat().st_size:
                return str(native)
            return str(workdir / '.cloudra' / f'calc-{task_id}.out.log')
        remote_results = workdir / '.cloudra' / f'remote-{task_id}' / 'results'
        if remote_results.is_dir():
            # A remote execution receipt must never fall back to evidence left
            # by a previous local/remote run in the shared input directory.
            native = remote_results / Path(get_log_path(input_file, job_type)).name
            if native.is_file() and native.stat().st_size:
                return str(native)
            captured = remote_results / '.cloudra' / f'calc-{task_id}.out.log'
            if captured.is_file():
                return str(captured)
            return str(native)
        try:
            recorded = json.loads(
                (workdir / f"state_{task_id}.json").read_text(encoding="utf-8")
            ).get("log_file")
        except (OSError, ValueError):
            recorded = None
        if recorded and Path(recorded).is_file():
            return str(recorded)
        native = Path(get_log_path(input_file, job_type=job_type))
        if job_type == 'gaussian' and native.is_file() and native.stat().st_size:
            return str(native)
        captured = workdir / ".cloudra" / f"calc-{task_id}.out.log"
        if captured.is_file():
            return str(captured)
    return get_log_path(input_file, job_type=job_type)


def allocate_gaussian_scratch(task_id: int, workdir: str) -> Path:
    """为单个 Gaussian 任务分配独占的 GAUSS_SCRDIR。

    并行本地任务共用全局 SCRDIR 时，g16 Link0 写入的 ``Gau-$PID.*`` 会互相覆盖，
    典型症状是日志在打印 Route/坐标前就 FileIO 退出。子目录在任务结束后由
    :func:`cleanup_gaussian_scratch` 删除——运行期间不得清理。
    """
    base = os.environ.get("GAUSS_SCRDIR") or os.path.join(workdir, ".g16_scratch")
    scratch = Path(base) / f"cloudra_g16_task{task_id}_{os.getpid()}"
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


def cleanup_gaussian_scratch(scratch: Path | str | None) -> None:
    """删除 :func:`allocate_gaussian_scratch` 创建的任务级 scratch（忽略错误）。"""
    if not scratch:
        return
    path = Path(scratch)
    # 只删 cloudra_g16_* 叶子，避免误删用户全局 GAUSS_SCRDIR
    if not path.name.startswith("cloudra_g16_"):
        return
    shutil.rmtree(path, ignore_errors=True)
