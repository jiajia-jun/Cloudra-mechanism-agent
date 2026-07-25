import argparse
import asyncio
import io
import json
import os
import time
from pathlib import Path

import cclib

from cloudra.context_manager import ContextManager
from cloudra.database import ConversationDB


async def run_guard(taskid: int, path: str, conv_id: str, time_out: int, db_path: str):
    """
    监控 Gaussian 日志文件，解析完成后写入 state.json 并更新数据库。

    使用文件 mtime 变化检测替代固定间隔 sleep：当日志文件未更新时只做轻量
    mtime 检查（0.5s 间隔）；检测到变化时才尝试解析。
    """
    from cloudra.compute_utils import get_log_path
    log_path = Path(get_log_path(path, job_type='gaussian'))
    workdir = os.path.dirname(log_path)
    db = ConversationDB.from_path(db_path)
    last_mtime = 0.0

    while True:
        try:
            current_mtime = log_path.stat().st_mtime
        except FileNotFoundError:
            await asyncio.sleep(0.5)
            continue

        # 文件未变化时轻量等待（time_out 作为首次解析的最大容忍延迟兜底）
        if last_mtime and current_mtime == last_mtime:
            await asyncio.sleep(0.5)
            continue
        last_mtime = current_mtime

        try:
            data = cclib.io.ccread(log_path)
            is_success = data.metadata.get('success', False)
            state_str = cclib.io.ccwrite(data, outputtype="cjson")
        except Exception as e:
            print(f'out文件解析失败：{e}')
            continue

        try:
            state_CJSON = cclib.io.cjsonreader.CJSON(io.StringIO(state_str))
        except Exception as e:
            print(f'json文件解析失败：{e}')
            continue

        data_dic = state_CJSON.parse()
        data_dic.pop('atomcoords', None)
        data_dic['is_success'] = is_success
        json_nm = f'state_{taskid}.json'
        json_path = os.path.join(workdir, json_nm)
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data_dic, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f'写入json失败，遇到问题：{e}')
            continue

        # 更新数据库中的任务状态
        state = 'done' if is_success else 'failed'
        try:
            async with db.aconnect() as con:
                await con.execute(
                    "UPDATE compute_jobs SET state=?, end_timestamp=? WHERE id=?",
                    (state, time.time(), taskid)
                )
                await con.commit()
            print(f'数据库状态已更新: task_id={taskid}, state={state}')
        except Exception as e:
            print(f'更新数据库失败：{e}')
            continue

        # 向 Coordinator 注入计算任务完成事件
        event_content = f'task_id为{taskid}的任务的state已更新为{state}，请前去监测任务状态！若出现问题，请发邮件联系用户。'
        try:
            await ContextManager.inject_event(
                conversation_id=conv_id,
                agent_id='a-0',
                event_type='compute_job',
                content=event_content,
                db_path=db_path,
            )
            print(f'已向 Coordinator 注入计算任务事件: task_id={taskid}')
        except Exception as e:
            print(f'注入上下文事件失败：{e}')

        # 任务已结束，退出监控循环
        break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--path', type=str, required=True)
    parser.add_argument('--conv_id', type=str, required=True)
    parser.add_argument('--timeout', type=int, required=True)
    parser.add_argument('--db_path', type=str, required=True)
    args = parser.parse_args()

    asyncio.run(run_guard(
        taskid=args.task_id,
        path=args.path,
        conv_id=args.conv_id,
        time_out=args.timeout,
        db_path=args.db_path,
    ))
