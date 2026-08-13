import argparse
import asyncio
import io
import os
import subprocess
import time
from pathlib import Path

from cloudra.infra import events
from cloudra.infra.compute_utils import build_calculator_cmd, check_job_type, get_log_path
from cloudra.infra.platform_utils import is_posix
from cloudra.persistence.context_manager import ContextManager
from cloudra.persistence.database import ConversationDB
from cloudra.persistence.fs_utils import atomic_write_json


async def _parse_log(log_path: Path, parse_timeout: int, job_type: str = "gaussian"):
    """尝试解析日志，返回 (data_dic, is_success) 或 (None, None) 表示超时/失败。

    若 calculator 已退出但日志文件不存在或为空，说明计算未产生有效输出，
    应立即失败而不是空等整个解析窗口。
    """
    if not log_path.exists() or log_path.stat().st_size == 0:
        print(f'日志文件不存在或为空：{log_path}')
        return None, None

    if job_type == "cp2k":
        # cclib 1.8.x 已移除 CP2K 解析器，这里用轻量文本解析兜底。
        return _parse_cp2k_log(log_path)

    # cclib 为重依赖且 CP2K 路径不需要它，惰性导入。
    import cclib

    deadline = time.monotonic() + parse_timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            data = cclib.io.ccread(log_path)
            is_success = data.metadata.get('success', False)
            state_str = cclib.io.ccwrite(data, outputtype="cjson")
            state_CJSON = cclib.io.cjsonreader.CJSON(io.StringIO(state_str))
            data_dic = state_CJSON.parse()
            data_dic.pop('atomcoords', None)
            data_dic['is_success'] = is_success
            return data_dic, is_success
        except Exception as e:
            last_error = e
            await asyncio.sleep(1.0)
    print(f'日志解析失败或超时：{last_error}')
    return None, None


def _parse_cp2k_log(log_path: Path) -> tuple[dict, bool] | None:
    """轻量解析 CP2K 输出日志（.out）。

    成功判据：日志包含 ``PROGRAM ENDED`` 且未出现 ``PROGRAM FAILED`` /
    ``ABORT`` 等终止标记；并提取最后一次 FORCE_EVAL 总能量。
    """
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f'读取 CP2K 日志失败：{e}')
        return None
    if not text.strip():
        return None

    normal = "PROGRAM ENDED" in text
    aborted = any(
        marker in text
        for marker in ("PROGRAM FAILED", "ABORT", "PROGRAM TERMINATED")
    )
    is_success = normal and not aborted

    energy = None
    for line in reversed(text.splitlines()):
        if "ENERGY| Total FORCE_EVAL" in line and "energy [a.u.]" in line:
            tokens = line.split()
            if tokens:
                try:
                    energy = float(tokens[-1])
                except ValueError:
                    pass
            break

    data_dic: dict = {
        "is_success": is_success,
        "total_energy_hartree": energy,
    }
    if energy is not None:
        data_dic["scf_energy_hartree"] = energy
        data_dic["scf_energy_ev"] = energy * 27.211386245988
    return data_dic, is_success


