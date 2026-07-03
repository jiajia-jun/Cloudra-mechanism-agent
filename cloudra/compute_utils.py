"""计算任务相关的公共工具函数。"""

import os
import shutil
import sys
import asyncio
from pathlib import Path
from typing import Optional

# 各 job_type 所需的任一外部可执行程序（通过系统 PATH 查找）。
_REQUIRED_BINS = {
    "gaussian": ["g16", "g09", "g26"],
    "vasp": ["vasp_std", "vasp_gam", "vasp_ncl"],
    "orca": ["orca"],
}

# guard 轮询间隔（秒）
GUARD_POLL_INTERVAL = 1800


def _default_calculator_path() -> str:
    """返回项目内置的 calculator.sh 绝对路径。"""
    return str(Path(__file__).parent / "calculator.sh")


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
        return False, f"不支持的 job_type: {job_type}"
    found = [b for b in bins if shutil.which(b)]
    if found:
        return True, ""

    return False, (
        f"系统 PATH 中缺少 {job_type} 计算所需的程序，"
        f"请安装并确保以下任一命令可用: {', '.join(bins)}"
    )


def check_calculator_script(workdir: str) -> tuple[bool, str]:
    """检查 calculator.sh 是否可用。

    优先查找工作目录下的 calculator.sh，允许用户按任务目录定制；
    找不到时回退到项目内置的 calculator.sh。

    Returns:
        (is_ok, script_path): is_ok 为 False 时 script_path 为空字符串。
    """
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
    ok, script_path = check_calculator_script(workdir)
    if not ok:
        return False, [], (
            f"未找到 calculator.sh，请确认该脚本已安装。"
            f"可以在工作目录 {workdir} 下放一个可执行的 calculator.sh，"
            f"或者保留项目内置脚本 { _default_calculator_path() }。"
        )
    return True, [script_path, input_file, job_type], ""


def build_guard_cmd(
    task_id: int,
    input_file: str,
    conv_id: str,
    db_path: str,
    poll_interval: int = GUARD_POLL_INTERVAL,
) -> list[str]:
    """构建 guard 子进程命令。"""
    return [
        sys.executable,
        "-m",
        "cloudra.guard",
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
    ]


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
    """统一启动 guard 和 calculator 子进程。

    Args:
        task_id: 计算任务在 compute_jobs 表中的 ID
        input_file: 输入文件绝对路径
        job_type: 计算任务类型
        conv_id: 所属 conversation_id
        db_path: 数据库路径
        wait_for_calculator: 是否在当前协程中等待 calculator 结束
        poll_interval: guard 轮询间隔

    Returns:
        (is_ok, message): is_ok 为 True 表示子进程已正常启动/完成；
                         为 False 时 message 为错误信息。
    """
    ok, calculator_cmd, msg = build_calculator_cmd(input_file, job_type)
    if not ok:
        return False, msg

    guard_cmd = build_guard_cmd(task_id, input_file, conv_id, db_path, poll_interval)

    try:
        # 先启动 guard，再启动 calculator
        guard_proc = await asyncio.create_subprocess_exec(*guard_cmd)

        # 短暂等待，检查 guard 是否瞬间崩溃
        await asyncio.sleep(0.3)
        if guard_proc.returncode is not None:
            return False, f"guard 进程启动失败，退出码: {guard_proc.returncode}"

        if wait_for_calculator:
            # 同步阻塞模式：等待 calculator 结束
            calc_proc = await asyncio.create_subprocess_exec(*calculator_cmd)
            returncode = await calc_proc.wait()

            # 给 guard 一段短暂的解析窗口（最多 10 秒）
            if guard_proc.returncode is None:
                try:
                    await asyncio.wait_for(guard_proc.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    pass

            # 确保 guard 不会成为僵尸/常驻进程
            if guard_proc.returncode is None:
                guard_proc.kill()
                await guard_proc.wait()

            if returncode != 0:
                return False, f"calculator 返回非零退出码: {returncode}"
            return True, ""
        else:
            # 异步后台模式：用 Popen + start_new_session 彻底脱离父进程，
            # 确保 compute_executor 退出后计算任务仍在运行。
            subprocess.Popen(
                calculator_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, ""
    except Exception as e:
        return False, f"启动计算子进程失败: {e}"


def get_log_path(input_file: str, job_type: str = "gaussian") -> str:
    """根据输入文件路径推导计算软件生成的日志文件路径。

    Gaussian 默认生成与输入文件同名但后缀为 .log 的文件；
    ORCA 生成 .out；VASP 的日志命名不固定，默认仍按 .out 处理。
    """
    path = Path(input_file)
    if job_type == "gaussian":
        return str(path.with_suffix(".log"))
    return str(path.with_suffix(".out"))
