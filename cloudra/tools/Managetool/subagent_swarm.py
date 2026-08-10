"""SubAgentSwarm (t-47)：对同一子 Agent 角色批量并行派发多个不同任务。

复用 _subagent_dispatch 的派发核心（与 t-0 同一套实例化/落库/执行/回取逻辑），
逐项展开 prompt_template 中的 {{item}} 占位符后并发派发，聚合结果返回。
"""

import asyncio
from typing import Any

from pydantic import Field

from cloudra.agent import Agent
from cloudra.database import ConversationDB
from cloudra.session_class import Session
from cloudra.subagents import Subagent_hash
from cloudra.tools.Managetool._subagent_dispatch import (
    dispatch_subagent,
    fetch_subagent_outcome,
)
from cloudra.tools_class import Tool, input_schema, output_schema

MIN_ITEMS = 2
MAX_ITEMS = 128

_STATE_LABELS = {
    "done": "成功",
    "failed": "失败",
    "cancelled": "已取消",
}

description = (
    "对同一子 Agent 角色并行派发多个不同任务（swarm）。Coordinator 用一个模板对 items 列表中的每一项各启动一个同角色子 Agent 实例，并发执行后聚合全部结果。\n"
    "重要指南：\n"
    "- **占位符**: prompt_template 必须包含 {{item}} 占位符，每项任务用它展开；展开后的任务描述必须两两不同。\n"
    "- **绝对路径与工具边界**: 必须在模板或 context 中指明工作目录的绝对路径，并明确允许使用的工具与禁止使用的工具。\n"
    "- **AgentHub**: 并行子任务可通过 `agent_hub` 工具互通发现/提问/回答；派发有重叠风险的任务时，提醒它们先查 hub、结论发 hub。\n"
    "- **并发上限**: max_concurrency > 0 时限制同时运行的子 Agent 实例数，默认 0 表示不限。\n"
    "- **agent_id**: 只能传入类似 a-1、a-2 的 id，不能传 explorer、writer 等名称；同一 agent_id 的多个实例并行运行，各自持有独立的会话与规划存储。\n"
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


class SubAgentSwarm_input_schema(input_schema):
    agent_id: str = Field(description="要并行派发的子 Agent 唯一标识符（id），例如 a-1、a-4，不能传名称如 explorer、small_mol")
    prompt_template: str = Field(
        description=(
            "任务模板，必须包含 {{item}} 占位符，每个子任务用 items 中对应项替换后展开。"
            "模板中必须包含：任务目标、必要的绝对路径/输入数据、允许使用的工具、禁止使用的工具、输出格式要求、完成标准。"
        )
    )
    items: list[str] = Field(
        description=f"要并行处理的任务项列表（{MIN_ITEMS}–{MAX_ITEMS} 项），每项替换模板中的 {{{{item}}}} 后生成一个子任务。"
    )
    context: list = Field(
        default_factory=list,
        description=(
            "注入每个子任务的初始上下文信息列表。"
            "列表中的每个元素必须是标准消息字典，格式为 {\"role\": \"user\"/\"system\"/\"assistant\", \"content\": \"...\"}，"
            "不要传入纯字符串。"
        )
    )
    is_wait: bool = Field(
        default=True,
        description="是否等待全部子任务完成并聚合结果。若为 False，则仅发射任务并立即返回所有 session_id。"
    )
    max_concurrency: int = Field(
        default=0,
        description="同时运行的子 Agent 实例数上限。0 表示不限；>0 时用信号量限制并发。"
    )


class SubAgentSwarm_output_schema(output_schema):
    session_ids: list[str] = Field(description="每个子任务的 Session ID（与 items 顺序一致）")
    task_ids: list[int] = Field(description="每个子任务的 Task ID（与 items 顺序一致）")
    result: str = Field(description="聚合报告（is_wait=True）或派发回执（is_wait=False）")


def _summarize_item(item: str, limit: int = 40) -> str:
    """item 摘要：单行化并截断，用于报告分节标题。"""
    text = " ".join(str(item).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class SubAgentSwarm(Tool):
    tool_id: str = 't-47'
    tool_name: str = 'SubAgentSwarm'
    tool_description: str = description
    input_schema: Any = SubAgentSwarm_input_schema
    output_schema: Any = SubAgentSwarm_output_schema
    subagent: Agent = None

    def is_manage(self) -> bool:
        return True

    def _error(self, message: str) -> SubAgentSwarm_output_schema:
        return SubAgentSwarm_output_schema(session_ids=[], task_ids=[], result=message)

    async def tool_call(
        self,
        input_instance: SubAgentSwarm_input_schema,
        session: Session
    ) -> SubAgentSwarm_output_schema:
        # ---- 校验 ----
        template = input_instance.prompt_template
        if "{{item}}" not in template:
            return self._error(
                "Error: prompt_template 必须包含 {{item}} 占位符，"
                "每个子任务用它替换为 items 中的对应项。"
            )

        items = [str(i) for i in input_instance.items]
        if not (MIN_ITEMS <= len(items) <= MAX_ITEMS):
            return self._error(
                f"Error: items 数量必须在 {MIN_ITEMS}–{MAX_ITEMS} 之间，实际为 {len(items)}。"
            )

        prompts = [template.replace("{{item}", item) for item in items]
        seen: dict[str, int] = {}
        duplicate_items: list[str] = []
        for item, prompt in zip(items, prompts):
            if prompt in seen:
                duplicate_items.append(item)
            else:
                seen[prompt] = len(seen)
        if duplicate_items:
            return self._error(
                "Error: 以下 items 展开后的任务描述与其他项重复，请去重或修改模板: "
                f"{duplicate_items}"
            )

        try:
            agent_hash = Subagent_hash()
        except Exception as e:
            return self._error(f"【系统错误】无法加载子 Agent 映射表: {str(e)}")

        agent_id = input_instance.agent_id
        agent_cls = agent_hash.get(agent_id)
        if agent_cls is None:
            available_ids = list(agent_hash.subagents_dict.keys())
            return self._error(
                f"Error: Agent ID '{agent_id}' not found. Available IDs: {available_ids}"
            )

        parent_session_id = getattr(session, "id", None) if session else None
        conversation_id = getattr(self.subagent, 'conversation_id', 'default') if self.subagent else 'default'
        working_directory = getattr(self.subagent, 'working_directory', None)

        # ---- 派发 ----
        if input_instance.is_wait:
            return await self._run_waiting(
                agent_cls, agent_id, items, prompts, input_instance,
                conversation_id, working_directory, parent_session_id,
            )
        return await self._run_fire_and_forget(
            agent_cls, agent_id, items, prompts, input_instance,
            conversation_id, working_directory, parent_session_id,
        )

    async def _run_waiting(
        self, agent_cls, agent_id, items, prompts, input_instance,
        conversation_id, working_directory, parent_session_id,
    ) -> SubAgentSwarm_output_schema:
        max_concurrency = int(input_instance.max_concurrency or 0)
        semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency > 0 else None
        db = ConversationDB(conversation_id)

        async def run_one(prompt: str):
            """派发单项并回取状态；异常不抛出，聚合为失败分节。"""
            try:
                dispatched = await dispatch_subagent(
                    agent_cls,
                    agent_id=agent_id,
                    query=prompt,
                    context=input_instance.context,
                    is_wait=True,
                    conversation_id=conversation_id,
                    working_directory=working_directory,
                    parent_session_id=parent_session_id,
                    semaphore=semaphore,
                )
            except Exception as e:
                return None, "failed", f"【系统错误】派发或执行异常: {e}"
            state, _result = await fetch_subagent_outcome(db, dispatched.task_id, dispatched.session_id)
            return dispatched, state, dispatched.result

        outcomes = await asyncio.gather(*(run_one(p) for p in prompts))

        session_ids: list[str] = []
        task_ids: list[int] = []
        sections: list[str] = []
        total = len(items)
        succeeded = 0
        for index, (item, (dispatched, state, result)) in enumerate(zip(items, outcomes), start=1):
            label = _STATE_LABELS.get(state, f"未知({state})")
            if state == "done":
                succeeded += 1
            session_id = dispatched.session_id if dispatched else "error"
            session_ids.append(session_id)
            task_ids.append(dispatched.task_id if dispatched else -1)
            sections.append(
                f"=== Item {index}/{total}: {_summarize_item(item)} ===\n"
                f"状态: {label}\n"
                f"session_id: {session_id}\n"
                f"{result}"
            )

        report = (
            f"Swarm 完成: {succeeded}/{total} 个成功 (agent_id={agent_id})\n\n"
            + "\n\n".join(sections)
        )
        return SubAgentSwarm_output_schema(
            session_ids=session_ids, task_ids=task_ids, result=report
        )

    async def _run_fire_and_forget(
        self, agent_cls, agent_id, items, prompts, input_instance,
        conversation_id, working_directory, parent_session_id,
    ) -> SubAgentSwarm_output_schema:
        session_ids: list[str] = []
        task_ids: list[int] = []
        failures: list[str] = []
        for item, prompt in zip(items, prompts):
            try:
                dispatched = await dispatch_subagent(
                    agent_cls,
                    agent_id=agent_id,
                    query=prompt,
                    context=input_instance.context,
                    is_wait=False,
                    conversation_id=conversation_id,
                    working_directory=working_directory,
                    parent_session_id=parent_session_id,
                )
                session_ids.append(dispatched.session_id)
                task_ids.append(dispatched.task_id)
            except Exception as e:
                session_ids.append("error")
                task_ids.append(-1)
                failures.append(f"- {_summarize_item(item)}: {e}")

        lines = [
            f"Swarm 已异步派发 {len(items)} 个子任务 (agent_id={agent_id})，",
            "可用 get_subagent_report 按 session_id 查询进度与结果。",
            "session_ids:",
        ]
        lines.extend(f"- {sid}" for sid in session_ids)
        if failures:
            lines.append("派发失败项:")
            lines.extend(failures)
        return SubAgentSwarm_output_schema(
            session_ids=session_ids, task_ids=task_ids, result="\n".join(lines)
        )

    def get_subagents(self) -> list[str]:
        return []


def get_class():
    return SubAgentSwarm
