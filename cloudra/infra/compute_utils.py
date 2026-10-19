"""计算任务相关的公共工具函数。"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from cloudra.infra.platform_utils import get_bash_path, is_posix
from cloudra.persistence.database import ComputeDB
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


def resolve_log_path(input_file: str, job_type: str = "gaussian", task_id: int | None = None) -> str:
    """解析计算作业的真实日志路径——query_compute_job 与完成通知统一走这里（GH #20）。

    预测路径（引擎惯例后缀）常与 guard 实际解析的日志不一致：部分引擎不自写
    日志文件（如本机 ORCA 6.1.1 macOS 构建把主输出全部写 stdout、从不落 .out），
    guard 会把 calculator stdout 捕获到 ``.cloudra/calc-<id>.out.log`` 并回退解析它，
    实际解析路径记录在 guard state json 的 ``log_file`` 字段。
    远端已有本轮 results 收据时只认收据内的原生日志/捕获，不读取旧本地证据。
    本地优先 state json 的真实 log_file；无 state 时 Gaussian 优先非空原生日志，
    其他引擎保留 calc 捕获优先，缺捕获时使用惯例路径。
    """
    if job_type == 'chem_task':
        return input_file
    if input_file and task_id is not None:
        workdir = Path(input_file).parent
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
