from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent

description = (
    "Launch a sub-agent to run a specific task. The Coordinator may split a complex job into subtasks.\n"
    "Important guidelines:\n"
    "- **Absolute paths**: you must provide the working directory's absolute path in query or context.\n"
    "- **Safety**: a security audit is enabled. explorer is read-only; writer may write files but cannot run scripts or destructive operations; the other sub-agents (researcher, small_mol, md, dft, experiment, env) may write/script/delete. Instruct them to spell out intent, blast radius, and rollback in Thought to aid approval.\n"
    "- **Task definition**: the task description must be extremely specific: name the tools to use, and explicitly forbid tools unrelated to the task.\n"
    "- **AgentHub**: sub-agents can share findings/questions/answers with other parallel Agents via `agent_hub`, and can address someone with to_agent (posts are public; addressees and authors of replied-to posts are notified). When dispatching overlapping work, tell them to check the hub first and post conclusions to the hub.\n"
    "- **agent_id is a stable role id**: pass ids such as a-1, a-2 — not names like explorer or writer; the same role id may be dispatched repeatedly for different tasks to run in parallel; for batch parallelism prefer subagent_swarm.\n"
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
    is_success: bool = Field(default=False, description="Whether the dispatch succeeded")
    session_id: str = Field(description="Sub-agent Session ID")
    act_agent: str = Field(description="Name of the Agent that actually ran the task")
    result: str = Field(description="Sub-agent's final result")


class SubAgentLauncher(Tool):
    tool_id: str = 't-0'
    tool_name: str = 'subagent_launcher'
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
        # Legacy 派发已删除；runtime_v2 的 LegacyToolExecutor 在执行前按工具名
        # 拦截到 subagent_bridge，此 body 只是兜底。
        return SubAgentLauncher_output_schema(
            is_success=False,
            session_id="error",
            act_agent="none",
            result="[System error] SubAgentLauncher is handled by runtime_v2; the legacy dispatch path no longer exists.",
        )

    def get_subagents(self) -> list[str]:
        return []


def get_class():
    return SubAgentLauncher
