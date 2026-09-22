"""TodoWrite：per-agent 任务清单工具。

对齐 Claude Code 的 TodoWrite 语义：整体替换式更新，帮助模型在长任务中
显式跟踪进度，也让用户（经 session 事件）看到 agent 的计划与推进。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from cloudra.base.session_class import Session
from cloudra.base.tool_actor import ToolActorContext
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.tools.Plantool._store import agent_store_path, load_json, save_json

_VALID_STATUSES = ("pending", "in_progress", "done")


class TodoItem(BaseModel):
    """单条任务项。更新已有任务时必须带上原 id，否则会被当成新任务。"""

    content: str = Field(description="Task content, one sentence.")
    status: Literal["pending", "in_progress", "done"] = Field(
        default="pending",
        description="Task status: pending (not started) / in_progress (in progress) / done (completed).",
    )
    id: str = Field(
        default="",
        description="Task id. Leave empty for a new task (auto-assigned); pass the original id when updating an existing task.",
    )


class TodoWrite_input_schema(input_schema):
    todos: list[TodoItem] = Field(
        description="Full task list (wholesale replace, not incremental). Pass an empty list to clear the list."
    )


class TodoWrite_output_schema(output_schema):
    result: str = Field(description="Tool result.")
    todos: list[dict] = Field(description="Updated full task list.")


class TodoWrite(Tool):
    tool_id: str = 't-40'
    tool_name: str = 'todo_write'
    tool_description: str = (
        "Manage the todo list used to track progress on multi-step tasks.\n"
        "Use when: the task needs 3+ steps or multiple tool-call rounds — build the list first, then work through it; "
        "update status as soon as an item is done, and set the next item to in_progress before starting it. "
        "Only one item may be in_progress at a time.\n"
        "Note: each call replaces the whole list (include the original id when updating an existing item); "
        "do not use this tool for a simple one-step task."
    )
    input_schema: Any = TodoWrite_input_schema
    output_schema: Any = TodoWrite_output_schema
    subagent: ToolActorContext | None = None

    @staticmethod
    def _normalize(todos: list[TodoItem], existing: list[dict]) -> list[dict]:
        """校验并规范化清单：分配缺失 id、限制 in_progress 唯一。"""
        used_ids = {item.get("id") for item in existing}
        normalized = []
        counter = len(existing)
        seen_in_progress = False
        for item in todos:
            entry = {"content": item.content, "status": item.status, "id": item.id}
            if not entry["id"]:
                counter += 1
                while f"t{counter}" in used_ids:
                    counter += 1
                entry["id"] = f"t{counter}"
            used_ids.add(entry["id"])
            # 软约束：多于一项 in_progress 时，只保留第一项，其余降级 pending
            if entry["status"] == "in_progress":
                if seen_in_progress:
                    entry["status"] = "pending"
                else:
                    seen_in_progress = True
            normalized.append(entry)
        return normalized

    @staticmethod
    def _format(todos: list[dict]) -> str:
        """渲染为可读清单文本（回传给 LLM，也可供前端直接展示）。"""
        if not todos:
            return "(empty list)"
        icon = {"pending": "○", "in_progress": "◐", "done": "●"}
        lines = [
            f"{icon.get(t['status'], '?')} [{t['id']}] {t['content']} ({t['status']})"
            for t in todos
        ]
        done = sum(1 for t in todos if t["status"] == "done")
        return "\n".join(lines) + f"\nProgress: {done}/{len(todos)} done"

    async def tool_call(
        self,
        user_input: TodoWrite_input_schema,
        session: Session,
    ) -> TodoWrite_output_schema:
        path = agent_store_path(self.subagent, "todos.json")
        existing = load_json(path, default=[])
        todos = self._normalize(user_input.todos, existing)
        save_json(path, todos)

        formatted = self._format(todos)
        await self.record_session_event(session, "todo_updated", {"todos": todos})
        return TodoWrite_output_schema(
            result=f"Todo list updated ({len(todos)} items):\n{formatted}",
            todos=todos,
        )


def get_class():
    return TodoWrite
