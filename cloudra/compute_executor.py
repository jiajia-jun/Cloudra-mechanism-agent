import subprocess
import argparse
import sys
import sqlite3
import json
import asyncio

async def run_compute(taskid: str, dbpath: str):

    # 接收main传来的id，改数据库，发射guard(与任务绑定，传id，路径，conv_id)和calculator.sh(健壮一点，方便以后解耦)两个子进程
    con = sqlite3.connect(dbpath, timeout=10)
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA busy_timeout=5000;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    
    cur.execute("SELECT conversation_id, path, jobtype FROM compute_jobs WHERE id=?", (taskid,))
    row = cur.fetchone()
    
    data_dic = {'conversation_id':row[0], 'path':row[1], 'jobtype':row[2],}

    if any(data_dic.get(key, None) is None for key in data_dic):
        print(f"Error: {taskid} 计算任务关键参数不完整")

        # 怎么让系统意识到提交失败了？这里实际上是复用的子agent的逻辑
        return
    else:
        try:
            # 并发产生两个子进程：高斯任务脚本，守护进程
            # 正常情况下main已经改过state了，这里再确认一次
            cur.execute("UPDATE compute_jobs SET state=? WHERE id=?", ("running", taskid))
            # 在这里发射的任务都会在main中得到捕获，正常情况不产生僵尸进程
            # 除非用户主动阻断，而那种情况下的僵尸进程是有益的
            guard = [sys.executable, "-m", "cloudra.guard", 
                    "--path", data_dic['path'], 
                    "--timeout", "1800", 
                    "--conv_id", data_dic['conversation_id'],
                    "--task_id", str(taskid),
                    "--db_path", dbpath]
            calculate = ['calculator.sh', data_dic['path'], data_dic['jobtype']]

            subprocess.Popen(calculate,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.Popen(guard,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            print(f"Error: 提交计算任务发生了错误：{e}")



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--db_path', type=str, required=True)
    args =parser.parse_args()
    asyncio.run(run_compute(args.task_id,args.db_path))



