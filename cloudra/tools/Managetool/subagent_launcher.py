import copy
import json
import os
from typing import Any

import aiosqlite
from pydantic import Field

from cloudra.agent import Agent
from cloudra.session_class import Session
from cloudra.subagents import Subagent_hash
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "启动子 Agent 执行特定任务。Coordinator 可将复杂任务拆分为多个子任务。\n"
    "重要指南：\n"
    "- **绝对路径**: 必须在 query 或 context 中提供工作目录的绝对路径。\n"
    "- **安全提示**: 系统已开启【安全审计】。对于 Writer 的写入和 Researcher 的脚本操作，请指导它们在 Thought 中详细说明意图以辅助审批。\n"
    "- **任务定义**: 任务描述需极其明确，指定要使用的工具，并明确禁止子 Agent 使用与其任务无关的工具。\n"
    "- **agent_id 必须是唯一标识符**: 调用时只能传入类似 a-1、a-2 的 id，不能传 explorer、writer 等名称。\n"
    "可用的子 Agent:\n"
    "1. explorer (a-1): 项目探索。总结架构，提取关键信息。只读。\n"
    "2. writer (a-2): 文档/代码产出。覆写文件。需通过安全审计。\n"
    "3. researcher (a-3): 文献/脚本研究。科研搜索，脚本执行。需通过安全审计。\n"
    "4. visionary (a-4): 视觉解析。专门负责图片、图表、分子结构的视觉识别与数据提取。\n"
    "5. operator (a-5): 高级操作。执行危险指令、环境配置、大规模文件管理。拥有最高执行权限，需严审。\n"
    "6. coder (a-6): 代码专家。编写复杂算法、科学计算脚本及自动化工作流。擅长重构、调试与性能优化。"
)


class SubAgentLauncher_input_schema(input_schema):
    agent_id: str = Field(description="要启动的子 Agent 唯一标识符（id），例如 a-1、a-2、a-3，不能传名称如 explorer、writer")
    query: str = Field(
        description=(
            "任务描述。这里只写当前任务需要什么，不要写子 Agent 的身份信息（系统已通过 prompt 注入）。"
            "必须包含：任务目标、必要的绝对路径/输入数据、允许使用的工具、禁止使用的工具、输出格式要求、完成标准。"
        )
    )
    context: list = Field(
        default_factory=list,
        description=(
            "提供给子 Agent 的初始上下文信息列表。"
            "列表中的每个元素必须是标准消息字典，格式为 {\"role\": \"user\"/\"system\"/\"assistant\", \"content\": \"...\"}，"
            "不要传入纯字符串。"
        )
    )
    is_wait: bool = Field(
        default=False,
        description="是否等待子 Agent 执行完毕。若为 True，工具将阻塞直至任务完成并返回结果；若为 False，则仅发射任务并立即返回。"
    )


class toSQLite3_output_schema(output_schema):
    is_success: bool = Field(description="是否成功创建任务记录")
    session_id: str = Field(description="子 Agent 的 Session ID")


class SubAgentLauncher_output_schema(output_schema):
    session_id: str = Field(description="子 Agent 的 Session ID")
    act_agent: str = Field(description="实际执行任务的 Agent 名称")
    result: str = Field(description="子 Agent 的最终返回结果")


