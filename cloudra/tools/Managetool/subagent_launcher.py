import os
from typing import Any

from pydantic import Field

from cloudra import session_store
from cloudra.agent import Agent
from cloudra.database import ConversationDB, aretry_on_locked, get_database_path
from cloudra.runtime_profile import is_mobile_runtime
from cloudra.session_class import Session
from cloudra.subagents import Subagent_hash
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "启动子 Agent 执行特定任务。Coordinator 可将复杂任务拆分为多个子任务。\n"
    "重要指南：\n"
    "- **绝对路径**: 必须在 query 或 context 中提供工作目录的绝对路径。\n"
    "- **安全提示**: 系统已开启【安全审计】。除 explorer 外所有子 Agent 均可执行写入/脚本/删除操作，请指导它们在 Thought 中详细说明意图、影响范围与回滚方案以辅助审批。\n"
    "- **任务定义**: 任务描述需极其明确，指定要使用的工具，并明确禁止子 Agent 使用与其任务无关的工具。\n"
    "- **AgentHub**: 子 Agent 可通过 `agent_hub` 工具与其他并行 Agent 共享发现/提问/回答。并行派发有重叠风险的任务时，提醒它们先查 hub、结论发 hub。\n"
    "- **agent_id 必须是唯一标识符**: 调用时只能传入类似 a-1、a-2 的 id，不能传 explorer、writer 等名称。\n"
    "可用的子 Agent:\n"
    "1. explorer (a-1): 探索+审查。摸清项目结构、定位文件；只读审查代码/文档/数据，输出带证据的审查报告。只读。\n"
    "2. writer (a-2): 论文写作与文档产出。写报告、论文、文档。需通过安全审计。\n"
    "3. researcher (a-3): 文献查阅。学术检索、方法论拆解、文献对标。全权限，危险操作需严审。\n"
    "4. small_mol (a-4): 小分子计算。Gaussian/ORCA 等分子/团簇量化计算：构象、过渡态、光谱、能量。\n"
    "5. md (a-5): 分子动力学。GROMACS/LAMMPS 体系构建、平衡、采样与轨迹分析。\n"
    "6. dft (a-6): 第一性原理。VASP/QE 等周期体系计算：体相、表面、缺陷、电子性质。\n"
    "7. experiment (a-7): 实验设计。DOE、对照设计、表征矩阵、安全评估与失败诊断。\n"
    "8. env (a-8): 环境管理。依赖安装、conda/虚拟环境、编译配置、HPC 作业环境。全权限，需严审。"
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

        # 兼容测试或旧调用中 session 为 None 的情况。
        parent_session_id = getattr(session, "id", None) if session else None

        # 从注册表获取 Agent 类并实例化（注册表现在存类而非模板实例）
        agent_cls = agent_hash.get(agent_id)

        if agent_cls is None:
            available_ids = list(agent_hash.subagents_dict.keys())
            result = f"Error: Agent ID '{agent_id}' not found. Available IDs: {available_ids}"
            return SubAgentLauncher_output_schema(
                session_id="error",
                act_agent="none",
                result=result
            )

        conversation_id = getattr(self.subagent, 'conversation_id', 'default') if self.subagent else 'default'
        working_directory = getattr(self.subagent, 'working_directory', None)
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

        act_agent = sub_agent.name

        db_path = get_database_path(conversation_id)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db = ConversationDB(conversation_id)

        # 先插入记录以获取 task_id，再生成 session_id 并更新 payload。
        # session_id 用于在 ContextManager 中隔离同一 conversation 下的不同子任务上下文。
        # yolo 标志随 payload 落库：子 Agent 子进程启动时据此注入 CLOUDRA_YOLO_MODE，
        # 使 Session 级 YOLO 能跨进程传播（CLI 进程级 env 则天然继承）。
        from cloudra.yolo_guard import is_yolo_enabled
        base_payload = {
            'agent_id': agent_id,
            'query': query,
            'context': context,
            'conversation_id': conversation_id,
            'parent_session_id': parent_session_id,
            'working_directory': sub_agent.working_directory,
            'yolo': is_yolo_enabled(),
        }

        if is_wait:
            # 同步模式：桌面端启动子进程；Android 在当前 Python 进程内执行。
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
            if is_mobile_runtime():
                from cloudra.runtime.executor import run_executor

                await run_executor(task_id, db_path, session_id)
            else:
                import asyncio
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
            # Android 没有 worker 子进程，任务创建后直接作为同进程协程运行。
            request_state = 'running' if is_mobile_runtime() else 'ready'
            task_id, session_id, base_payload = await session_store.acreate_subagent_request(
                db,
                state=request_state,
                payload=base_payload,
                conversation_id=conversation_id,
                parent_session_id=parent_session_id,
                session_id_fn=lambda tid: f"{sub_agent.id}_task{tid}",
            )
            sub_agent.session_id = session_id
            if is_mobile_runtime():
                from cloudra.runtime.executor import run_executor
                from cloudra.runtime.mobile_tasks import create_mobile_task

                create_mobile_task(run_executor(task_id, db_path, session_id))
            else:
                from cloudra import events

                await events.aemit(
                    conversation_id,
                    "subagent_request_ready",
                    task_id=task_id,
                    session_id=session_id,
                    agent_id=agent_id,
                )
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
