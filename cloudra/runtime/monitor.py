import argparse
import asyncio
import io
import json
import os
import subprocess
import time
from pathlib import Path

import cclib

from cloudra import events
from cloudra.compute_utils import build_calculator_cmd, check_job_type, get_log_path
from cloudra.context_manager import ContextManager
from cloudra.database import ConversationDB


async def _parse_log(log_path: Path, parse_timeout: int):
    """尝试解析日志，返回 (data_dic, is_success) 或 (None, None) 表示超时/失败。

    若 calculator 已退出但日志文件不存在或为空，说明计算未产生有效输出，
    应立即失败而不是空等整个解析窗口。
    """
    if not log_path.exists() or log_path.stat().st_size == 0:
        print(f'日志文件不存在或为空：{log_path}')
        return None, None

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
    calc_proc = await asyncio.create_subprocess_exec(
        *calculator_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=workdir,
    )
    print(f'[guard] calculator 启动 (PID {calc_proc.pid})，等待其结束...')
    returncode = await calc_proc.wait()
    print(f'[guard] calculator 退出，退出码：{returncode}')

    data_dic, is_success = await _parse_log(log_path, parse_timeout)
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
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data_dic, f, ensure_ascii=False, indent=4)
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

    event_content = (
        f'task_id为{taskid}的任务的state已更新为{state}，请前去监测任务状态！'
        f'若出现问题，请发邮件联系用户。'
    )
    try:
        await ContextManager.inject_event(
            conversation_id=conv_id,
            agent_id='a-0',
            event_type='compute_job',
            content=event_content,
            db_path=db_path,
        )
        print(f'[guard] 已向 Coordinator 注入计算任务事件: task_id={taskid}')
    except Exception as e:
        print(f'[guard] 注入上下文事件失败：{e}')

    # 广播事件，让等待方立即被唤醒
    try:
        events.emit(conv_id, "task_finished", task_id=taskid, task_kind="compute", state=state)
    except Exception:
        pass


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
