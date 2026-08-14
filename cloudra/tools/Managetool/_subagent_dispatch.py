"""子 Agent 派发的可复用核心：实例化 → 落库 → 按模式执行 → 从 DB 取结果。

SubAgentLauncher (t-0) 与 SubAgentSwarm (t-47) 共用此模块；t-0 的行为
（同步/异步、inprocess/subprocess、输出前缀打印、结果回取、yolo env 传播）
全部封装在 dispatch_subagent 中，launcher 只做参数解析与输出包装。
"""

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional

from cloudra.dag.models import OrchestrationMode, normalize_orchestration_mode
from cloudra.infra.runtime_profile import subagent_execution_mode
from cloudra.persistence.database import ConversationDB, aretry_on_locked, get_database_path
from cloudra.persistence.workspace import resolve_working_directory
from cloudra.services import session_store


def _subagent_orchestration_mode(parent_mode: Any) -> OrchestrationMode:
    """DAG 会话的子 Agent 以 dag_record 运行：确定性 harness 负责登记工具证据，
    子 Agent 不触发 Supervisor（guided 只属 Coordinator 会话）。standard 会话
    的子 Agent 保持 standard，零图开销。
    """
    if normalize_orchestration_mode(parent_mode) is OrchestrationMode.STANDARD:
        return OrchestrationMode.STANDARD
    return OrchestrationMode.DAG_RECORD


async def run_subagent_in_process(task_id: int, db_path: str, session_id: str) -> None:
    """进程内执行子任务：异常一律落库 failed/cancelled，绝不传播到父 Agent 的事件循环。

    run_executor 内部已捕获执行期异常（done/failed/cancelled 单一路径收尾）；
    这里兜底它启动阶段（取任务、实例化 Agent 等）可能抛出的异常，
    否则任务状态会永远挂在 running。
    """
    from cloudra.runtime.executor import run_executor

    try:
        await run_executor(task_id, db_path, session_id)
    except asyncio.CancelledError:
        # 父任务被取消：对齐子进程路径 SIGTERM 的兜底语义，尽力标记 cancelled 后继续传播。
        try:
            db = ConversationDB.from_path(db_path)
            await session_store.afinalize_task(db, task_id, session_id, 'cancelled')
        except Exception as mark_err:
            print(f"[系统错误] 子任务取消状态回写失败: {mark_err}")
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            db = ConversationDB.from_path(db_path)
            await session_store.afinalize_task(db, task_id, session_id, 'failed', error=str(e))
        except Exception as mark_err:
            print(f"[系统错误] 子任务收尾状态回写失败: {mark_err}")


@dataclass
class SubagentDispatchResult:
    """单次派发的结果句柄。"""

    task_id: int
    session_id: str
    act_agent: str
    result: str


