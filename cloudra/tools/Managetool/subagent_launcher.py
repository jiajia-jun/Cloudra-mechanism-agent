from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.subagents import Subagent_hash
from cloudra.tools.Managetool._subagent_dispatch import (
    dispatch_subagent,
    run_subagent_in_process,
)

# 向后兼容：历史实现中该协程定义在本模块，保留别名以防外部引用。
_run_subagent_in_process = run_subagent_in_process

description = (
    "Launch a sub-agent to run a specific task. The Coordinator may split a complex job into subtasks.\n"
    "Important guidelines:\n"
    "- **Absolute paths**: you must provide the working directory's absolute path in query or context.\n"
    "- **Safety**: a security audit is enabled. explorer is read-only; writer may write files but cannot run scripts or destructive operations; the other sub-agents (researcher, small_mol, md, dft, experiment, env) may write/script/delete. Instruct them to spell out intent, blast radius, and rollback in Thought to aid approval.\n"
    "- **Task definition**: the task description must be extremely specific: name the tools to use, and explicitly forbid tools unrelated to the task.\n"
    "- **AgentHub**: sub-agents can share findings/questions/answers with other parallel Agents via `agent_hub`, and can address someone with to_agent (posts are public; addressees and authors of replied-to posts are notified). When dispatching overlapping work, tell them to check the hub first and post conclusions to the hub.\n"
    "- **agent_id is a stable role id**: pass ids such as a-1, a-2 — not names like explorer or writer; the same role id may be dispatched repeatedly for different tasks to run in parallel; for batch parallelism prefer SubAgentSwarm.\n"
    "Available sub-agents:\n"
    "1. explorer (a-1): explore + review. Map project structure and locate files; read-only review of code/docs/data with an evidence-backed report. Read-only.\n"
    "2. writer (a-2): papers and documents. Write reports, papers, docs. May write files, but cannot run scripts or destructive operations; must pass the security audit.\n"
    "3. researcher (a-3): literature. Academic search, method breakdown, literature comparison. Full permissions; dangerous ops need strict review.\n"
    "4. small_mol (a-4): small-molecule compute. Gaussian/ORCA molecular/cluster QM: conformers, TS, spectra, energies.\n"
    "5. md (a-5): molecular dynamics. GROMACS/LAMMPS system build, equilibration, sampling, and trajectory analysis.\n"
    "6. dft (a-6): first-principles. VASP/CP2K periodic systems: bulk, surfaces, defects, electronic properties.\n"
    "7. experiment (a-7): experimental design. DOE, controls, characterization matrix, safety assessment, and failure diagnosis.\n"
    "8. env (a-8): environment management. Dependency install, conda/venvs, build config, HPC job environments. Full permissions; strict review."
)


class SubAgentLauncher_input_schema(input_schema):
    agent_id: str = Field(description="Unique id of the sub-agent to launch, e.g. a-1, a-2, a-3 — not a name such as explorer or writer")
    query: str = Field(
        description=(
            "Task description. Write only what this task needs, not the sub-agent's identity (already injected via prompt). "
            "Must include: goal, required absolute paths/input data, allowed tools, forbidden tools, output format, and done criteria."
        )
    )
    context: list = Field(
        default_factory=list,
        description=(
            "Initial context messages for the sub-agent. "
            "Each element must be a standard message dict {\"role\": \"user\"/\"system\"/\"assistant\", \"content\": \"...\"}; "
            "do not pass plain strings."
        )
    )
    is_wait: bool = Field(
        default=False,
        description="Whether to wait until the sub-agent finishes. True blocks until the task completes and returns the result; False fires the task and returns immediately."
    )


class SubAgentLauncher_output_schema(output_schema):
    session_id: str = Field(description="Sub-agent Session ID")
    act_agent: str = Field(description="Name of the Agent that actually ran the task")
    result: str = Field(description="Sub-agent's final result")


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
                result=f"[System error] Failed to load sub-agent mapping: {str(e)}"
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
        parent_mode = getattr(self.subagent, 'orchestration_mode', 'standard')

        dispatched = await dispatch_subagent(
            agent_cls,
            agent_id=agent_id,
            query=input_instance.query,
            context=input_instance.context,
            is_wait=input_instance.is_wait,
            conversation_id=conversation_id,
            working_directory=working_directory,
            parent_session_id=parent_session_id,
            parent_orchestration_mode=parent_mode,
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