async def run_guard(
    taskid: int,
    path: str,
    conv_id: str,
    parse_timeout: int,
    db_path: str,
    job_type: str = "gaussian",
):
    """
    Guard：calculator 的父进程。

    1. 启动 calculator 子进程并 wait()（事件驱动，不再轮询 mtime）。
    2. calculator 退出后，在 parse_timeout 窗口内尝试解析日志。
    3. 解析成功则写 state.json、更新数据库、注入事件；失败则标记 failed。
    """
    log_path = Path(get_log_path(path, job_type=job_type))
    workdir = os.path.dirname(log_path)
    db = ConversationDB.from_path(db_path)

    ok, msg = check_job_type(job_type, workdir)
    if not ok:
        print(f'[guard] 环境检查失败：{msg}')
        await _mark_failed(db, taskid, msg)
        return

    ok, calculator_cmd, msg = build_calculator_cmd(path, job_type=job_type)
    if not ok:
        print(f'[guard] 无法构建 calculator 命令：{msg}')
        await _mark_failed(db, taskid, msg)
        return

    # 启动 calculator；start_new_session 保证 guard 意外退出时 calculator 不被连带杀死。
    # Windows 不支持 start_new_session，仅 POSIX 传入。
    from cloudra.infra.compute_utils import (
        allocate_gaussian_scratch,
        cleanup_gaussian_scratch,
    )

    calc_env = os.environ.copy()
    scratch_dir = None
    if job_type == "gaussian":
        scratch_dir = allocate_gaussian_scratch(taskid, workdir)
        calc_env["GAUSS_SCRDIR"] = str(scratch_dir)
        print(f'[guard] Gaussian scratch: {scratch_dir}')

    calc_kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "cwd": workdir,
        "env": calc_env,
    }
    if is_posix():
        calc_kwargs["start_new_session"] = True
    try:
        calc_proc = await asyncio.create_subprocess_exec(*calculator_cmd, **calc_kwargs)
        print(f'[guard] calculator 启动 (PID {calc_proc.pid})，等待其结束...')
        returncode = await calc_proc.wait()
        print(f'[guard] calculator 退出，退出码：{returncode}')
    finally:
        # 必须在 g16 退出后再清；运行中删除会制造 FileIO / 假“输入被删”。
        cleanup_gaussian_scratch(scratch_dir)

    data_dic, is_success = await _parse_log(log_path, parse_timeout, job_type=job_type)
    if data_dic is None:
        await _mark_failed(
            db,
            taskid,
            "guard 在解析窗口内无法完成日志解析，请让 Agent 自行读取 state.json 或原始日志确认结果。",
        )
        return

    json_nm = f'state_{taskid}.json'
    json_path = os.path.join(workdir, json_nm)
    try:
        atomic_write_json(json_path, data_dic, indent=4)
    except Exception as e:
        print(f'写入 json 失败：{e}')
        await _mark_failed(db, taskid, f"写入 state json 失败：{e}")
        return

    state = 'done' if is_success else 'failed'
    try:
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE compute_jobs SET state=?, end_timestamp=? WHERE id=?",
                (state, time.time(), taskid)
            )
            await con.commit()
        print(f'[guard] 数据库状态已更新: task_id={taskid}, state={state}')
    except Exception as e:
        print(f'[guard] 更新数据库失败：{e}')
        return

    # 终态事件路由给任务的提交者，而不是一律发给 Coordinator：
    # 子 Agent 提交的任务由子 Agent 自己跟进；查不到时回退 Coordinator。
    info = await _resolve_submission_info(db, taskid)
    submitter = info["agent_id"]

    if state == 'done':
        guidance = "Next: use log_parser on the log to extract energy/frequencies and other results."
    else:
        guidance = (
            "Next: use query_compute_job to inspect last_error, and read the log to locate the failure; "
            "if needed, fix the input file and resubmit with submit_compute_job. "
            "If you cannot resolve it, email the user."
        )
    event_content = (
        f"Compute job task_id={taskid} finished, state={state}.\n"
        f"Input file: {info['path']}\n"
        f"Log file: {log_path}\n"
        f"Structured result: {json_path}\n"
        f"{guidance}"
    )
    # 提交者不是 Coordinator 时，两边都通知：提交者跟进结果（定向到其 session，
    # 避免并行同 agent_id 的兄弟 session 被误唤醒），Coordinator 保有全局视野。
    targets = {submitter: info["session_id"], 'a-0': None}
    for target, target_session in targets.items():
        try:
            await ContextManager.inject_event(
                conversation_id=conv_id,
                agent_id=target,
                event_type='compute_job',
                content=event_content,
                db_path=db_path,
                session_id=target_session,
            )
            print(f'[guard] 已向 {target} 注入计算任务事件: task_id={taskid}')
        except Exception as e:
            print(f'[guard] 注入上下文事件失败 ({target}): {e}')

    # 广播事件，让等待方立即被唤醒
    try:
        events.emit(conv_id, "task_finished", task_id=taskid, task_kind="compute", state=state)
    except Exception:
        pass


async def _resolve_submission_info(db: ConversationDB, taskid: int) -> dict:
    """查询任务的提交信息：{"agent_id", "session_id", "path"}。

    agent_id 查不到（无 session、老任务、表结构差异）时回退 'a-0'，
    保证终态事件至少送达 Coordinator；session_id 用于把事件定向到提交者的
    session，path 是输入文件路径。
    """
    info = {"agent_id": 'a-0', "session_id": None, "path": ""}
    try:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT session_id, path FROM compute_jobs WHERE id=?", (taskid,)
            )
            row = await cur.fetchone()
            if row:
                info["session_id"] = row[0]
                info["path"] = row[1] or ""
            if row and row[0]:
                cur = await con.execute(
                    "SELECT agent_id FROM session WHERE session_id=?", (row[0],)
                )
                agent_row = await cur.fetchone()
                if agent_row and agent_row[0]:
                    info["agent_id"] = agent_row[0]
    except Exception as e:
        print(f'[guard] 查询任务提交者失败（回退 a-0）：{e}')
    return info


async def _resolve_submitter(db: ConversationDB, taskid: int) -> str:
    """查询任务的提交者 agent_id（compute_jobs.session_id → session.agent_id）。

    查不到（无 session、老任务、表结构差异）时回退 'a-0'，保证终态事件
    至少送达 Coordinator。
    """
    return (await _resolve_submission_info(db, taskid))["agent_id"]


async def _mark_failed(db: ConversationDB, taskid: int, message: str):
    """将任务标记为 failed，并打印错误信息。"""
    print(f'Error: {message}')
    try:
        async with db.aconnect() as con:
            await con.execute(
                "UPDATE compute_jobs SET state=?, end_timestamp=? WHERE id=?",
                ('failed', time.time(), taskid)
            )
            await con.commit()
    except Exception as e:
        print(f'[guard] 标记 failed 失败：{e}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--path', type=str, required=True)
    parser.add_argument('--conv_id', type=str, required=True)
    parser.add_argument('--timeout', type=int, required=True)
    parser.add_argument('--db_path', type=str, required=True)
    parser.add_argument('--job_type', type=str, default='gaussian')
    args = parser.parse_args()

    asyncio.run(run_guard(
        taskid=args.task_id,
        path=args.path,
        conv_id=args.conv_id,
        parse_timeout=max(60, args.timeout),
        db_path=args.db_path,
        job_type=args.job_type,
    ))
