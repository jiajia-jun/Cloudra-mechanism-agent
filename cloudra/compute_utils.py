"""计算任务相关的公共工具函数。"""

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cloudra.database import ConversationDB
from cloudra.platform_utils import get_bash_path, is_posix

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
            f"未找到 calculator.sh 或可用的 bash，请确认脚本已安装且 bash 在 PATH 中。"
            f"可以在工作目录 {workdir} 下放一个可执行的 calculator.sh，"
            f"或者保留项目内置脚本 { _default_calculator_path() }。"
        )
    return True, [bash_path, script_path, input_file, job_type], ""


def build_guard_cmd(
    task_id: int,
    input_file: str,
    conv_id: str,
    db_path: str,
    poll_interval: int = GUARD_POLL_INTERVAL,
    job_type: str = "gaussian",
) -> list[str]:
    """构建 guard 子进程命令。"""
    return [
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
    guard_cmd = build_guard_cmd(task_id, input_file, conv_id, db_path, poll_interval)

    try:
        if wait_for_calculator:
            # 同步阻塞模式：等待 guard 完成任务（事件驱动 waitpid）
            guard_proc = await asyncio.create_subprocess_exec(*guard_cmd)
            await guard_proc.wait()

            db = ConversationDB.from_path(db_path)
            async with db.aconnect() as con:
                cur = await con.execute(
                    "SELECT state FROM compute_jobs WHERE id=?", (task_id,)
                )
                row = await cur.fetchone()
            final_state = row[0] if row else None
            if final_state == "done":
                return True, ""
            if final_state == "failed":
                return (
                    False,
                    f"task_id={task_id} 计算任务失败或 guard 未能在解析窗口内完成解析，"
                    f"请让 Agent 自行读取 state_{task_id}.json 或原始日志确认结果。",
                )
            return (
                False,
                f"task_id={task_id} guard 异常退出且未落库终态，请检查日志。",
            )

        # 异步后台模式：guard 与 calculator 脱离当前进程会话，独立运行。
        popen_kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if is_posix():
            popen_kwargs["start_new_session"] = True
        subprocess.Popen(guard_cmd, **popen_kwargs)
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
