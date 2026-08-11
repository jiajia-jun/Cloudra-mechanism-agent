import argparse
import asyncio
import json
import os
import sys
import time

from cloudra.infra.compute_utils import check_job_type, launch_compute_processes
from cloudra.persistence.database import ConversationDB


async def _mark_failed(dbpath: str, task_id: int, message: str):
    """将任务标记为 failed，并打印错误信息。"""
    print(f"Error: {message}")
    db = ConversationDB.from_path(dbpath)
    async with db.aconnect() as con:
        await con.execute(
            "UPDATE compute_jobs SET state=?, end_timestamp=?, last_error=? WHERE id=?",
            ('failed', time.time(), message[:2000], task_id)
        )
        await con.commit()


async def run_compute(task_id: int, dbpath: str):

    # 接收main传来的id，改数据库，发射guard(与任务绑定，传id，路径，conv_id)和calculator.sh(健壮一点，方便以后解耦)两个子进程
    db = ConversationDB.from_path(dbpath)
    async with db.aconnect() as con:
        cur = await con.execute(
            """SELECT conversation_id, path, jobtype, scheduler,
            scheduler_options FROM compute_jobs WHERE id=?""",
            (task_id,),
        )
        row = await cur.fetchone()

    if row is None:
        await _mark_failed(dbpath, task_id, "计算任务不存在")
        return 1

    try:
        scheduler_options = json.loads(row[4] or '{}')
        if not isinstance(scheduler_options, dict):
            raise ValueError("scheduler_options 必须是 JSON object")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        await _mark_failed(dbpath, task_id, f"scheduler_options 无效：{exc}")
        return 1

    data_dic = {
        'conversation_id': row[0],
        'path': row[1],
        'job_type': row[2],
        'scheduler': row[3] or 'local',
        'scheduler_options': scheduler_options,
    }
    if any(
        data_dic.get(key) is None
        for key in ("conversation_id", "path", "job_type")
    ):
        await _mark_failed(dbpath, task_id, f"{task_id} 计算任务关键参数不完整")
        return 1
    workdir = os.path.dirname(data_dic['path'])

    if data_dic['scheduler'] == 'slurm':
        from cloudra.infra.slurm import run_slurm_compute

        try:
            return await run_slurm_compute(
                task_id,
                dbpath,
                scheduler=data_dic['scheduler_options'],
            )
        except Exception as exc:
            await _mark_failed(dbpath, task_id, f"Slurm 执行失败：{exc}")
            return 1
    if data_dic['scheduler'] != 'local':
        await _mark_failed(
            dbpath,
            task_id,
            f"不支持的 scheduler: {data_dic['scheduler']}",
        )
        return 1

    # 前置依赖检查：避免在缺少计算软件时起空壳进程
    ok, msg = check_job_type(data_dic['job_type'], workdir)
    if not ok:
        await _mark_failed(dbpath, task_id, msg)
        return 1

    # 正常情况下main已经改过state了，这里再确认一次；start_timestamp 只补空值，
    # 以 claim 时写入的开始时间为准。
    try:
        async with db.aconnect() as con:
            await con.execute(
                """UPDATE compute_jobs SET state=?,
                start_timestamp=CASE WHEN start_timestamp IS NULL OR start_timestamp<=0
                    THEN ? ELSE start_timestamp END
                WHERE id=?""",
                ("running", time.time(), task_id),
            )
            await con.commit()
    except Exception as e:
        await _mark_failed(dbpath, task_id, f"更新任务状态失败：{e}")
        return 1

    # 统一启动 guard（guard 会作为 calculator 的父进程并等待其结束）
    ok, msg = await launch_compute_processes(
        task_id=task_id,
        input_file=data_dic['path'],
        job_type=data_dic['job_type'],
        conv_id=data_dic['conversation_id'],
        db_path=dbpath,
        wait_for_calculator=True,
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
