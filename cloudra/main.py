from cloudra.reAct import reAct, Coordinator_reAct
from cloudra.agent import Coordinator
from cloudra.conversation_class import Conversation
from cloudra.session_manager import SessionManager
import sys
import threading
import os
import asyncio
import json
import aiosqlite
import sqlite3
import time
from cloudra.subagents import Subagent_hash
from cloudra.config import get_config


def init_database(db_path: str):
    """初始化数据库表"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS session (
            session_id TEXT PRIMARY KEY,
            state TEXT,
            result TEXT
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS subagent_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT,
            input_data TEXT,
            conversation_id TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            agent_name TEXT,
            details TEXT,
            state TEXT DEFAULT 'pending', -- pending, approved, denied
            denial_reason TEXT DEFAULT ''
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS compute_jobs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            state TEXT,
            path TEXT,
            start_timestamp INTEGER,
            end_timestamp INTEGER DEFAULT -1,
            jobtype TEXT DEFAULT 'gaussian' -- gaussian, orca, vasp
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS context_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            agent_id TEXT,
            event_type TEXT,
            content TEXT,
            state TEXT DEFAULT 'pending', -- pending, delivered, failed
            created_at REAL
        )
    ''')
    conn.commit()
    conn.close()


import copy
import subprocess

def pipe_logger(process, agent_name):
    """用于实时转发子进程输出的辅助函数"""
    prefix = f"{Color.CYAN}[{agent_name}]{Color.END}"
    for line in iter(process.stdout.readline, ''):
        if not line:
            continue
        # 子进程输出可能包含多行（如 reasoning_content），逐行加前缀，避免信息混在一起
        for subline in line.splitlines():
            print(f"{prefix} {subline}")
    process.stdout.close()

def checking_task(database_path: str):
    # 记录已经启动的进程，避免重复启动
    active_processes = {} 

    while True:
        try:
            con = sqlite3.connect(database_path, timeout=10)
            cur = con.cursor()
            
            # 使用原子操作 (Optimistic Locking): 先尝试把状态从 ready 改为 running，并返回被修改的 id 和 input_data
            # 如果别的线程已经改了，这个 UPDATE 就会返回空，从而避免冲突。
            cur.execute("""
                UPDATE subagent_requests 
                SET state = 'running' 
                WHERE id IN (
                    SELECT id FROM subagent_requests WHERE state = 'ready' LIMIT 1
                )
                RETURNING id, input_data
            """)
            
            claimed_task = cur.fetchone()
            
            if claimed_task:
                request_id, input_data = claimed_task
                con.commit() # 确认修改
                
                if isinstance(input_data, str):
                    input_instance = json.loads(input_data)
                else:
                    input_instance = input_data

                agent_id = input_instance.get('agent_id')
                agent_hash = Subagent_hash()
                template_agent = getattr(agent_hash, agent_id, None)
                agent_name = template_agent.name if template_agent else "Unknown"

                # 启动子进程
                process = subprocess.Popen(
                    [sys.executable, '-m', 'cloudra.executor', '--task_id', str(request_id), '--db', database_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                # ISSUE 3 Fix: 等待一小会儿，检查进程是否瞬间崩溃
                time.sleep(0.5)
                if process.poll() is not None:
                    # 进程刚起就死了
                    return_code = process.returncode
                    print(f"{Color.RED}[系统错误]{Color.END} Agent {agent_name} (Task {request_id}) 启动失败! 退出码: {return_code}")
                    # 回滚状态为 failed，避免死等
                    cur.execute("UPDATE subagent_requests SET state = ? WHERE id = ?", ('failed', request_id))
                    con.commit()
                else:
                    # 正常运行，开启线程读取日志
                    t = threading.Thread(target=pipe_logger, args=(process, agent_name), daemon=True)
                    t.start()
                    active_processes[request_id] = process
            else:
                con.rollback()

            con.close()
        except Exception as e:
            print(f"{Color.RED}[系统错误]{Color.END} checking_task 发生异常: {e}")
        
        time.sleep(1)

def approval_handler(database_path: str):
    """处理安全审批的后台线程"""
    while True:
        try:
            con = sqlite3.connect(database_path)
            cur = con.cursor()
            cur.execute("SELECT id, session_id, details FROM approvals WHERE state = 'pending'")
            requests = cur.fetchall()
            con.close()

            for req_id, session_id, details in requests:
                print(f"\n{Color.RED}{Color.BOLD}[安全审批请求]{Color.END}")
                print(f"来自会话: {session_id}")
                print(f"操作详情: {Color.YELLOW}{details}{Color.END}")
                
                user_input = input("是否允许执行？(y/n): ").strip().lower()
                
                state = 'approved' if user_input == 'y' else 'denied'
                denial_reason = ''
                if state == 'denied':
                    reason_input = input("拒绝原因（可选，直接回车跳过）: ").strip()
                    if reason_input:
                        denial_reason = reason_input
                
                con = sqlite3.connect(database_path)
                cur = con.cursor()
                cur.execute(
                    "UPDATE approvals SET state = ?, denial_reason = ? WHERE id = ?",
                    (state, denial_reason, req_id)
                )
                con.commit()
                con.close()
                status_msg = f"已标记为: {state}"
                if state == 'denied' and denial_reason:
                    status_msg += f"，原因: {denial_reason}"
                print(f"{Color.GREEN}{status_msg}{Color.END}\n")

        except Exception as e:
            pass
        time.sleep(2)


def check_compute(db_path: str):
    active_processes = {}

    while True:
        try:
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()

            cur.execute("""
                UPDATE compute_jobs
                SET state = 'running'
                WHERE id IN (
                    SELECT id FROM compute_jobs WHERE state = 'ready' LIMIT 1
                )
                RETURNING id
            """)

            claimed_task = cur.fetchone()

            if claimed_task:
                task_id, = claimed_task
                con.commit() # 确认修改
            
                process = subprocess.Popen(
                        [sys.executable, '-m', 'cloudra.compute_executor', '--task_id', str(task_id), '--db_path', db_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )
                # 等待一小会儿，检查 compute_executor 是否瞬间崩溃
                time.sleep(0.5)
                if process.poll() is not None and process.returncode != 0:
                    return_code = process.returncode
                    print(f"{Color.RED}[系统错误]{Color.END} 计算任务 (Task {task_id}) 启动失败! 退出码: {return_code}")
                    # 若 compute_executor 内已写入 failed 则无需再改；这里做二次兜底
                    cur.execute("UPDATE compute_jobs SET state = ? WHERE id = ? AND state = 'running'", ('failed', task_id))
                    con.commit()
                else:
                    t = threading.Thread(target=pipe_logger, args=(process, f"compute-{task_id}"), daemon=True)
                    t.start()
                    active_processes[task_id] = process
            else:
                con.rollback()

            con.close()
        except Exception as e:
            print(f'{Color.RED}[系统错误]{Color.END} check_compute 发生异常: {e}')
        time.sleep(5)



class Color:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_banner():
    print(f"{Color.BLUE}{Color.BOLD}")
    print("  Cloudra - AI 化学科研助手")
    print(f"  版本: v1.6.2{Color.END}")
    print("-" * 45)


async def _wait_for_background_tasks(database: str, conversation_id: str) -> None:
    """异步等待当前 conversation 下的所有后台任务（子 Agent + 计算任务）全部完成。

    Coordinator 在此阶段保持进程存活但处于休息状态，不占用 LLM 资源；
    当计算任务完成或子 Agent 返回时，会被唤醒继续处理。
    """
    while True:
        async with aiosqlite.connect(database, timeout=10) as con:
            cur = await con.execute(
                """
                SELECT 
                    (SELECT COUNT(*) FROM subagent_requests WHERE state IN ('ready', 'running') AND conversation_id = ?),
                    (SELECT COUNT(*) FROM compute_jobs WHERE state IN ('ready', 'running') AND conversation_id = ?)
                """,
                (conversation_id, conversation_id)
            )
            row = await cur.fetchone()
            subagent_count = row[0] if row else 0
            compute_count = row[1] if row else 0
        if subagent_count == 0 and compute_count == 0:
            break
        await asyncio.sleep(1)


async def run_task_async(query: str, conv_id: str = None, verbose: bool = True) -> str:
    """
    执行一个 Cloudra 任务（异步版本）。
    
    Args:
        query: 用户查询/需求
        conv_id: 可选，继续已有对话
        verbose: 是否打印 banner 和进度信息
    
    Returns:
        Coordinator 的最终结果字符串
    """
    if verbose:
        print_banner()
        print(f"{Color.GREEN}[系统]{Color.END} 正在启动任务: {Color.BOLD}{query}{Color.END}")
        if conv_id:
            print(f"{Color.GREEN}[系统]{Color.END} 继续对话: {conv_id}")

    data_dir = get_config().data_dir
    database = os.path.join(data_dir, 'tasks', 'database.db')
    
    os.makedirs(os.path.dirname(database), exist_ok=True)
    init_database(database)

    # 恢复或创建对话
    conversation = Conversation(conv_id)
    conversation.touch()
    
    coordinator_agent = Coordinator(query=query, conversation_id=conversation.id)
    # 只有当前上下文中最后一条不是当前 query 时才追加，避免重复插入。
    context = await coordinator_agent.get_context()
    if not context or context[-1].get('content') != query:
        await coordinator_agent.update_context({'role': 'user', 'content': query})

    father_reAct = Coordinator_reAct(coordinator_agent)

    t = threading.Thread(target=checking_task, args=(database,), daemon=True)
    t.start()

    t = threading.Thread(target=check_compute, args=(database,), daemon=True)
    t.start()

    t_approval = threading.Thread(target=approval_handler, args=(database,), daemon=True)
    t_approval.start()
    
    if verbose:
        print(f"{Color.GREEN}[系统]{Color.END} 协调者 Agent 已就绪，开始推理...\n")
    
    # 标记会话为运行中
    conversation.set_state('running')
    try:
        result = await father_reAct.run()

        # Coordinator 第一轮推理结束后，进入休息等待模式：
        # 进程保持存活，持续轮询后台任务（子 Agent / 计算任务）和外部事件。
        while True:
            if verbose:
                print(f"\n{Color.YELLOW}[系统]{Color.END} 正在等待后台任务完成...")
            await _wait_for_background_tasks(database, conversation.id)

            # 检查 guard / 邮件监听器等是否注入了外部事件
            cm = coordinator_agent.context_manager
            has_pending = await cm.has_pending_events() if cm else False
            if not has_pending:
                break

            if verbose:
                print(f"\n{Color.YELLOW}[系统]{Color.END} 收到外部事件，Coordinator 继续处理...")
            result = await father_reAct.run()

    finally:
        # 无论成功失败，任务结束后都标记为 sleeping（除非被归档）
        if conversation.state != 'archived':
            conversation.set_state('sleeping')
    conversation.touch()

    if verbose:
        print(f"\n{Color.BLUE}{Color.BOLD}" + "="*20 + " 任务完成 " + "="*20 + f"{Color.END}")
        print(f"{Color.BOLD}最终结果:{Color.END}\n{result}")
        print(f"{Color.BLUE}{Color.BOLD}" + "="*48 + f"{Color.END}")
    
    return result


def run_task(query: str, conv_id: str = None, verbose: bool = True) -> str:
    """
    执行一个 Cloudra 任务（同步包装入口）。
    """
    return asyncio.run(run_task_async(query, conv_id, verbose))


def legacy_main():
    """兼容旧入口：python cloudra/main.py 'query' [conv_id]"""
    if len(sys.argv) < 2:
        print_banner()
        print(f"{Color.YELLOW}使用方法:{Color.END} python3 -m cloudra.run '你的需求' [对话ID]")
        print(f"{Color.YELLOW}示例:{Color.END} python3 -m cloudra.run '搜索钙钛矿电池相关论文'")
        sys.exit(0)

    query = sys.argv[1]
    conv_id = sys.argv[2] if len(sys.argv) > 2 else None
    run_task(query, conv_id)


if __name__ == '__main__':
    legacy_main()
