from cloudra.reAct import reAct, Coordinator_reAct
from cloudra.agent import Coordinator
from cloudra.conversation_class import Conversation
from cloudra.session_manager import SessionManager
import sys
import threading
import os
import asyncio
import json
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
            input_data TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            agent_name TEXT,
            details TEXT,
            state TEXT DEFAULT 'pending' -- pending, approved, denied
        )
    ''')
    
    conn.commit()
    conn.close()


import copy
import subprocess

def pipe_logger(process, agent_name):
    """用于实时转发子进程输出的辅助函数"""
    for line in iter(process.stdout.readline, ''):
        if line:
            print(f"{Color.CYAN}[{agent_name}]{Color.END} {line.strip()}")
    process.stdout.close()

def checking_task(database_path: str):
    # 记录已经启动的进程，避免重复启动
    active_processes = {} 

    while True:
        try:
            con = sqlite3.connect(database_path)
            cur = con.cursor()
            cur.execute("SELECT id, input_data FROM subagent_requests WHERE state = ?", ('ready',))
            requests = cur.fetchall()

            for request in requests:
                request_id, input_data = request
                if isinstance(input_data, str):
                    input_instance = json.loads(input_data)
                else:
                    input_instance = input_data

                agent_id = input_instance.get('agent_id')
                agent_hash = Subagent_hash()
                template_agent = getattr(agent_hash, agent_id, None)
                agent_name = template_agent.name if template_agent else "Unknown"

                # 标记为处理中
                cur.execute(
                    "UPDATE subagent_requests SET state = ? WHERE id = ?",
                    ('running', request_id)
                )
                con.commit()

                # 启动子进程
                # 使用 sys.executable 确保使用与主进程相同的 Python 解释器
                # 以模块方式启动，保证包内 import 正确
                process = subprocess.Popen(
                    [sys.executable, '-m', 'cloudra.executor', '--task_id', str(request_id), '--db', database_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1 # 行缓冲
                )

                # 开启线程实时读取输出
                t = threading.Thread(target=pipe_logger, args=(process, agent_name), daemon=True)
                t.start()
                
                active_processes[request_id] = process

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
                
                con = sqlite3.connect(database_path)
                cur = con.cursor()
                cur.execute("UPDATE approvals SET state = ? WHERE id = ?", (state, req_id))
                con.commit()
                con.close()
                print(f"{Color.GREEN}已标记为: {state}{Color.END}\n")

        except Exception as e:
            pass
        time.sleep(2)


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
    print(f"  版本: v1.0.0{Color.END}")
    print("-" * 45)


def run_task(query: str, conv_id: str = None, verbose: bool = True) -> str:
    """
    执行一个 Cloudra 任务。
    
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
    new_query = {'role':'user', 'content':query}
    coordinator_agent.update_context(new_query)

    father_reAct = Coordinator_reAct(coordinator_agent)

    t = threading.Thread(target=checking_task, args=(database,), daemon=True)
    t.start()

    t_approval = threading.Thread(target=approval_handler, args=(database,), daemon=True)
    t_approval.start()
    
    if verbose:
        print(f"{Color.GREEN}[系统]{Color.END} 协调者 Agent 已就绪，开始推理...\n")
    
    result = asyncio.run(father_reAct.run())
    conversation.touch()

    # 等待子任务完成
    if verbose:
        print(f"\n{Color.YELLOW}[系统]{Color.END} 正在等待子任务完成...")
    while True:
        con = sqlite3.connect(database)
        cur = con.cursor()
        # 只检查属于当前会话且未完成的任务
        cur.execute(
            "SELECT COUNT(*) FROM subagent_requests WHERE (state = 'ready' OR state = 'running') AND input_data LIKE ?",
            (f'%{conversation.id}%',)
        )
        count = cur.fetchone()[0]
        con.close()
        
        if count == 0:
            break
        
        time.sleep(1)
    
    if verbose:
        print(f"\n{Color.BLUE}{Color.BOLD}" + "="*20 + " 任务完成 " + "="*20 + f"{Color.END}")
        print(f"{Color.BOLD}最终结果:{Color.END}\n{result}")
        print(f"{Color.BLUE}{Color.BOLD}" + "="*48 + f"{Color.END}")
    
    return result


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
