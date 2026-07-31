import argparse
import asyncio
import json
import os
import signal
import sys
import traceback

from cloudra import events, session_store
from cloudra.context_manager import ContextManager
from cloudra.database import ConversationDB, aretry_on_locked
from cloudra.platform_utils import is_posix
from cloudra.react import AgentCancelled, reAct
from cloudra.subagents import Subagent_hash
from cloudra.tools.Interactool.ask_user import use_input_handler


def _mark_cancelled_sync(database_path: str, task_id: int, session_id: str) -> None:
    """事件循环退出后的兜底：用同步连接把任务标记为 cancelled。

    仅在 SIGTERM/SIGINT 打断 asyncio.run 之后调用，此时不能再使用异步连接。
    """
    db = ConversationDB.from_path(database_path)
    try:
        session_store.finalize_task(db, task_id, session_id, 'cancelled', retries=2)
    except Exception as e:
        print(f"[executor] cancelled 状态兜底写入失败: {e}")


async def _finalize_task(db, task_id: int, session_id: str, status: str, error: str = None) -> None:
    """executor 本地薄封装：统一收尾写库（done/cancelled/failed 单一路径），失败只打日志。"""
    try:
        await session_store.afinalize_task(db, task_id, session_id, status, error=error)
    except Exception as mark_err:
        print(f"[executor] 任务收尾状态回写失败 ({status}): {mark_err}")


async def _wake_coordinator(database_path: str, input_data: dict, content: str) -> None:
    """持久化唤醒事件后再退出，避免 fire-and-forget 随子进程一起丢失。"""
    try:
        conv_id = input_data.get('conversation_id', 'default')
        await ContextManager.inject_event(
            conversation_id=conv_id,
            agent_id='a-0',
            event_type='subagent',
            content=content,
            db_path=database_path,
        )
    except Exception as e:
        print(f"[executor] 事件注入失败: {e}")


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

    # 准备 Agent 环境,从注册表取 Agent 类并实例化（注册表现在存类而非模板实例）
    agent_hash = Subagent_hash()
    agent_id = input_data.get('agent_id')
    query = input_data.get('query')

    agent_cls = agent_hash.get(agent_id)
    if agent_cls is None:
        print(f"Error: Agent ID {agent_id} not found.")
        return

    conv_id = input_data.get('conversation_id', 'default')

    # 启动 IPC listener，使本进程能收到外部事件与 cancel 信号。
    await events.ensure_listener(conv_id)

    working_dir = input_data.get('working_directory')
    sub_agent = agent_cls(
        query=query,
        conversation_id=conv_id,
        working_directory=working_dir,
    )
    sub_agent.session_id = input_data.get('session_id')

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

    # 子 Agent 身份 prompt 在每次模型请求前动态装配；任务要求由 agent.query 提供。
    sub_reAct = reAct(
        agent=sub_agent,
        session_id=session_id,
        parent_session_id=input_data.get('parent_session_id'),
    )
    sub_reAct.log.is_main = True # 在子进程内部，它是主日志

    # 3. 执行任务
    print(f"--- Agent {sub_agent.name} 启动 (PID: {os.getpid()}) ---")
    try:
        async def wait_for_user(prompt: str) -> str:
            from cloudra.interactions import wait_for_user_response

            return await wait_for_user_response(
                conversation_id=conv_id,
                session_id=session_id,
                agent_id=agent_id,
                prompt=prompt,
                db_path=database_path,
            )

        with use_input_handler(wait_for_user):
            result = await sub_reAct.run()
        print(f"\n[结论] {result}")
        print(f"--- Agent {sub_agent.name} 执行完毕 ---")

        # 4. 统一收尾：落库 done，并注入事件唤醒 Coordinator（结论截断 500 字符）
        await _finalize_task(db, task_id, session_id, 'done')
        await _wake_coordinator(
            database_path,
            input_data,
            f"子 Agent {sub_agent.name} (session={session_id}, task_id={task_id}) 已完成。结论: {result[:500]}",
        )
    except AgentCancelled:
        # 用户打断：reAct.run 已把 session 标为 cancelled，这里同步 subagent_requests
        print(f"--- Agent {sub_agent.name} 已被用户打断 ---")
        await _finalize_task(db, task_id, session_id, 'cancelled')
        await _wake_coordinator(
            database_path,
            input_data,
            f"子 Agent {sub_agent.name} (session={session_id}, task_id={task_id}) 已被取消。",
        )
    except Exception as e:
        # 打印完整 traceback：只打一行 message 会让根因排查变成猜谜
        print(f"Critical Error in Sub-process: {e}")
        traceback.print_exc()
        error_message = str(e)

        await _finalize_task(db, task_id, session_id, 'failed', error=error_message)
        # 事件内容截断 500 字符；session.error 保留完整错误
        await _wake_coordinator(
            database_path,
            input_data,
            f"子 Agent {sub_agent.name} (session={session_id}, task_id={task_id}) 执行失败: {error_message[:500]}",
        )

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task_id', type=int, required=True)
    parser.add_argument('--db', type=str, required=True)
    parser.add_argument('--session_id', type=str, default=None)
    args = parser.parse_args()

    # SIGTERM（如父进程 cancel）→ 抛出 SystemExit，走下方兜底标记 cancelled。
    # Windows 上 SIGTERM 不会由系统正常投递，仅 POSIX 注册处理器。
    if is_posix():
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    try:
        asyncio.run(run_executor(args.task_id, args.db, args.session_id))
    except (KeyboardInterrupt, SystemExit):
        # 事件循环已退出，用同步连接尽力标记 cancelled
        _mark_cancelled_sync(args.db, args.task_id, args.session_id or '')
        sys.exit(0)
