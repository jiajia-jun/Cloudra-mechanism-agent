import asyncio
from pathlib import Path
import cclib
import json
import os
import subprocess
import argparse
import sqlite3
import time


async def run_guard(taskid: int, path: str, conv_id: str, time_out: int, db_path: str):
    '''
    启动后每 time_out 秒解析一次 log 文档，写入 state.json，
    更新 compute_jobs 表状态，并唤醒 conv_id 下的 agent。

    path 是 gjf 路径！
    '''
    log_path = Path(path).with_suffix('.out')
    workdir = os.path.dirname(log_path)

    while True:
        await asyncio.sleep(time_out)

        try:
            data = cclib.io.read(log_path)
            is_success = data.metadata.get('success', False)
            state_str = cclib.io.ccwrite(data, outputtype="cjson")
        except Exception as e:
            print(f'out文件解析失败：{e}')
            continue

        try:
            state_CJSON = cclib.io.cjsonreader.CJSON(state_str)
        except Exception as e:
            print(f'json文件解析失败：{e}')
            continue

        data_dic = state_CJSON.parse()
        del data_dic['atomcoords']
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
        try:
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()
            state = 'done' if is_success else 'failed'
            cur.execute(
                "UPDATE compute_jobs SET state=?, end_timestamp=? WHERE id=?",
                (state, time.time(), taskid)
            )
            con.commit()
            con.close()
            print(f'数据库状态已更新: task_id={taskid}, state={state}')
        except Exception as e:
            print(f'更新数据库失败：{e}')
            continue

        # 唤醒 agent
        prompt = f'task_id为{taskid}的任务的state已更新，请前去监测任务状态！若出现问题，请发邮件联系用户。'
        cmd = ['cloudra', 'run', f'"{prompt}"', '--conv_id', conv_id]
        subprocess.run(cmd)

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
