import argparse
import asyncio
import copy
import json
import os
import signal
import sys
import traceback
from datetime import datetime, timezone

from cloudra.database import ConversationDB, aretry_on_locked, retry_on_locked
from cloudra.reAct import AgentCancelled, reAct
from cloudra.subagents import Subagent_hash


def _mark_cancelled_sync(database_path: str, task_id: int, session_id: str) -> None:
    """事件循环退出后的兜底：用同步连接把任务标记为 cancelled。

    仅在 SIGTERM/SIGINT 打断 asyncio.run 之后调用，此时不能再使用异步连接。
    """
    db = ConversationDB.from_path(database_path)
    now = datetime.now(timezone.utc).isoformat()

    def write():
        with db.connect() as con:
            con.execute("UPDATE subagent_requests SET state='cancelled' WHERE id=?", (task_id,))
            con.execute(
                "UPDATE session SET state='cancelled', finished_at=COALESCE(finished_at, ?) WHERE session_id=?",
                (now, session_id),
            )
            con.commit()

    try:
        retry_on_locked(write, retries=2)
    except Exception as e:
        print(f"[executor] cancelled 状态兜底写入失败: {e}")


async def run_executor(task_id: int, database_path: str, session_id: str = None):
    # 连接数据库获取任务
    db = ConversationDB.from_path(database_path)

    async def fetch_task():
        async with db.aconnect() as con:
            cur = await con.execute("SELECT input_data FROM subagent_requests WHERE id = ?", (task_id,))
            return await cur.fetchone()

    row = await aretry_on_locked(fetch_task)
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
    sub_agent.session_id = input_data.get('session_id')
    sub_agent.working_directory = input_data.get('working_directory')

    # 重置上下文管理器：深拷贝可能把 launcher 中或模板实例里的旧 context_manager 带过来，
    # 强制置空后 get_context() 会按当前 conversation_id/session_id 重新初始化，避免跨任务污染。
    sub_agent.context_manager = None
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
        session_id=session_id,
        parent_session_id=input_data.get('parent_session_id'),
    )
    sub_reAct.log.is_main = True # 在子进程内部，它是主日志

    async def heartbeat():
        while True:
            async def write_heartbeat():
                async with db.aconnect() as con:
                    await con.execute(
                        "UPDATE session SET heartbeat_at=? WHERE session_id=?",
                        (datetime.now(timezone.utc).isoformat(), session_id),
                    )
                    await con.commit()

            try:
                await aretry_on_locked(write_heartbeat)
            except Exception as e:
                # 心跳是可丢失的遥测：锁竞争耗尽重试时打一条日志即可，
                # 不能让心跳任务静默死亡（异常无人 retrieve 且会话看似失联）。
                print(f"[executor] 心跳写入失败（已忽略，下轮继续）: {e}")
            await asyncio.sleep(5)

    heartbeat_task = asyncio.create_task(heartbeat())

    # 3. 执行任务
    print(f"--- Agent {sub_agent.name} 启动 (PID: {os.getpid()}) ---")
    try:
        result = await sub_reAct.run()
        print(f"\n[结论] {result}")
        print(f"--- Agent {sub_agent.name} 执行完毕 ---")

        # 4. 更新数据库状态为 done
        async def mark_done():
            async with db.aconnect() as con:
                await con.execute("UPDATE subagent_requests SET state = ? WHERE id = ?", ('done', task_id))
                await con.execute(
                    "UPDATE session SET exit_code=0, finished_at=COALESCE(finished_at, ?) WHERE session_id=?",
                    (datetime.now(timezone.utc).isoformat(), session_id),
                )
                await con.commit()

        await aretry_on_locked(mark_done)
    except AgentCancelled:
        # 用户打断：reAct.run 已把 session 标为 cancelled，这里同步 subagent_requests
        print(f"--- Agent {sub_agent.name} 已被用户打断 ---")

        async def mark_cancelled():
            async with db.aconnect() as con:
                await con.execute(
                    "UPDATE subagent_requests SET state='cancelled' WHERE id=?", (task_id,)
                )
                await con.execute(
                    "UPDATE session SET state='cancelled', finished_at=COALESCE(finished_at, ?) WHERE session_id=?",
                    (datetime.now(timezone.utc).isoformat(), session_id),
                )
                await con.commit()

        try:
            await aretry_on_locked(mark_cancelled)
        except Exception as mark_err:
            print(f"[executor] cancelled 状态回写失败: {mark_err}")
    except Exception as e:
        # 打印完整 traceback：只打一行 message 会让根因排查变成猜谜
        print(f"Critical Error in Sub-process: {e}")
        traceback.print_exc()
        error_message = str(e)

        async def mark_failed():
            async with db.aconnect() as con:
                await con.execute("UPDATE subagent_requests SET state = ? WHERE id = ?", ('failed', task_id))
                await con.execute(
                    """UPDATE session SET state='failed', error=?, finished_at=?, exit_code=1
                    WHERE session_id=?""",
                    (error_message, datetime.now(timezone.utc).isoformat(), session_id),
                )
                await con.commit()

        try:
            await aretry_on_locked(mark_failed)
        except Exception as mark_err:
            # 状态回写也失败时至少留下日志，不能让异常掩盖原始错误
            print(f"[executor] 任务失败状态回写失败: {mark_err}")
    finally:
        heartbeat_task.cancel()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--db', type=str, required=True)
    parser.add_argument('--session_id', type=str, default=None)
    args = parser.parse_args()

    # SIGTERM（如父进程 cancel）→ 抛出 SystemExit，走下方兜底标记 cancelled
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    try:
        asyncio.run(run_executor(args.task_id, args.db, args.session_id))
    except (KeyboardInterrupt, SystemExit):
        # 事件循环已退出，用同步连接尽力标记 cancelled
        _mark_cancelled_sync(args.db, args.task_id, args.session_id or '')
        sys.exit(0)
