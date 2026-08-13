"""任务执行入口：run_task_async / run_task 与后台任务等待。"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from cloudra.base.conversation_class import Conversation
from cloudra.core.agent import Coordinator
from cloudra.core.react import Coordinator_reAct
from cloudra.dag.models import (
    OrchestrationMode,
    build_orchestration_config,
    normalize_orchestration_mode,
)
from cloudra.infra.events import ensure_listener, subscribe_async
from cloudra.infra.presentation import Color, print_banner
from cloudra.infra.runtime_profile import is_mobile_runtime
from cloudra.persistence.context_manager import ContextManager
from cloudra.persistence.database import ConversationDB, aretry_on_locked


async def _count_pending_tasks(db: ConversationDB, conversation_id: str) -> tuple[int, int, int]:
    """返回 (subagent, compute, scheduled reminder 的 pending 数)。"""

    async def query():
        async with db.aconnect() as con:
            cur = await con.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM subagent_requests WHERE state IN ('ready', 'running') AND conversation_id = ?),
                    (SELECT COUNT(*) FROM compute_jobs WHERE state IN ('ready', 'running') AND conversation_id = ?),
                    (SELECT COUNT(*) FROM scheduled_reminders WHERE state = 'pending' AND conversation_id = ?)
                """,
                (conversation_id, conversation_id, conversation_id),
            )
            return await cur.fetchone()

    row = await aretry_on_locked(query)
    return (
        row[0] if row else 0,
        row[1] if row else 0,
        row[2] if row else 0,
    )


async def _fire_due_reminders(db: ConversationDB, conversation_id: str) -> int:
    """原子认领已到期提醒，持久化事件并唤醒目标 Agent。"""
    now = time.time()

    async def claim() -> list:
        async with db.aconnect() as con:
            await con.execute("BEGIN IMMEDIATE")
            cur = await con.execute(
                """
                SELECT id, agent_id, session_id, content FROM scheduled_reminders
                WHERE conversation_id=? AND state='pending' AND wake_at<=?
                ORDER BY wake_at, id
                """,
                (conversation_id, now),
            )
            rows = await cur.fetchall()
            if rows:
                ids = [row[0] for row in rows]
                await con.execute(
                    "UPDATE scheduled_reminders SET state='fired', fired_at=? "
                    f"WHERE id IN ({','.join('?' * len(ids))}) AND state='pending'",
                    (now, *ids),
                )
            await con.commit()
            return rows

    # 写事务必须带锁重试：等待循环每 ≤30s 走一次这里，多进程高峰期的
    # 瞬时锁竞争不应穿透出去杀死整个任务。
    rows = await aretry_on_locked(claim)

    for schedule_id, agent_id, session_id, content in rows:
        await ContextManager.inject_event(
            conversation_id=conversation_id,
            agent_id=agent_id,
            event_type="scheduled_reminder",
            content=(
                f"[Reminder #{schedule_id}] {content}\n"
                "[System] This is a timed reminder you set for yourself, not a new task. "
                "Check each item in the reminder: if the work is done, clean up reminders you "
                "no longer need and call stop to finish silently; if it is unfinished or you "
                "found something new, keep going, and set the next reminder if you still need "
                "to monitor. Do not reply with prose that only acknowledges receipt — output "
                "without action does not advance any work."
            ),
            db_path=db.path,
            session_id=session_id,
        )
    return len(rows)


async def _seconds_until_next_reminder(db: ConversationDB, conversation_id: str) -> float | None:
    async def query():
        async with db.aconnect() as con:
            cur = await con.execute(
                """
                SELECT MIN(wake_at) FROM scheduled_reminders
                WHERE conversation_id=? AND state='pending'
                """,
                (conversation_id,),
            )
            return await cur.fetchone()

    row = await aretry_on_locked(query)
    if not row or row[0] is None:
        return None
    return max(0.0, float(row[0]) - time.time())


