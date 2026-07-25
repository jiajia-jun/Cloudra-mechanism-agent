"""任务执行入口：run_task_async / run_task 与后台任务等待。"""

from __future__ import annotations

import asyncio
from typing import Optional

from cloudra.agent import Coordinator
from cloudra.conversation_class import Conversation
from cloudra.database import ConversationDB
from cloudra.presentation import Color, print_banner
from cloudra.react import Coordinator_reAct
from cloudra.runtime import workers


async def _wait_for_background_tasks(database: str, conversation_id: str) -> None:
    """异步等待当前 conversation 下所有后台任务完成（事件驱动，不再轮询）。"""
    from cloudra.events import notifier as _n

    db = ConversationDB.from_path(database)
    loop = asyncio.get_running_loop()

    while True:
        async with db.aconnect() as con:
            cur = await con.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM subagent_requests WHERE state IN ('ready', 'running') AND conversation_id = ?),
                    (SELECT COUNT(*) FROM compute_jobs WHERE state IN ('ready', 'running') AND conversation_id = ?)
                """,
                (conversation_id, conversation_id),
            )
            row = await cur.fetchone()
            subagent_count = row[0] if row else 0
            compute_count = row[1] if row else 0
        if subagent_count == 0 and compute_count == 0:
            break
        await loop.run_in_executor(None, _n.wait_task, 1.0)


async def run_task_async(
    query: str,
    conv_id: Optional[str] = None,
    verbose: bool = True,
    session_id: Optional[str] = None,
    working_directory: Optional[str] = None,
    interactive_approval: bool = True,
) -> str:
    """执行一个 Cloudra 任务（异步版本）。

    Args:
        query: 用户查询/需求
        conv_id: 可选，继续已有对话
        verbose: 是否打印 banner 和进度信息
        interactive_approval: 是否启动终端交互式审批线程（API 模式应传 False，
            审批改走 Web/API 通道）

    Returns:
        Coordinator 的最终结果字符串
    """
    if verbose:
        print_banner()
        print(f"{Color.GREEN}[系统]{Color.END} 正在启动任务: {Color.BOLD}{query}{Color.END}")
        if conv_id:
            print(f"{Color.GREEN}[系统]{Color.END} 继续对话: {conv_id}")

    conversation = Conversation(conv_id)
    conversation.touch()

    conv_db = ConversationDB(conversation.id)
    conv_db.init()
    database = conv_db.path

    coordinator_agent = Coordinator(
        query=query,
        conversation_id=conversation.id,
        working_directory=working_directory,
    )
    context = await coordinator_agent.get_context()
    if not context or context[-1].get("content") != query:
        await coordinator_agent.update_context({"role": "user", "content": query})

    father_reAct = Coordinator_reAct(coordinator_agent, session_id=session_id)

    workers.acquire_workers(database, interactive_approval)

    if verbose:
        print(f"{Color.GREEN}[系统]{Color.END} 协调者 Agent 已就绪，开始推理...\n")

    conversation.set_state("running")
    try:
        result = await father_reAct.run()

        while True:
            if verbose:
                print(f"\n{Color.YELLOW}[系统]{Color.END} 正在等待后台任务完成...")
            await _wait_for_background_tasks(database, conversation.id)

            cm = coordinator_agent.context_manager
            has_pending = await cm.has_pending_events() if cm else False
            if not has_pending:
                break

            if verbose:
                print(f"\n{Color.YELLOW}[系统]{Color.END} 收到外部事件，Coordinator 继续处理...")
            father_reAct._continue = True
            await father_reAct._poll_and_inject_external_events()
            result = await father_reAct.run()

    finally:
        workers.release_workers(database)
        if conversation.state != "archived":
            conversation.set_state("sleeping")
    conversation.touch()

    if verbose:
        print(f"\n{Color.BLUE}{Color.BOLD}" + "=" * 20 + " 任务完成 " + "=" * 20 + f"{Color.END}")
        print(f"{Color.BOLD}最终结果:{Color.END}\n{result}")
        print(f"{Color.BLUE}{Color.BOLD}" + "=" * 48 + f"{Color.END}")

    return result


def run_task(
    query: str,
    conv_id: Optional[str] = None,
    verbose: bool = True,
    interactive_approval: bool = True,
) -> str:
    """执行一个 Cloudra 任务（同步包装入口）。"""
    return asyncio.run(run_task_async(query, conv_id, verbose, interactive_approval=interactive_approval))
