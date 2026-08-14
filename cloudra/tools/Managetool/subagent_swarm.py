"""SubAgentSwarm (t-47)：对同一子 Agent 角色批量并行派发多个不同任务。

复用 _subagent_dispatch 的派发核心（与 t-0 同一套实例化/落库/执行/回取逻辑），
逐项展开 prompt_template 中的 {{item}} 占位符后并发派发，聚合结果返回。
"""

import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.persistence.database import ConversationDB
from cloudra.subagents import Subagent_hash
from cloudra.tools.Managetool._subagent_dispatch import (
    dispatch_subagent,
    fetch_subagent_outcome,
)

MIN_ITEMS = 2
MAX_ITEMS = 128

_STATE_LABELS = {
    "done": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
}

description = (
    "Dispatch many distinct tasks in parallel to the same sub-agent role (swarm). The Coordinator expands a template once per item in items, starts one same-role instance each, runs them concurrently, and aggregates all results.\n"
    "Important guidelines:\n"
    "- **Placeholder**: prompt_template must contain the {{item}} placeholder; each task is expanded from it; expanded task descriptions must all differ.\n"
    "- **Absolute paths and tool bounds**: the template or context must give the working directory's absolute path, and must name allowed and forbidden tools.\n"
    "- **AgentHub**: parallel subtasks can share findings/questions/answers via `agent_hub` and address someone with to_agent (posts are public; addressees and authors of replied-to posts are notified); when dispatching overlapping work, tell them to check the hub first and post conclusions to the hub.\n"
    "- **Concurrency cap**: max_concurrency > 0 limits how many sub-agent instances run at once; default 0 means unlimited.\n"
    "- **agent_id**: pass ids such as a-1, a-2 — not names like explorer or writer; multiple instances of the same agent_id run in parallel, each with its own session and plan store.\n"
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


class SubAgentSwarm_input_schema(input_schema):
    agent_id: str = Field(description="Unique id of the sub-agent to dispatch in parallel, e.g. a-1, a-4 — not a name such as explorer or small_mol")
    prompt_template: str = Field(
        description=(
            "Task template; must contain the {{item}} placeholder, expanded per item in items. "
            "The template must include: goal, required absolute paths/input data, allowed tools, forbidden tools, output format, and done criteria."
        )
    )
    items: list[str] = Field(
        description=f"List of task items to run in parallel ({MIN_ITEMS}–{MAX_ITEMS} items); each replaces {{{{item}}}} in the template to form one subtask."
    )
    context: list = Field(
        default_factory=list,
        description=(
            "Initial context injected into every subtask. "
            "Each element must be a standard message dict {\"role\": \"user\"/\"system\"/\"assistant\", \"content\": \"...\"}; "
            "do not pass plain strings."
        )
    )
    is_wait: bool = Field(
        default=True,
        description="Whether to wait for all subtasks and aggregate results. If False, fire the tasks and immediately return all session_ids."
    )
    max_concurrency: int = Field(
        default=0,
        description="Max number of sub-agent instances running at once. 0 means unlimited; >0 uses a semaphore."
    )


class SubAgentSwarm_output_schema(output_schema):
    session_ids: list[str] = Field(description="Session ID of each subtask (same order as items)")
    task_ids: list[int] = Field(description="Task ID of each subtask (same order as items)")
    result: str = Field(description="Aggregated report (is_wait=True) or dispatch receipt (is_wait=False)")


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
                "Error: prompt_template must contain the {{item}} placeholder; "
                "each subtask substitutes it with the corresponding item."
            )

        items = [str(i) for i in input_instance.items]
        if not (MIN_ITEMS <= len(items) <= MAX_ITEMS):
            return self._error(
                f"Error: items count must be between {MIN_ITEMS} and {MAX_ITEMS}, got {len(items)}."
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
                "Error: after expanding the following items, the task description duplicates another item; "
                "deduplicate or change the template: "
                f"{duplicate_items}"
            )

        try:
            agent_hash = Subagent_hash()
        except Exception as e:
            return self._error(f"[System error] Failed to load sub-agent mapping: {str(e)}")

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
        parent_mode = getattr(self.subagent, 'orchestration_mode', 'standard')

        # ---- 派发 ----
        if input_instance.is_wait:
            return await self._run_waiting(
                agent_cls, agent_id, items, prompts, input_instance,
                conversation_id, working_directory, parent_session_id, parent_mode,
            )
        return await self._run_fire_and_forget(
            agent_cls, agent_id, items, prompts, input_instance,
            conversation_id, working_directory, parent_session_id, parent_mode,
        )

    async def _run_waiting(
        self, agent_cls, agent_id, items, prompts, input_instance,
        conversation_id, working_directory, parent_session_id, parent_mode,
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
                    parent_orchestration_mode=parent_mode,
                    semaphore=semaphore,
                )
            except Exception as e:
                return None, "failed", f"[System error] Dispatch or execution error: {e}"
            state, _result = await fetch_subagent_outcome(db, dispatched.task_id, dispatched.session_id)
            return dispatched, state, dispatched.result

        outcomes = await asyncio.gather(*(run_one(p) for p in prompts))

        session_ids: list[str] = []
        task_ids: list[int] = []
        sections: list[str] = []
        total = len(items)
        succeeded = 0
        for index, (item, (dispatched, state, result)) in enumerate(zip(items, outcomes), start=1):
            label = _STATE_LABELS.get(state, f"unknown({state})")
            if state == "done":
                succeeded += 1
            session_id = dispatched.session_id if dispatched else "error"
            session_ids.append(session_id)
            task_ids.append(dispatched.task_id if dispatched else -1)
            sections.append(
                f"=== Item {index}/{total}: {_summarize_item(item)} ===\n"
                f"status: {label}\n"
                f"session_id: {session_id}\n"
                f"{result}"
            )

        report = (
            f"Swarm finished: {succeeded}/{total} succeeded (agent_id={agent_id})\n\n"
            + "\n\n".join(sections)
        )
        return SubAgentSwarm_output_schema(
            session_ids=session_ids, task_ids=task_ids, result=report
        )

    async def _run_fire_and_forget(
        self, agent_cls, agent_id, items, prompts, input_instance,
        conversation_id, working_directory, parent_session_id, parent_mode,
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
                    parent_orchestration_mode=parent_mode,
                )
                session_ids.append(dispatched.session_id)
                task_ids.append(dispatched.task_id)
            except Exception as e:
                session_ids.append("error")
                task_ids.append(-1)
                failures.append(f"- {_summarize_item(item)}: {e}")

        lines = [
            f"Swarm asynchronously dispatched {len(items)} subtasks (agent_id={agent_id});",
            "use get_subagent_report with session_id to query progress and results.",
            "session_ids:",
        ]
        lines.extend(f"- {sid}" for sid in session_ids)
        if failures:
            lines.append("Failed dispatches:")
            lines.extend(failures)
        return SubAgentSwarm_output_schema(
            session_ids=session_ids, task_ids=task_ids, result="\n".join(lines)
        )

    def get_subagents(self) -> list[str]:
        return []


def get_class():
    return SubAgentSwarm
