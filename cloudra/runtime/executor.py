import argparse
import asyncio
import json
import os
import signal
import sys
import time
import traceback

from cloudra.core.react import AgentCancelled, reAct
from cloudra.infra import events
from cloudra.infra.platform_utils import is_posix
from cloudra.infra.runtime_profile import is_mobile_runtime
from cloudra.persistence.context_manager import ContextManager
from cloudra.persistence.database import ConversationDB, aretry_on_locked
from cloudra.services import session_store
from cloudra.subagents import Subagent_hash
from cloudra.tools.Interactool.ask_user import use_input_handler


def _mark_cancelled_sync(database_path: str, task_id: int, session_id: str) -> None:
    """事件循环退出后的兜底：用同步连接把任务标记为 cancelled。

    仅在 SIGTERM/SIGINT 打断 asyncio.run 之后调用，此时不能再使用异步连接。
    子 Agent 无论何种停法都要通知 Coordinator——这里补上 SIGTERM 路径漏掉的事件。
    hub_call 会话不当交付：跳过 Coordinator「已完成/终止」唤醒，改给主叫挂断。
    """
    db = ConversationDB.from_path(database_path)
    conv_id = "default"
    agent_label = "subagent"
    payload: dict = {}
    try:
        with db.connect() as con:
            row = con.execute(
                "SELECT conversation_id, input_data FROM subagent_requests WHERE id=?",
                (task_id,),
            ).fetchone()
        if row:
            conv_id = row[0] or conv_id
            try:
                loaded = json.loads(row[1] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                loaded = {}
            if isinstance(loaded, dict):
                payload = loaded
                conv_id = payload.get("conversation_id") or conv_id
                agent_label = payload.get("agent_id") or agent_label
    except Exception as e:
        print(f"[executor] 读取 subagent 元数据失败: {e}")

    try:
        session_store.finalize_task(db, task_id, session_id, 'cancelled', retries=2)
    except Exception as e:
        print(f"[executor] cancelled 状态兜底写入失败: {e}")

    if payload.get("origin") == "hub_call":
        _wake_caller_hangup_sync(
            database_path,
            payload,
            agent_name=agent_label,
            session_id=session_id,
        )
        return

    _wake_coordinator_sync(
        database_path,
        conversation_id=conv_id,
        content=(
            f"Sub-agent {agent_label} (session={session_id}, task_id={task_id}) "
            f"was terminated (SIGTERM/interrupt)."
        ),
    )


def _wake_coordinator_sync(
    database_path: str, *, conversation_id: str, content: str
) -> None:
    """同步写入 Coordinator 唤醒事件（事件循环已退出时使用）。"""
    try:
        db = ConversationDB.from_path(database_path)
        with db.connect() as con:
            con.execute(
                """
                INSERT INTO context_events
                    (conversation_id, agent_id, session_id, event_type, content, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id or "default",
                    "a-0",
                    None,
                    "subagent",
                    content,
                    "pending",
                    time.time(),
                ),
            )
            con.commit()
        events.emit(
            conversation_id or "default",
            "external_event",
            agent_id="a-0",
            session_id=None,
            event_type="subagent",
            content=content,
        )
    except Exception as e:
        print(f"[executor] 同步唤醒 Coordinator 失败: {e}")


def _wake_caller_hangup_sync(
    database_path: str,
    input_data: dict,
    *,
    agent_name: str,
    session_id: str | None,
) -> None:
    """SIGTERM 后无法走 async deliver_incoming_call：同步给主叫挂断。"""
    conv_id = input_data.get("conversation_id") or "default"
    caller_id = input_data.get("caller_agent_id") or "a-0"
    caller_session = input_data.get("caller_session_id") or None
    hangup = f"[Call ended] {agent_name} (session={session_id}) hung up."
    try:
        db = ConversationDB.from_path(database_path)
        with db.connect() as con:
            con.execute(
                """
                INSERT INTO context_events
                    (conversation_id, agent_id, session_id, event_type, content, state, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conv_id,
                    caller_id,
                    caller_session,
                    "user_message",
                    hangup,
                    "pending",
                    time.time(),
                ),
            )
            con.commit()
        events.emit(
            conv_id,
            "external_event",
            agent_id=caller_id,
            session_id=caller_session,
            event_type="user_message",
            content=hangup,
        )
    except Exception as e:
        print(f"[executor] 同步挂断通知失败: {e}")


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


async def _wake_after_executor(
    database_path: str,
    input_data: dict,
    content: str,
    *,
    agent_name: str | None = None,
    session_id: str | None = None,
) -> None:
    """Launcher 子任务唤醒 Coordinator；hub_call 会话则给主叫挂断，不当交付。"""
    if input_data.get("origin") == "hub_call":
        try:
            caller_id = input_data.get("caller_agent_id") or "a-0"
            caller_session = input_data.get("caller_session_id") or ""
            label = agent_name or input_data.get("agent_id") or "subagent"
            sid = session_id or input_data.get("session_id")
            hangup = f"[Call ended] {label} (session={sid}) hung up."
            from cloudra.tools.Managetool._hub_call import deliver_incoming_call

            await deliver_incoming_call(
                conversation_id=input_data.get("conversation_id", "default"),
                callee_agent_id=caller_id,
                callee_session_id=caller_session or "",
                text=hangup,
                db_path=database_path,
            )
        except Exception as e:
            print(f"[executor] 事件注入失败: {e}")
        return
    await _wake_coordinator(database_path, input_data, content)


async def _backfill_dag_assignee_nodes(
    db: ConversationDB,
    session_id: str,
    agent_id: str,
    final_state: str,
    error: str = None,
    orchestration_mode: str = 'standard',
) -> None:
    """子 Agent 终态 → process 图指派节点的确定性补写。

    只补 ``payload.assignee == agent_id`` 且仍停在 ready/running 的 planned 节点：
    done → succeeded；failed/cancelled → failed（blocked_reason 取 error 前 200
    字符）。on_tool_finished 的绑定回报与子 agent 手动 update_node 都不动——
    这里只兜住"子进程结束了但节点没人收尾"的情况。standard 会话零开销直接返回；
    补写失败只打日志，不影响收尾主路径。
    """
    from cloudra.dag.models import OrchestrationMode, normalize_orchestration_mode

    if normalize_orchestration_mode(orchestration_mode) is OrchestrationMode.STANDARD:
        return

    def _apply() -> None:
        from cloudra.dag.controller import DagController
        from cloudra.dag.models import UpdateNode
        from cloudra.dag.store import DagStore, GraphBundleNotFound

        store = DagStore(db)
        try:
            snapshot = store.load_snapshot()
        except GraphBundleNotFound:
            return  # 该 conversation 还没建图
        node_status = 'succeeded' if final_state == 'done' else 'failed'
        operations = []
        for node in snapshot.process.nodes:
            if node.node_type == 'observed_tool_call':
                continue  # harness 遥测记录不是排产工作，不由子 agent 收尾
            if node.assignee != agent_id:
                continue
            if node.status not in {'ready', 'running'}:
                continue
            changes = {'status': node_status}
            if node_status == 'failed' and error:
                changes['blocked_reason'] = error[:200]
            operations.append(UpdateNode(
                op='update_node',
                graph='process',
                node_id=node.node_id,
                changes=changes,
            ))
        if not operations:
            return
        # harness 通道写入：actor=HARNESS 不受按图分权限制，自带 stale 重试
        DagController(db, session_id, orchestration_mode)._apply_harness(
            operations,
            f"sub-agent {agent_id} ended with {final_state}; "
            "deterministic assignee status backfill",
        )

    try:
        await asyncio.to_thread(_apply)
    except Exception as exc:
        print(f"[executor] DAG 终态补写失败（已忽略）: {exc}")


async def _pending_reminder_count(db: ConversationDB, conv_id: str, agent_id: str, session_id: str = None) -> int:
    """本 Agent 本 session 仍待触发的 schedule 提醒数（含无 session 的旧提醒）。"""

    if session_id is not None:
        where = ("conversation_id=? AND agent_id=? AND state='pending' "
                 "AND (session_id IS NULL OR session_id=?)")
        params = (conv_id, agent_id, session_id)
    else:
        where = "conversation_id=? AND agent_id=? AND state='pending'"
        params = (conv_id, agent_id)

    async def query() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(
                f"SELECT COUNT(*) FROM scheduled_reminders WHERE {where}",
                params,
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    return await aretry_on_locked(query)


async def _seconds_until_own_reminder(db: ConversationDB, conv_id: str, agent_id: str, session_id: str = None) -> float | None:
    """本 Agent 本 session 下一次提醒到期距现在的秒数（无提醒返回 None）。"""

    if session_id is not None:
        where = ("conversation_id=? AND agent_id=? AND state='pending' "
                 "AND (session_id IS NULL OR session_id=?)")
        params = (conv_id, agent_id, session_id)
    else:
        where = "conversation_id=? AND agent_id=? AND state='pending'"
        params = (conv_id, agent_id)

    async def query():
        async with db.aconnect() as con:
            cur = await con.execute(
                f"SELECT MIN(wake_at) FROM scheduled_reminders WHERE {where}",
                params,
            )
            return await cur.fetchone()

    row = await aretry_on_locked(query)
    if not row or row[0] is None:
        return None
    return max(0.0, float(row[0]) - time.time())


async def _session_heartbeat(db: ConversationDB, session_id: str | None) -> None:
    """子 Agent session 的存活心跳（5s，对齐 service 侧 `_heartbeat`）。

    executor 是独立子进程，没有 service 的心跳任务；缺了它，挂起等待提醒
    （waiting）或长任务运行中的活体 session 心跳静止，会被 recover_stale
    误判成僵尸标 interrupted。心跳是 best-effort，失败绝不杀死主流程。
    """
    if not session_id:
        return
    while True:
        await asyncio.sleep(5)
        try:
            await session_store.aheartbeat(db, session_id)
        except Exception:
            pass


async def _run_with_reminder_waits(sub_reAct, db: ConversationDB, conv_id: str, agent_id: str):
    """跑子 Agent 主循环；结束后若本 Agent 仍有 pending schedule 提醒，挂起等待。

    子 Agent 的 ReAct 一旦以正文/stop 收尾就会 return；但它可能刚用 schedule
    安排了自唤醒（例如监控异步计算任务）。此时不能放任 session 结束——
    挂起进程，等提醒到期（自己原子认领触发，与主 runner 并发安全）或收到
    外部事件后，复活循环续跑。没有 pending 提醒时立即返回，行为与原来一致。
    """
    from cloudra.runtime.runner import _fire_due_reminders

    # 并行子任务可能复用同一个 agent_id（如多个 a-4），等待与复活都必须
    # 限定在本 session 的提醒上，否则会互相唤醒、互相续命。
    session_id = getattr(getattr(sub_reAct, "session", None), "id", None)

    result = await sub_reAct.run()
    while await _pending_reminder_count(db, conv_id, agent_id, session_id) > 0:
        sub = await events.subscribe_async(conv_id, "external_event")
        delay = await _seconds_until_own_reminder(db, conv_id, agent_id, session_id)
        timeout = min(30.0, delay) if delay is not None else 30.0
        try:
            await asyncio.wait_for(sub.get(), timeout=max(0.05, timeout))
        except asyncio.TimeoutError:
            pass
        # 自己触发到期提醒（原子认领，主 runner 同时触发也不会重复）
        await _fire_due_reminders(db, conv_id)
        if not await sub_reAct.drain_pending_external_events():
            continue  # 唤醒但没有本 Agent 的事件（如别人的广播），继续等
        sub_reAct._continue = True
        result = await sub_reAct.run()
    return result


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
    # DAG 会话的子 Agent 以 dag_record 运行（派发时写入 payload），
    # 让 harness 登记它们的工具证据；缺省/standard 保持零图开销。
    from cloudra.dag.models import normalize_orchestration_mode

    sub_agent.orchestration_mode = normalize_orchestration_mode(
        input_data.get('orchestration_mode', 'standard')
    )

    # hub_call spawn：session.query 仍是通话原文，但上下文不能再落一条裸 query。
    # 先挂上 query="" 的 ContextManager，后面 extra_context 只追加【来电】user 行。
    if input_data.get("origin") == "hub_call":
        sub_agent.context_manager = ContextManager(
            agent_id=sub_agent.id,
            conversation_id=sub_agent.conversation_id,
            prompt=sub_agent.prompt,
            query="",
            session_id=sub_agent.session_id,
            on_compaction_progress=sub_agent._report_compaction_progress,
        )

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
    # reAct.__init__ 里的 session_create 走同步 sqlite 写入（busy_timeout 会阻塞
    # 等待写锁）：进程内并发执行多个子任务（swarm）时，若在事件循环线程直接构造，
    # 一旦与其他协程的异步写事务竞争，同步 busy 等待会冻结整个事件循环直至超时
    # （异步持锁方需要事件循环才能提交）。放到工作线程构造，锁等待不再阻塞循环。
    sub_reAct = await asyncio.to_thread(
        reAct,
        agent=sub_agent,
        session_id=session_id,
        parent_session_id=input_data.get('parent_session_id'),
    )
    sub_reAct.log.is_main = True # 在子进程内部，它是主日志

    # 3. 执行任务
    print(f"--- Agent {sub_agent.name} 启动 (PID: {os.getpid()}) ---")
    # 进程内 follower（隔离 TUI resume / swarm）不经过 run_task_async，
    # 必须自己拉起 check_compute，否则 Coordinator 进程死后 jobs 会停在 ready。
    workers_mod = None
    if not is_mobile_runtime():
        from cloudra.runtime import workers as workers_mod
        workers_mod.acquire_workers(database_path, interactive_approval=False)
    heartbeat = asyncio.create_task(
        _session_heartbeat(db, getattr(getattr(sub_reAct, "session", None), "id", None))
    )
    try:
        async def wait_for_user(prompt: str) -> str:
            from cloudra.services.interactions import wait_for_user_response

            return await wait_for_user_response(
                conversation_id=conv_id,
                session_id=session_id,
                agent_id=agent_id,
                prompt=prompt,
                db_path=database_path,
            )

        with use_input_handler(wait_for_user):
            result = await _run_with_reminder_waits(sub_reAct, db, conv_id, agent_id)
        print(f"\n[结论] {result}")
        print(f"--- Agent {sub_agent.name} 执行完毕 ---")

        # 4. 统一收尾：落库 done，并注入事件唤醒 Coordinator（结论截断 500 字符）
        await _finalize_task(db, task_id, session_id, 'done')
        await _backfill_dag_assignee_nodes(
            db, session_id, agent_id, 'done',
            orchestration_mode=input_data.get('orchestration_mode', 'standard'),
        )
        await _wake_after_executor(
            database_path,
            input_data,
            f"Sub-agent {sub_agent.name} (session={session_id}, task_id={task_id}) completed. Conclusion: {result[:500]}",
            agent_name=sub_agent.name,
            session_id=session_id,
        )
    except AgentCancelled:
        # 用户打断：reAct.run 已把 session 标为 cancelled，这里同步 subagent_requests
        print(f"--- Agent {sub_agent.name} 已被用户打断 ---")
        await _finalize_task(db, task_id, session_id, 'cancelled')
        await _backfill_dag_assignee_nodes(
            db, session_id, agent_id, 'cancelled',
            orchestration_mode=input_data.get('orchestration_mode', 'standard'),
        )
        await _wake_after_executor(
            database_path,
            input_data,
            f"Sub-agent {sub_agent.name} (session={session_id}, task_id={task_id}) was cancelled.",
            agent_name=sub_agent.name,
            session_id=session_id,
        )
    except Exception as e:
        # 打印完整 traceback：只打一行 message 会让根因排查变成猜谜
        print(f"Critical Error in Sub-process: {e}")
        traceback.print_exc()
        error_message = str(e)

        await _finalize_task(db, task_id, session_id, 'failed', error=error_message)
        await _backfill_dag_assignee_nodes(
            db, session_id, agent_id, 'failed', error=error_message,
            orchestration_mode=input_data.get('orchestration_mode', 'standard'),
        )
        # 事件内容截断 500 字符；session.error 保留完整错误
        await _wake_after_executor(
            database_path,
            input_data,
            f"Sub-agent {sub_agent.name} (session={session_id}, task_id={task_id}) failed: {error_message[:500]}",
            agent_name=sub_agent.name,
            session_id=session_id,
        )
    finally:
        heartbeat.cancel()
        if workers_mod is not None:
            should_release = True
            try:
                from cloudra.runtime.runner import _count_pending_tasks
                sub_n, compute_n, reminder_n = await _count_pending_tasks(db, conv_id)
                should_release = sub_n == 0 and compute_n == 0 and reminder_n == 0
            except Exception:
                should_release = True
            if should_release:
                workers_mod.release_workers(database_path)

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
