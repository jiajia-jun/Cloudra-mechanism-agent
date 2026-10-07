"""SubAgentSwarm (t-47)：对同一子 Agent 角色批量并行派发多个不同任务。

执行由 runtime_v2 的 subagent_bridge 按工具名拦截实现（{{item}} 展开 +
并发上限 + 聚合）；本类只保留 schema 与描述。
"""

from typing import Any

from pydantic import ConfigDict, Field, model_validator

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.runtime_v2.roles import builtin_role_directory

MIN_ITEMS = 2
MAX_ITEMS = 128

description = (
    "Dispatch many distinct tasks in parallel to the same sub-agent role (swarm). The Coordinator expands a template once per item in items, starts one same-role instance each, runs them concurrently, and aggregates all results.\n"
    "Important guidelines:\n"
    "- **Placeholder**: prompt_template must contain the {{item}} placeholder; each task is expanded from it; expanded task descriptions must all differ.\n"
    "- **Assignment contract**: give absolute working paths, inputs, scope boundaries, expected output, evidence, and done criteria. Do not prescribe tool whitelists or step-by-step tool sequences; specialists choose methods within their existing permissions.\n"
    "- **AgentHub**: parallel subtasks can share findings/questions/answers via `agent_hub` and address someone with to_agent (posts are public; addressees and authors of replied-to posts are notified); when dispatching overlapping work, tell them to check the hub first and post conclusions to the hub.\n"
    "- **Concurrency cap**: max_concurrency > 0 limits how many sub-agent instances run at once; default 0 means unlimited.\n"
    "- **role_id**: use a semantic role id, such as explorer or small_mol; "
    "instances of that role run in parallel, each with its own session and plan store.\n"
    + builtin_role_directory()
)


class SubAgentSwarm_input_schema(input_schema):
    model_config = ConfigDict(extra="forbid", strict=True)

    role_id: str = Field(description="Semantic role id from the role directory, e.g. explorer or small_mol")
    prompt_template: str = Field(
        description=(
            "Task template; must contain the {{item}} placeholder, expanded per item in items. "
            "Include: goal, required absolute paths/input data, scope boundaries, output format, evidence, and done criteria. Do not prescribe tool whitelists or step-by-step tool sequences."
        )
    )
    items: list[str] = Field(
        min_length=MIN_ITEMS,
        max_length=MAX_ITEMS,
        description=f"List of task items to run in parallel ({MIN_ITEMS}–{MAX_ITEMS} items); each replaces {{{{item}}}} in the template to form one subtask."
    )
    context: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Initial context injected into every subtask. "
            "Each element must be a standard message dict {\"role\": \"user\"/\"system\"/\"assistant\", \"content\": \"...\"}; "
            "do not pass plain strings."
        )
    )
    is_wait: bool = Field(
        default=True,
        description=(
            "Whether to wait for all subtasks and aggregate results. If False, fire the tasks and return "
            "immediately: with max_concurrency=0 all session_ids are returned at once; with "
            "max_concurrency>0 a group_id is returned instead (subtasks report progress/completion via agent_hub "
            "or upon finish, or inspect get_subagent_report with that group_id)."
        )
    )
    max_concurrency: int = Field(
        default=0,
        ge=0,
        description="Max number of sub-agent instances running at once. 0 means unlimited; >0 uses a semaphore."
    )

    @model_validator(mode="after")
    def validate_tasks(self):
        if "{{item}}" not in self.prompt_template:
            raise ValueError("prompt_template must contain the {{item}} placeholder")
        if len(set(self.items)) != len(self.items):
            raise ValueError("items must expand to distinct task descriptions")
        return self


class SubAgentSwarm_output_schema(output_schema):
    is_success: bool = Field(default=False, description="Whether the swarm dispatch succeeded")
    session_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Session ID of each subtask (same order as items). Populated when is_wait=True, and when "
            "is_wait=False with max_concurrency=0. Empty for grouped dispatch (is_wait=False with "
            "max_concurrency>0): children spawn lazily under the concurrency cap, so per-item child "
            "session ids are only available later via get_subagent_report(group_id=...)."
        ),
    )
    group_id: str = Field(
        default="",
        description="Launch group ID; returned only for grouped dispatch (is_wait=False with max_concurrency>0)",
    )
    pending_count: int = Field(default=0, description="Items still queued at dispatch time (grouped dispatch only)")
    result: str = Field(default="", description="Aggregated report (is_wait=True) or dispatch receipt (is_wait=False)")


class SubAgentSwarm(Tool):
    tool_id: str = 't-47'
    tool_name: str = 'subagent_swarm'
    tool_description: str = description
    input_schema: Any = SubAgentSwarm_input_schema
    output_schema: Any = SubAgentSwarm_output_schema
    subagent: ToolActorContext | None = None

    def is_manage(self) -> bool:
        return True

    def _error(self, message: str) -> SubAgentSwarm_output_schema:
        return SubAgentSwarm_output_schema(result=message)

    async def tool_call(
        self,
        input_instance: SubAgentSwarm_input_schema,
        session: Session
    ) -> SubAgentSwarm_output_schema:
        # Legacy 派发已删除；runtime_v2 的 LegacyToolExecutor 在执行前按工具名
        # 拦截到 subagent_bridge，此 body 只是兜底。
        return self._error(
            "[System error] SubAgentSwarm is handled by runtime_v2; the legacy dispatch path no longer exists."
        )
