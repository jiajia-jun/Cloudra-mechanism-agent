"""计算任务相关的公共工具函数。"""

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cloudra.infra.platform_utils import get_bash_path, is_posix
from cloudra.persistence.database import ComputeDB
from cloudra.services.compute_store import aget_compute_job

# 各 job_type 所需的任一外部可执行程序（通过系统 PATH 查找）。
_REQUIRED_BINS = {
    "gaussian": ["g16", "g09", "g26"],
    "vasp": ["vasp_std", "vasp_gam", "vasp_ncl"],
    "orca": ["orca"],
    "cp2k": ["cp2k.popt", "cp2k.ssmp", "cp2k.psmp", "cp2k"],
}

# guard 轮询间隔（秒）
GUARD_POLL_INTERVAL = 1800


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

    优先查找工作目录下的 calculator.sh，允许用户按任务目录定制；
    找不到时回退到项目内置的 calculator.sh。
    Windows/Android 等没有 shebang 执行语义的环境需要同时找到 bash。

    Returns:
        (is_ok, script_path): is_ok 为 False 时 script_path 为空字符串。
    """
    bash_path = get_bash_path()
    if bash_path is None:
        return False, ""

    local_script = os.path.join(workdir, "calculator.sh")
    if os.access(local_script, os.X_OK):
        return True, local_script

    default_script = _default_calculator_path()
    if os.access(default_script, os.X_OK):
        return True, default_script

    return False, ""


def build_calculator_cmd(input_file: str, job_type: str) -> tuple[bool, list[str], str]:
    """构建 calculator 子进程命令。

    Returns:
        (is_ok, cmd, message): is_ok 为 False 时 cmd 为空列表，message 为错误信息。
    """
    workdir = os.path.dirname(input_file)
    bash_path = get_bash_path()
    ok, script_path = check_calculator_script(workdir)
    if bash_path is None or not ok:
        return False, [], (
            f"calculator.sh or a usable bash was not found; confirm the script is installed and bash is on PATH. "
            f"You may place an executable calculator.sh in the working directory {workdir}, "
            f"or keep the built-in script {_default_calculator_path()}."
        )
    return True, [bash_path, script_path, input_file, job_type], ""


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
    ORCA、CP2K 生成 .out；VASP 的日志命名不固定，默认仍按 .out 处理。
    """
    path = Path(input_file)
    if job_type == "gaussian":
        return str(path.with_suffix(".log"))
    return str(path.with_suffix(".out"))


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
