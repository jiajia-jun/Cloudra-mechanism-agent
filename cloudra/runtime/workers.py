"""后台线程池：子 Agent 调度、计算任务分发、审批监听（事件驱动）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

from cloudra import session_store
from cloudra.database import ConversationDB
from cloudra.events import notifier
from cloudra.presentation import Color, pipe_logger
from cloudra.subagents import Subagent_hash

_WORKERS_LOCK = threading.Lock()
_WORKERS: dict[str, dict] = {}

_EVENT_TIMEOUT = 30.0


def reap_exited_executors(database_path: str, active_processes: dict) -> list[int]:
    exited = [rid for rid, proc in list(active_processes.items()) if proc.poll() is not None]
    for rid in exited:
        active_processes.pop(rid, None)
    if not exited:
        return []
    db = ConversationDB.from_path(database_path)
    return session_store.reap_exited_requests(db, exited)


def checking_task(database_path: str, stop_event: threading.Event = None):
    active_processes = {}
    notifier.clear_task()

    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            for rid in reap_exited_executors(database_path, active_processes):
                print(f"{Color.RED}[系统错误]{Color.END} 子任务 {rid} 的执行进程意外退出，已标记为 failed。")
                _notify_state_changed()
            db = ConversationDB.from_path(database_path)
            claimed_task = session_store.claim_ready_request(db)

            if claimed_task:
                request_id, input_data = claimed_task

                if isinstance(input_data, str):
                    input_instance = json.loads(input_data)
                else:
                    input_instance = input_data

                agent_id = input_instance.get("agent_id")
                agent_hash = Subagent_hash()
                agent_cls = agent_hash.get(agent_id)
                agent_name = agent_cls.model_fields["name"].default if agent_cls else "Unknown"

                child_env = dict(os.environ)
                if input_instance.get("yolo"):
                    child_env["CLOUDRA_YOLO_MODE"] = "true"
                process = subprocess.Popen(
                    [sys.executable, "-m", "cloudra.runtime.executor", "--task_id", str(request_id), "--db", database_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=child_env,
                )

                time.sleep(0.5)
                if process.poll() is not None:
                    return_code = process.returncode
                    print(f"{Color.RED}[系统错误]{Color.END} Agent {agent_name} (Task {request_id}) 启动失败! 退出码: {return_code}")
                    session_store.fail_request(db, request_id)
                else:
                    t = threading.Thread(target=pipe_logger, args=(process, agent_name), daemon=True)
                    t.start()
                    active_processes[request_id] = process
                    _notify_state_changed()
        except Exception as e:
            print(f"{Color.RED}[系统错误]{Color.END} checking_task 发生异常: {e}")

        notifier.wait_task(_EVENT_TIMEOUT)


def _notify_state_changed():
    """runner 等待后台任务时用：任务插入或进程退出时触发唤醒。"""
    notifier.notify_task_inserted()
    notifier.notify_compute_inserted()


def apply_approval_decision(database_path: str, req_id: int, state: str, denial_reason: str = "") -> bool:
    db = ConversationDB.from_path(database_path)
    return session_store.decide_approval(db, req_id, state, denial_reason)


def approval_handler(database_path: str, stop_event: threading.Event = None):
    last_error = None
    _unanswerable: set[int] = set()

    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            db = ConversationDB.from_path(database_path)
            requests = session_store.list_pending_approvals(db)

            for req_id, session_id, _agent_name, details in requests:
                if req_id in _unanswerable:
                    continue
                print(f"\n{Color.RED}{Color.BOLD}[安全审批请求]{Color.END}")
                print(f"来自会话: {session_id}")
                print(f"操作详情: {Color.YELLOW}{details}{Color.END}")

                try:
                    user_input = input("是否允许执行？(y/n): ").strip().lower()
                except EOFError:
                    _unanswerable.add(req_id)
                    continue

                state = "approved" if user_input == "y" else "denied"
                denial_reason = ""
                if state == "denied":
                    reason_input = input("拒绝原因（可选，直接回车跳过）: ").strip()
                    if reason_input:
                        denial_reason = session_store.sanitize_db_text(reason_input)

                if apply_approval_decision(database_path, req_id, state, denial_reason):
                    status_msg = f"已标记为: {state}"
                    if state == "denied" and denial_reason:
                        status_msg += f"，原因: {denial_reason}"
                    print(f"{Color.GREEN}{status_msg}{Color.END}\n")
                else:
                    print(f"{Color.YELLOW}[系统]{Color.END} 审批 {req_id} 已在其他端处理，本次输入忽略。\n")

        except Exception as e:
            err = str(e)
            if err != last_error:
                print(f"{Color.RED}[系统错误]{Color.END} approval_handler 发生异常: {err}")
                last_error = err

        notifier.wait_approval(_EVENT_TIMEOUT)


def check_compute(db_path: str, stop_event: threading.Event = None):
    active_processes = {}
    notifier.clear_compute()

    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            db = ConversationDB.from_path(db_path)
            with db.connect() as con:
                cur = con.cursor()

                cur.execute("SELECT id FROM compute_jobs WHERE state = 'ready' LIMIT 1")
                if cur.fetchone() is not None:
                    cur.execute("""
                        UPDATE compute_jobs
                        SET state = 'running'
                        WHERE id IN (
                            SELECT id FROM compute_jobs WHERE state = 'ready' LIMIT 1
                        )
                        RETURNING id
                    """)
                    claimed_task = cur.fetchone()
                else:
                    claimed_task = None

                if claimed_task:
                    task_id, = claimed_task
                    con.commit()

                    process = subprocess.Popen(
                        [sys.executable, "-m", "cloudra.runtime.compute_executor", "--task_id", str(task_id), "--db_path", db_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )
                    time.sleep(0.5)
                    if process.poll() is not None and process.returncode != 0:
                        return_code = process.returncode
                        print(f"{Color.RED}[系统错误]{Color.END} 计算任务 (Task {task_id}) 启动失败! 退出码: {return_code}")
                        cur.execute("UPDATE compute_jobs SET state = ? WHERE id = ? AND state = 'running'", ("failed", task_id))
                        con.commit()
                    else:
                        t = threading.Thread(target=pipe_logger, args=(process, f"compute-{task_id}"), daemon=True)
                        t.start()
                        active_processes[task_id] = process
                else:
                    con.rollback()
        except Exception as e:
            print(f"{Color.RED}[系统错误]{Color.END} check_compute 发生异常: {e}")

        notifier.wait_compute(_EVENT_TIMEOUT)


def acquire_workers(database: str, interactive_approval: bool) -> None:
    with _WORKERS_LOCK:
        existing = _WORKERS.get(database)
        if existing and any(t.is_alive() for t in existing["threads"]):
            existing["refcount"] += 1
            return
        stop_event = threading.Event()
        threads = [
            threading.Thread(target=checking_task, args=(database, stop_event), daemon=True),
            threading.Thread(target=check_compute, args=(database, stop_event), daemon=True),
        ]
        if interactive_approval and not os.environ.get("CLOUDRA_YOLO_MODE"):
            threads.append(threading.Thread(target=approval_handler, args=(database, stop_event), daemon=True))
        for t in threads:
            t.start()
        _WORKERS[database] = {"stop": stop_event, "threads": threads, "refcount": 1}


def release_workers(database: str) -> None:
    with _WORKERS_LOCK:
        entry = _WORKERS.get(database)
        if entry is None:
            return
        entry["refcount"] -= 1
        if entry["refcount"] > 0:
            return
        entry["stop"].set()
        for thread in entry["threads"]:
            thread.join(timeout=0.2)
        _WORKERS.pop(database, None)
