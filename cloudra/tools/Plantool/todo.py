"""TodoWrite：per-agent 任务清单工具。

对齐 Claude Code 的 TodoWrite 语义：整体替换式更新，帮助模型在长任务中
显式跟踪进度，也让用户（经 session 事件）看到 agent 的计划与推进。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.tools.Plantool._store import agent_store_path, load_json, save_json

_VALID_STATUSES = ("pending", "in_progress", "done")


class TodoItem(BaseModel):
    """单条任务项。更新已有任务时必须带上原 id，否则会被当成新任务。"""

    content: str = Field(description="任务内容，一句话描述。")
    status: Literal["pending", "in_progress", "done"] = Field(
        default="pending",
        description="任务状态：pending（未开始）/ in_progress（进行中）/ done（已完成）。",
    )
    id: str = Field(
        default="",
        description="任务 id。新建任务留空（自动分配）；更新已有任务时填原 id。",
    )


class TodoWrite_input_schema(input_schema):
    todos: list[TodoItem] = Field(
        description="完整任务清单（整体替换，不是增量）。传空列表可清空清单。"
    )


class TodoWrite_output_schema(output_schema):
    result: str = Field(description="工具执行结果。")
    todos: list[dict] = Field(description="更新后的完整任务清单。")


class TodoWrite(Tool):
    tool_id: str = 't-40'
    tool_name: str = 'todo_write'
    tool_description: str = (
        "管理工作清单（todo list），用于跟踪多步骤任务的进度。\n"
        "适用场景：任务需要 3 步以上或多轮工具调用时，先建立清单再逐项推进；"
        "每完成一项立即更新状态，开始新任务前把对应项置为 in_progress。"
        "同一时刻只允许一项为 in_progress。\n"
        "注意：每次调用整体替换清单（更新已有任务需带上原 id）；"
        "单步即可完成的简单任务不要使用本工具。"
    )
    input_schema: Any = TodoWrite_input_schema
    output_schema: Any = TodoWrite_output_schema
    subagent: Agent = None

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
            return "（清单为空）"
        icon = {"pending": "○", "in_progress": "◐", "done": "●"}
        lines = [
            f"{icon.get(t['status'], '?')} [{t['id']}] {t['content']} ({t['status']})"
            for t in todos
        ]
        done = sum(1 for t in todos if t["status"] == "done")
        return "\n".join(lines) + f"\n进度: {done}/{len(todos)} 已完成"

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
            result=f"任务清单已更新（共 {len(todos)} 项）：\n{formatted}",
            todos=todos,
        )


def get_class():
    return TodoWrite
