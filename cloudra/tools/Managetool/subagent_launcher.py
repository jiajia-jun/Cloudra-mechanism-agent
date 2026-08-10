from typing import Any

from pydantic import Field

from cloudra.agent import Agent
from cloudra.session_class import Session
from cloudra.subagents import Subagent_hash
from cloudra.tools.Managetool._subagent_dispatch import (
    dispatch_subagent,
    run_subagent_in_process,
)
from cloudra.tools_class import Tool, input_schema, output_schema

# 向后兼容：历史实现中该协程定义在本模块，保留别名以防外部引用。
_run_subagent_in_process = run_subagent_in_process

description = (
    "启动子 Agent 执行特定任务。Coordinator 可将复杂任务拆分为多个子任务。\n"
    "重要指南：\n"
    "- **绝对路径**: 必须在 query 或 context 中提供工作目录的绝对路径。\n"
    "- **安全提示**: 系统已开启【安全审计】。除 explorer 外所有子 Agent 均可执行写入/脚本/删除操作，请指导它们在 Thought 中详细说明意图、影响范围与回滚方案以辅助审批。\n"
    "- **任务定义**: 任务描述需极其明确，指定要使用的工具，并明确禁止子 Agent 使用与其任务无关的工具。\n"
    "- **AgentHub**: 子 Agent 可通过 `agent_hub` 工具与其他并行 Agent 共享发现/提问/回答。并行派发有重叠风险的任务时，提醒它们先查 hub、结论发 hub。\n"
    "- **agent_id 必须是唯一标识符**: 调用时只能传入类似 a-1、a-2 的 id，不能传 explorer、writer 等名称；同一 agent_id 可以对不同任务重复派发以实现并行；批量并行建议用 SubAgentSwarm（t-47）。\n"
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

        dispatched = await dispatch_subagent(
            agent_cls,
            agent_id=agent_id,
            query=input_instance.query,
            context=input_instance.context,
            is_wait=input_instance.is_wait,
            conversation_id=conversation_id,
            working_directory=working_directory,
            parent_session_id=parent_session_id,
        )

        return SubAgentLauncher_output_schema(
            session_id=dispatched.session_id,
            act_agent=dispatched.act_agent,
            result=dispatched.result
        )

    def get_subagents(self) -> list[str]:
        return []


def get_class():
    return SubAgentLauncher