class SubAgentLauncher(Tool):
    tool_id: str = 't-0'
    tool_name: str = 'SubAgentLauncher'
    tool_description: str = description
    input_schema: Any = SubAgentLauncher_input_schema
    output_schema: Any = SubAgentLauncher_output_schema
    subagent: Agent = None

    def is_manage(self) -> bool:
        return True

    async def tool_call(
        self,
        input_instance: SubAgentLauncher_input_schema,
        session: Session
    ) -> SubAgentLauncher_output_schema:
        try:
            agent_hash = Subagent_hash()
        except Exception as e:
            return SubAgentLauncher_output_schema(
                session_id="error",
                act_agent="none",
                result=f"【系统错误】无法加载子 Agent 映射表: {str(e)}"
            )

        agent_id = input_instance.agent_id
        query = input_instance.query
        context = input_instance.context
        is_wait = input_instance.is_wait

        # 尝试从 hash 中获取子 agent 模板实例
        template_agent = getattr(agent_hash, agent_id, None)

        if template_agent is None:
            available_ids = list(agent_hash.subagents_dict.keys())
            result = f"Error: Agent ID '{agent_id}' not found. Available IDs: {available_ids}"
            return SubAgentLauncher_output_schema(
                session_id="error",
                act_agent="none",
                result=result
            )

        # 核心防御：如果模板实例异常或属性被清空
        if not hasattr(template_agent, 'temperature'):
             return SubAgentLauncher_output_schema(
                session_id="error",
                act_agent="none",
                result=f"【系统错误】子 Agent '{agent_id}' 实例异常，缺少必要属性。"
            )

        # 深拷贝模板实例，避免污染 Subagent_hash 中的全局缓存。
        # 每个子任务都应拿到一个独立、干净的 Agent 实例。
        sub_agent = copy.deepcopy(template_agent)
        sub_agent.temperature = 0.7
        sub_agent.top_p = 1.0
        sub_agent.frequency_penalty = 0.0
        sub_agent.presence_penalty = 0.0
        sub_agent.query = query
        # 保留父 Agent 的 conversation_id，使 _wait_for_subtasks 仍能按 conversation 聚合任务。
        # 真正的上下文隔离通过 session_id 在 ContextManager 中实现。
        conversation_id = getattr(self.subagent, 'conversation_id', 'default') if self.subagent else 'default'
        sub_agent.conversation_id = conversation_id
        # 不在这里初始化 context_manager，避免在 launcher 进程中污染模板实例。

        act_agent = sub_agent.name

        # 写入数据库记录
        from cloudra.config import get_config
        db_path = os.path.join(get_config().data_dir, 'tasks', 'database.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # 先插入记录以获取 task_id，再生成 session_id 并更新 payload。
        # session_id 用于在 ContextManager 中隔离同一 conversation 下的不同子任务上下文。
        base_payload = {
            'agent_id': agent_id,
            'query': query,
            'context': context,
            'conversation_id': conversation_id,
        }

        if is_wait:
            # 同步模式：标记为 running 并直接启动子进程执行
            async with aiosqlite.connect(db_path) as con:
                cur = await con.execute(
                    "INSERT INTO subagent_requests (state, input_data, conversation_id) VALUES (?, ?, ?)",
                    ('running', json.dumps(base_payload), conversation_id)
                )
                task_id = cur.lastrowid

                # 使用 task_id 生成统一的 session_id，确保 launcher 与 executor 看到的是同一个 session
                session_id = f"{sub_agent.id}_task{task_id}"
                sub_agent.session_id = session_id
                base_payload['session_id'] = session_id
                await con.execute(
                    "UPDATE subagent_requests SET input_data = ? WHERE id = ?",
                    (json.dumps(base_payload), task_id)
                )
                await con.commit()

            import asyncio
            import sys

            # 启动并等待子进程结束
            print(f"\n[系统] 正在同步执行子任务 (Task ID: {task_id})... 请稍候。")
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'cloudra.executor', '--task_id', str(task_id), '--db', db_path, '--session_id', session_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )

            # 实时将子进程输出打印到控制台（带上前缀）
            output_lines = []
            prefix = f"\033[96m[{act_agent}]\033[0m"
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode('utf-8', errors='replace')
                # 子进程输出可能包含多行，逐行加前缀
                for subline in text.splitlines():
                    print(f"{prefix} {subline}")
                    output_lines.append(subline)
            await process.wait()

            # 核心改进：从数据库中获取真实的 result 字段，而不是抓取 stdout 的最后一行
            # 这样可以确保哪怕结论很长，Coordinator 也能完整看到
            async with aiosqlite.connect(db_path) as con:
                cur = await con.execute("SELECT result FROM session WHERE session_id = ?", (session_id,))
                row = await cur.fetchone()

            if row and row[0]:
                result = row[0]
            else:
                result = f"Task completed, but no explicit result was found in database. Last output lines: {' | '.join(output_lines[-3:])}"
        else:
            # 异步模式：仅写入 ready，由 main.py 的后台线程 pickup
            async with aiosqlite.connect(db_path) as con:
                cur = await con.execute(
                    "INSERT INTO subagent_requests (state, input_data, conversation_id) VALUES (?, ?, ?)",
                    ('ready', json.dumps(base_payload), conversation_id)
                )
                task_id = cur.lastrowid
                session_id = f"{sub_agent.id}_task{task_id}"
                sub_agent.session_id = session_id
                base_payload['session_id'] = session_id
                await con.execute(
                    "UPDATE subagent_requests SET input_data = ? WHERE id = ?",
                    (json.dumps(base_payload), task_id)
                )
                await con.commit()
            result = f"Task submitted asynchronously: agent_id={agent_id}, session_id={session_id}"

        return SubAgentLauncher_output_schema(
            session_id=session_id,
            act_agent=act_agent,
            result=result
        )

    def get_subagents(self) -> list[str]:
        return []


def get_class():
    return SubAgentLauncher