async def dispatch_subagent(
    agent_cls: Any,
    *,
    agent_id: str,
    query: str,
    context: list,
    is_wait: bool,
    conversation_id: str,
    working_directory: Optional[str],
    parent_session_id: Optional[str],
    parent_orchestration_mode: Any = OrchestrationMode.STANDARD,
    semaphore: Optional[asyncio.Semaphore] = None,
    extra_payload: Optional[dict] = None,
) -> SubagentDispatchResult:
    """实例化子 Agent、落库 subagent_requests、按运行模式执行并回取结果。

    semaphore 仅在 is_wait=True 时有意义：in-process 模式包住执行协程，
    subprocess 模式包住 spawn + 等待，用于 swarm 限制并发实例数。
    """
    working_directory = resolve_working_directory(working_directory)
    sub_agent = agent_cls(
        query=query,
        conversation_id=conversation_id,
        working_directory=working_directory,
    )
    sub_agent.temperature = 0.7
    sub_agent.top_p = None
    sub_agent.frequency_penalty = 0.0
    sub_agent.presence_penalty = 0.0
    sub_agent.working_directory = working_directory
    sub_mode = _subagent_orchestration_mode(parent_orchestration_mode)
    sub_agent.orchestration_mode = sub_mode

    act_agent = sub_agent.name

    db_path = get_database_path(conversation_id)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = ConversationDB(conversation_id)

    # 先插入记录以获取 task_id，再生成 session_id 并更新 payload。
    # session_id 用于在 ContextManager 中隔离同一 conversation 下的不同子任务上下文。
    # yolo 标志随 payload 落库：子 Agent 子进程启动时据此注入 CLOUDRA_YOLO_MODE，
    # 使 Session 级 YOLO 能跨进程传播（CLI 进程级 env 则天然继承）。
    from cloudra.infra.yolo_guard import is_yolo_enabled
    base_payload = {
        'agent_id': agent_id,
        'query': query,
        'context': context,
        'conversation_id': conversation_id,
        'parent_session_id': parent_session_id,
        'working_directory': sub_agent.working_directory,
        'orchestration_mode': sub_mode.value,
        'yolo': is_yolo_enabled(),
    }
    if extra_payload:
        base_payload.update(extra_payload)

    if is_wait:
        # 同步模式：默认在当前 Python 进程内执行（Android 唯一支持的方式）；
        # CLOUDRA_SUBAGENT_MODE=subprocess 可切回每任务一个子进程的旧行为。
        in_process = subagent_execution_mode() == "inprocess"
        task_id, session_id, base_payload = await session_store.acreate_subagent_request(
            db,
            state='running',
            payload=base_payload,
            conversation_id=conversation_id,
            parent_session_id=parent_session_id,
            session_id_fn=lambda tid: f"{sub_agent.id}_task{tid}",
        )
        sub_agent.session_id = session_id

        output_lines = []
        print(f"\n[系统] 正在同步执行子任务 (Task ID: {task_id})... 请稍候。")

        async def _execute() -> None:
            if in_process:
                await run_subagent_in_process(task_id, db_path, session_id)
            else:
                import sys

                # Session 级 YOLO 通过 env 显式传给子进程。
                child_env = dict(os.environ)
                if base_payload.get('yolo'):
                    child_env["CLOUDRA_YOLO_MODE"] = "true"
                process = await asyncio.create_subprocess_exec(
                    sys.executable, '-m', 'cloudra.runtime.executor', '--task_id', str(task_id), '--db', db_path, '--session_id', session_id,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=child_env
                )

                # 实时将子进程输出打印到控制台（带上前缀）。
                prefix = f"\033[96m[{act_agent}]\033[0m"
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    text = line.decode('utf-8', errors='replace')
                    for subline in text.splitlines():
                        print(f"{prefix} {subline}")
                        output_lines.append(subline)
                await process.wait()

        if semaphore is not None:
            async with semaphore:
                await _execute()
        else:
            await _execute()

        # 核心改进：从数据库中获取真实的 result 字段，而不是抓取 stdout 的最后一行
        # 这样可以确保哪怕结论很长，Coordinator 也能完整看到
        async def fetch_result():
            async with db.aconnect() as con:
                cur = await con.execute("SELECT result FROM session WHERE session_id = ?", (session_id,))
                return await cur.fetchone()

        row = await aretry_on_locked(fetch_result)

        if row and row[0]:
            result = row[0]
        else:
            result = f"Task completed, but no explicit result was found in database. Last output lines: {' | '.join(output_lines[-3:])}"
    else:
        # 进程内执行时任务创建后直接作为同进程协程运行（state=running）；
        # 子进程模式下挂 ready，由 worker 线程认领并 spawn executor 子进程。
        in_process = subagent_execution_mode() == "inprocess"
        request_state = 'running' if in_process else 'ready'
        task_id, session_id, base_payload = await session_store.acreate_subagent_request(
            db,
            state=request_state,
            payload=base_payload,
            conversation_id=conversation_id,
            parent_session_id=parent_session_id,
            session_id_fn=lambda tid: f"{sub_agent.id}_task{tid}",
        )
        sub_agent.session_id = session_id
        if in_process:
            from cloudra.runtime.mobile_tasks import create_mobile_task

            create_mobile_task(run_subagent_in_process(task_id, db_path, session_id))
        else:
            from cloudra.infra import events

            await events.aemit(
                conversation_id,
                "subagent_request_ready",
                task_id=task_id,
                session_id=session_id,
                agent_id=agent_id,
            )
        result = (
            f"Task submitted asynchronously: agent_id={agent_id}, session_id={session_id}. "
            f"Retrieve the result later with get_subagent_report(session_id=\"{session_id}\")."
        )

    return SubagentDispatchResult(
        task_id=task_id,
        session_id=session_id,
        act_agent=act_agent,
        result=result,
    )


async def fetch_subagent_outcome(
    db: ConversationDB, task_id: int, session_id: str
) -> tuple[str, str]:
    """读取已结束子任务的 (状态, 结果文本)，供 swarm 聚合报告使用。"""

    async def fetch():
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT state FROM subagent_requests WHERE id = ?", (task_id,)
            )
            state_row = await cur.fetchone()
            cur = await con.execute(
                "SELECT result FROM session WHERE session_id = ?", (session_id,)
            )
            result_row = await cur.fetchone()
            return state_row, result_row

    state_row, result_row = await aretry_on_locked(fetch)
    state = state_row[0] if state_row and state_row[0] else "unknown"
    result = result_row[0] if result_row and result_row[0] else "(无结果)"
    return state, result
