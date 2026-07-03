import subprocess
import argparse
import sys
import aiosqlite
import json
import asyncio
import time

from cloudra.compute_utils import check_job_type, launch_compute_processes


async def _mark_failed(dbpath: str, task_id: int, message: str):
    """将任务标记为 failed，并打印错误信息。"""
    print(f"Error: {message}")
    async with aiosqlite.connect(dbpath, timeout=10) as con:
        await con.execute(
            "UPDATE compute_jobs SET state=?, end_timestamp=? WHERE id=?",
            ('failed', time.time(), task_id)
        )
        await con.commit()


async def run_compute(task_id: int, dbpath: str):

    # 接收main传来的id，改数据库，发射guard(与任务绑定，传id，路径，conv_id)和calculator.sh(健壮一点，方便以后解耦)两个子进程
    async with aiosqlite.connect(dbpath, timeout=10) as con:
        await con.execute("PRAGMA journal_mode=WAL;")
        await con.execute("PRAGMA busy_timeout=5000;")
        await con.execute("PRAGMA synchronous=NORMAL;")
        
        cur = await con.execute("SELECT conversation_id, path, jobtype FROM compute_jobs WHERE id=?", (task_id,))
        row = await cur.fetchone()
    
    data_dic = {'conversation_id': row[0], 'path': row[1], 'job_type': row[2]}
    workdir = os.path.dirname(data_dic['path'])

    if any(data_dic.get(key, None) is None for key in data_dic):
        await _mark_failed(dbpath, task_id, f"{task_id} 计算任务关键参数不完整")
        return 1

    # 前置依赖检查：避免在缺少计算软件时起空壳进程
    ok, msg = check_job_type(data_dic['job_type'], workdir)
    if not ok:
        await _mark_failed(dbpath, task_id, msg)
        return 1

    # 正常情况下main已经改过state了，这里再确认一次
    try:
        async with aiosqlite.connect(dbpath, timeout=10) as con:
            await con.execute("UPDATE compute_jobs SET state=? WHERE id=?", ("running", task_id))
            await con.commit()
    except Exception as e:
        await _mark_failed(dbpath, task_id, f"更新任务状态失败：{e}")
        return 1

    # 统一启动 guard 和 calculator
    ok, msg = await launch_compute_processes(
        task_id=task_id,
        input_file=data_dic['path'],
        job_type=data_dic['job_type'],
        conv_id=data_dic['conversation_id'],
        db_path=dbpath,
        wait_for_calculator=False,
    )
    if not ok:
        await _mark_failed(dbpath, task_id, msg)
        return 1

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--db_path', type=str, required=True)
    args = parser.parse_args()
    exit_code = asyncio.run(run_compute(args.task_id, args.db_path))
    sys.exit(exit_code)