async def _wait_for_background_tasks(database: str, conversation_id: str) -> None:
    """等待后台任务完成，或在 Coordinator 收到外部事件时提前返回。

    schedule 等待期间用户仍可能从 TUI 补充消息。外部事件到达时必须把控制权
    交还给 runner，让 Coordinator 立即处理；尚未到期的 reminder 继续保持
    pending，后续仍会再次进入这里等待。
    """
    db = ConversationDB.from_path(database)
    sub = await subscribe_async(
        conversation_id,
        ("task_finished", "session_state", "__worker_stop", "external_event"),
    )

    # 先查一次：如果已经没有 pending，直接返回。
    await _fire_due_reminders(db, conversation_id)
    subagent_count, compute_count, reminder_count = await _count_pending_tasks(db, conversation_id)
    if subagent_count == 0 and compute_count == 0 and reminder_count == 0:
        return

    # 有 pending 则等事件；每被唤醒后只复核一次计数，不再主动轮询。
    while True:
        message = None
        try:
            reminder_delay = await _seconds_until_next_reminder(db, conversation_id)
            timeout = min(30.0, reminder_delay) if reminder_delay is not None else 30.0
            message = await asyncio.wait_for(sub.get(), timeout=max(0.01, timeout))
        except asyncio.TimeoutError:
            pass
        await _fire_due_reminders(db, conversation_id)
        subagent_count, compute_count, reminder_count = await _count_pending_tasks(db, conversation_id)
        if (
            message is not None
            and message.get("kind") == "external_event"
            and message.get("agent_id") in (None, "a-0")
        ):
            return
        if subagent_count == 0 and compute_count == 0 and reminder_count == 0:
            break


async def run_task_async(
    query: str,
    conv_id: Optional[str] = None,
    verbose: bool = True,
    session_id: Optional[str] = None,
    working_directory: Optional[str] = None,
    interactive_approval: bool = True,
    orchestration_mode: str | OrchestrationMode = OrchestrationMode.STANDARD,
    orchestration_config: Optional[dict] = None,
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
    orchestration_mode = normalize_orchestration_mode(orchestration_mode)
    if orchestration_config is None:
        orchestration_config = build_orchestration_config(orchestration_mode)

    if verbose:
        print_banner()
        print(f"{Color.GREEN}[系统]{Color.END} 正在启动任务: {Color.BOLD}{query}{Color.END}")
        if conv_id:
            print(f"{Color.GREEN}[系统]{Color.END} 继续对话: {conv_id}")

    # Conversation/DB/Coordinator/reAct 初始化含同步 SQLite 与磁盘 IO。
    # TUI 与任务同 loop：必须移出，否则启动瞬间界面假死。
    def _bootstrap():
        conversation = Conversation(conv_id)
        conversation.touch()
        conv_db = ConversationDB(conversation.id)
        conv_db.init()
        coordinator_agent = Coordinator(
            query=query,
            conversation_id=conversation.id,
            working_directory=working_directory,
            orchestration_mode=orchestration_mode,
            orchestration_config=orchestration_config,
        )
        father = Coordinator_reAct(coordinator_agent, session_id=session_id)
        return conversation, coordinator_agent, conv_db.path, father

    conversation, coordinator_agent, database, father_reAct = await asyncio.to_thread(
        _bootstrap
    )
    context = await coordinator_agent.get_context()
    if not context or context[-1].get("content") != query:
        await coordinator_agent.update_context({"role": "user", "content": query})

    # 先启动 IPC listener，确保 workers 线程订阅前事件总线可用。
    await ensure_listener(conversation.id)

    workers = None
    if not is_mobile_runtime():
        # workers imports subprocess and must not be imported by embedded
        # Android Python.  Mobile child agents are launched as asyncio tasks.
        from cloudra.runtime import workers as desktop_workers

        workers = desktop_workers
        workers.acquire_workers(database, interactive_approval)

    if verbose:
        print(f"{Color.GREEN}[系统]{Color.END} 协调者 Agent 已就绪，开始推理...\n")

    conversation.set_state("running")
    try:
        result = await father_reAct.run()

        while True:
            if verbose:
                print(f"\n{Color.YELLOW}[系统]{Color.END} 正在等待后台任务完成...")
            await father_reAct._record_phase("waiting")
            await _wait_for_background_tasks(database, conversation.id)

            has_pending_events = await father_reAct.drain_pending_external_events()
            if has_pending_events:
                if verbose:
                    print(
                        f"\n{Color.YELLOW}[系统]{Color.END} "
                        "收到外部事件，Coordinator 继续处理..."
                    )
                father_reAct._continue = True
                result = await father_reAct.run()
                continue

            # drain 为空也可能是 external_event 提前唤醒后的竞态；
            # 只有后台真正排空才允许结束，否则继续等。
            db = ConversationDB.from_path(database)
            sub_n, compute_n, reminder_n = await _count_pending_tasks(
                db, conversation.id
            )
            if sub_n == 0 and compute_n == 0 and reminder_n == 0:
                break

    finally:
        if workers is not None:
            # 后台仍有 ready/running 任务时保住 worker，避免 compute 永久卡 ready。
            should_release = True
            try:
                db = ConversationDB.from_path(database)
                sub_n, compute_n, reminder_n = await _count_pending_tasks(
                    db, conversation.id
                )
                should_release = sub_n == 0 and compute_n == 0 and reminder_n == 0
            except Exception:
                should_release = True
            if should_release:
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
