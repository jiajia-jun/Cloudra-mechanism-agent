"""后台线程池：子 Agent 调度、计算任务分发、审批监听（事件驱动）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from cloudra import session_store
from cloudra.database import ConversationDB
from cloudra.events import emit, subscribe_thread
from cloudra.presentation import Color, pipe_logger
from cloudra.subagents import Subagent_hash

_WORKERS_LOCK = threading.Lock()
_WORKERS: dict[str, dict] = {}

# 子进程启动宽限期：如果在此时间内退出且任务仍挂在 running，视为启动崩溃。
_STARTUP_GRACE_SECONDS = 2.0


def _conv_id_from_db_path(db_path: str) -> str:
    try:
        return Path(db_path).parent.parent.name
    except Exception:
        return "default"


def reap_exited_executors(database_path: str, active_processes: dict) -> list[int]:
    """兼容旧测试/调用方：扫描 active_processes 中已退出进程并回收。

    生产主循环已改为 watcher 线程 + IPC 事件驱动，不再主动轮询 proc.poll()。
    """
    exited = [rid for rid, proc in list(active_processes.items()) if proc.poll() is not None]
    if not exited:
        return []
    # 任何已退出进程都不应再留在 active 表中，无论 DB 是否真正做了状态迁移。
    for rid in exited:
        active_processes.pop(rid, None)
    db = ConversationDB.from_path(database_path)
    return session_store.reap_exited_requests(db, exited)


def _emit_worker_stop(conv_id: str) -> None:
    """让同步线程无超时 wait 立即退出。"""
    try:
        emit(conv_id, "__worker_stop")
    except Exception:
        pass


def _watch_subprocess(
    process: subprocess.Popen,
    db_path: str,
    task_id: int,
    kind: str,
    label: str,
) -> None:
    """守护线程：等待子进程退出，必要时把仍挂 running 的任务标为 failed 并广播事件。"""
    start = time.monotonic()
    try:
        returncode = process.wait()
    except Exception:
        returncode = -1
    elapsed = time.monotonic() - start

    conv_id = _conv_id_from_db_path(db_path)
    failed = False

    try:
        db = ConversationDB.from_path(db_path)
        if kind == "subagent":
            # 如果 executor 正常结束，它自己已经落库 done/failed；这里只处理未收尾的残迹。
            reaped = session_store.reap_exited_requests(db, [task_id])
            if reaped:
                failed = True
        else:  # compute
            with db.connect() as con:
                row = con.execute(
                    "SELECT state FROM compute_jobs WHERE id=?", (task_id,)
                ).fetchone()
                state = row[0] if row else None
                if state in ("ready", "running") and (elapsed < _STARTUP_GRACE_SECONDS or returncode != 0):
                    con.execute(
                        "UPDATE compute_jobs SET state='failed', end_timestamp=? WHERE id=?",
                        (time.time(), task_id),
                    )
                    con.commit()
                    failed = True
                else:
                    con.commit()
        if failed:
            print(
                f"{Color.RED}[系统错误]{Color.END} {label} (Task {task_id}) 进程异常退出/启动失败! "
                f"退出码: {returncode}"
            )
            if kind == "compute":
                emit(conv_id, "task_finished", task_id=task_id, task_kind="compute", state="failed")
        else:
            # 正常结束：runner 等的是 task_finished 事件；如果 executor 没有 emit（如老版本），这里兜底广播。
            emit(conv_id, "task_finished", task_id=task_id, task_kind=kind, state="done")
    except Exception as e:
        print(f"{Color.RED}[系统错误]{Color.END} {label} 退出回收失败: {e}")


def _start_subagent_executor(
    database_path: str,
    request_id: int,
    input_data: dict,
    active_processes: dict,
) -> None:
    """启动一个子 Agent executor 子进程并挂上 watcher。"""
    agent_id = input_data.get("agent_id")
    agent_hash = Subagent_hash()
    agent_cls = agent_hash.get(agent_id)
    agent_name = agent_cls.model_fields["name"].default if agent_cls else "Unknown"

    if request_id in active_processes:
        return

    child_env = dict(os.environ)
    if input_data.get("yolo"):
        child_env["CLOUDRA_YOLO_MODE"] = "true"

    process = subprocess.Popen(
        [sys.executable, "-m", "cloudra.runtime.executor", "--task_id", str(request_id), "--db", database_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=child_env,
    )
    active_processes[request_id] = process

    t = threading.Thread(
        target=pipe_logger,
        args=(process, agent_name),
        daemon=True,
    )
    t.start()

    threading.Thread(
        target=_watch_subprocess,
        args=(process, database_path, request_id, "subagent", f"Agent {agent_name}"),
        daemon=True,
    ).start()


def checking_task(database_path: str, stop_event: threading.Event = None):
    active_processes: dict[int, subprocess.Popen] = {}
    conv_id = _conv_id_from_db_path(database_path)
    sub = subscribe_thread(
        conv_id,
        ("subagent_request_ready", "task_finished", "__worker_stop"),
    )

    while True:
        if stop_event and stop_event.is_set():
            break
        payload = sub.wait(timeout=None)
        if payload is None:
            continue
        if stop_event and stop_event.is_set():
            break

        kind = payload.get("_kind")
        if kind == "task_finished":
            active_processes.pop(payload.get("task_id"), None)
            continue

        try:
            db = ConversationDB.from_path(database_path)
            while True:
                claimed = session_store.claim_ready_request(db)
                if not claimed:
                    break
                request_id, input_data = claimed
                if isinstance(input_data, str):
                    input_data = json.loads(input_data)
                _start_subagent_executor(database_path, request_id, input_data, active_processes)
        except Exception as e:
            print(f"{Color.RED}[系统错误]{Color.END} checking_task 发生异常: {e}")


def _start_compute_executor(db_path: str, task_id: int, active_processes: dict) -> None:
    if task_id in active_processes:
        return
    process = subprocess.Popen(
        [sys.executable, "-m", "cloudra.runtime.compute_executor", "--task_id", str(task_id), "--db_path", db_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    active_processes[task_id] = process

    t = threading.Thread(
        target=pipe_logger,
        args=(process, f"compute-{task_id}"),
        daemon=True,
    )
    t.start()

    threading.Thread(
        target=_watch_subprocess,
        args=(process, db_path, task_id, "compute", f"compute-{task_id}"),
        daemon=True,
    ).start()


def check_compute(db_path: str, stop_event: threading.Event = None):
    active_processes: dict[int, subprocess.Popen] = {}
    conv_id = _conv_id_from_db_path(db_path)
    sub = subscribe_thread(
        conv_id,
        ("compute_job_ready", "task_finished", "__worker_stop"),
    )

    while True:
        if stop_event and stop_event.is_set():
            break
        payload = sub.wait(timeout=None)
        if payload is None:
            continue
        if stop_event and stop_event.is_set():
            break

        kind = payload.get("_kind")
        if kind == "task_finished":
            active_processes.pop(payload.get("task_id"), None)
            continue

        try:
            db = ConversationDB.from_path(db_path)
            with db.connect() as con:
                cur = con.cursor()
                cur.execute("SELECT id FROM compute_jobs WHERE state = 'ready' LIMIT 1")
                row = cur.fetchone()
                if row is None:
                    con.rollback()
                    continue
                cur.execute("""
                    UPDATE compute_jobs
                    SET state = 'running'
                    WHERE id IN (
                        SELECT id FROM compute_jobs WHERE state = 'ready' LIMIT 1
                    )
                    RETURNING id
                """)
                claimed = cur.fetchone()
                if claimed:
                    con.commit()
                    task_id = claimed[0]
                    _start_compute_executor(db_path, task_id, active_processes)
                else:
                    con.rollback()
        except Exception as e:
            print(f"{Color.RED}[系统错误]{Color.END} check_compute 发生异常: {e}")


def apply_approval_decision(database_path: str, req_id: int, state: str, denial_reason: str = "") -> bool:
    db = ConversationDB.from_path(database_path)
    return session_store.decide_approval(db, req_id, state, denial_reason)


def approval_handler(database_path: str, stop_event: threading.Event = None):
    last_error = None
    _unanswerable: set[int] = set()
    conv_id = _conv_id_from_db_path(database_path)
    sub = subscribe_thread(
        conv_id,
        ("approval_pending", "approval_decided", "__worker_stop"),
    )

    while True:
        if stop_event and stop_event.is_set():
            break
        payload = sub.wait(timeout=None)
        if payload is None:
            continue
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
        _emit_worker_stop(_conv_id_from_db_path(database))
        for thread in entry["threads"]:
            thread.join(timeout=0.5)
        _WORKERS.pop(database, None)
