import sys
import os
import json
import aiosqlite
import asyncio
import copy
import argparse
from cloudra.reAct import reAct
from cloudra.subagents import Subagent_hash

async def run_executor(task_id: int, database_path: str, session_id: str = None):
    # 连接数据库获取任务
    async with aiosqlite.connect(database_path, timeout=10) as con:
        await con.execute("PRAGMA journal_mode=WAL;")
        await con.execute("PRAGMA busy_timeout=5000;")
        cur = await con.execute("SELECT input_data FROM subagent_requests WHERE id = ?", (task_id,))
        row = await cur.fetchone()
        if not row:
            print(f"Error: Task {task_id} not found.")
            return
        
        input_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]

    # 准备 Agent 环境,从哈希表里取实例
    agent_hash = Subagent_hash()
    agent_id = input_data.get('agent_id')
    query = input_data.get('query')
    
    template_agent = getattr(agent_hash, agent_id, None)
    if template_agent is None:
        print(f"Error: Agent ID {agent_id} not found.")
        return


    # 关于为什么deepcopy: 不这样做的话所有会话中的子agent都会是同一个
    sub_agent = copy.deepcopy(template_agent)
    sub_agent.query = query
    sub_agent.conversation_id = input_data.get('conversation_id', 'default')
    
    # 重新加载上下文，否则会产生跨会话污染
    await sub_agent.get_context()
    
    # 如果 payload 中传入了额外的 context，则追加进去
    extra_context = input_data.get('context', [])
    if extra_context:
        for block in extra_context:
            # LLM 可能把 context 传成字符串列表，需要转换成标准消息字典
            if isinstance(block, str):
                block = {"role": "user", "content": block}
            elif not isinstance(block, dict):
                block = {"role": "user", "content": str(block)}
            await sub_agent.update_context(block)
    
    # 强制子进程日志不打印到控制台，由主进程通过管道收集
    # 如果 launcher 已指定 session_id，则复用，保证 launcher 与 executor 的 session 一致
    if not session_id:
        session_id = input_data.get('session_id')

    # 子 Agent 的身份 prompt 由 agent.prompt 提供，任务要求由 agent.query 提供，
    # reAct 不再接收会覆盖身份 prompt 的 prompt 参数。
    sub_reAct = reAct(
        agent=sub_agent,
        session_id=session_id
    )
    sub_reAct.log.is_main = True # 在子进程内部，它是主日志

    # 3. 执行任务
    print(f"--- Agent {sub_agent.name} 启动 (PID: {os.getpid()}) ---")
    try:
        result = await sub_reAct.run()
        print(f"\n[结论] {result}")
        print(f"--- Agent {sub_agent.name} 执行完毕 ---")
        
        # 4. 更新数据库状态为 done
        async with aiosqlite.connect(database_path, timeout=10) as con:
            await con.execute("UPDATE subagent_requests SET state = ? WHERE id = ?", ('done', task_id))
            await con.commit()
    except Exception as e:
        print(f"Critical Error in Sub-process: {e}")
        async with aiosqlite.connect(database_path, timeout=10) as con:
            await con.execute("UPDATE subagent_requests SET state = ? WHERE id = ?", ('failed', task_id))
            await con.commit()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--db', type=str, required=True)
    parser.add_argument('--session_id', type=str, default=None)
    args = parser.parse_args()

    asyncio.run(run_executor(args.task_id, args.db, args.session_id))
