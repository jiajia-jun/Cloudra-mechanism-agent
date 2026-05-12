import sys
import os
import json
import sqlite3
import asyncio
import copy
import argparse
from reAct import reAct
from subagents import Subagent_hash

async def run_executor(task_id: int, database_path: str):
    # 1. 连接数据库获取任务
    con = sqlite3.connect(database_path, timeout=10)
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("SELECT input_data FROM subagent_requests WHERE id = ?", (task_id,))
    row = cur.fetchone()
    if not row:
        print(f"Error: Task {task_id} not found.")
        return
    
    input_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    con.close()

    # 2. 准备 Agent 环境
    agent_hash = Subagent_hash()
    agent_id = input_data.get('agent_id')
    query = input_data.get('query')
    
    template_agent = getattr(agent_hash, agent_id, None)
    if template_agent is None:
        print(f"Error: Agent ID {agent_id} not found.")
        return

    sub_agent = copy.deepcopy(template_agent)
    sub_agent.query = query
    sub_agent.conversation_id = input_data.get('conversation_id', 'default')
    
    # 核心修复：必须根据新的 conversation_id 重新加载上下文，否则会产生跨会话污染
    sub_agent.context = sub_agent.get_context()
    
    # 如果 payload 中传入了额外的 context，则追加进去
    extra_context = input_data.get('context', [])
    if extra_context:
        for block in extra_context:
            sub_agent.update_context(block)
    
    # 强制子进程日志不打印到控制台，由主进程通过管道收集
    sub_reAct = reAct(
        agent=sub_agent,
        prompt=input_data.get('reasoning_prompt', "")
    )
    sub_reAct.log.is_main = True # 在子进程内部，它是主日志

    # 3. 执行任务
    print(f"--- Agent {sub_agent.name} 启动 (PID: {os.getpid()}) ---")
    try:
        result = await sub_reAct.run()
        print(f"\n[结论] {result}")
        print(f"--- Agent {sub_agent.name} 执行完毕 ---")
        
        # 4. 更新数据库状态为 done
        con = sqlite3.connect(database_path, timeout=10)
        cur = con.cursor()
        cur.execute("UPDATE subagent_requests SET state = ? WHERE id = ?", ('done', task_id))
        con.commit()
        con.close()
    except Exception as e:
        print(f"Critical Error in Sub-process: {e}")
        con = sqlite3.connect(database_path, timeout=10)
        cur = con.cursor()
        cur.execute("UPDATE subagent_requests SET state = ? WHERE id = ?", ('failed', task_id))
        con.commit()
        con.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--db', type=str, required=True)
    args = parser.parse_args()

    asyncio.run(run_executor(args.task_id, args.db))
