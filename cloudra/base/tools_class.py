from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from pydantic import BaseModel, ConfigDict

from cloudra.base.session_class import Session
from cloudra.persistence.database import ConversationDB, get_database_path
from cloudra.tools.core.permission_model import Permission

if TYPE_CHECKING:
    from cloudra.infra.yolo_guard import YoloGuard

# runtime_v2 的审批钩子：LegacyToolExecutor 在执行工具前总是设置；
# 未设置即生产外路径（v1/CLI/Flet 已删除），request_approval 直接抛错。
# 签名: async (**fields) -> tuple[bool, str]，字段同 request_approval 的关键字参数。
_APPROVAL_HANDLER: ContextVar[
    Optional[Callable[..., Awaitable[tuple[bool, str]]]]
] = ContextVar("cloudra_approval_handler", default=None)


@contextmanager
def use_approval_handler(handler: Callable[..., Awaitable[tuple[bool, str]]]):
    """Scope a v2 approval handler to one tool execution (per-task isolation)."""
    token = _APPROVAL_HANDLER.set(handler)
    try:
        yield
    finally:
        _APPROVAL_HANDLER.reset(token)


def _tool_db_path(subagent) -> str:
    """根据 tool 关联的 Agent 返回对应 conversation 的数据库路径。"""
    conv_id = getattr(subagent, 'conversation_id', 'default') if subagent else 'default'
    return get_database_path(conv_id)


class input_schema(BaseModel):
    '''
    工具输入模式基类，定义工具需要的输入参数和格式。

    子类用法示例：
        class MyInput(input_schema):
            query: str = Field(description="搜索关键词")
            max_results: int = Field(default=10, description="最大返回条数")

    通过 to_parameters_schema() 可自动生成符合 OpenAI Function Calling 规范的 parameters 字典。
    '''

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def to_parameters_schema(cls) -> dict:
        '''
        生成符合 OpenAI Function Calling 的 parameters 字典。
        基于 Pydantic model_json_schema() 微调：
        - properties / required 已由 Pydantic 根据字段声明自动生成
        - 强制附加 additionalProperties: false，防止 LLM 传入未定义字段
        '''
        schema = cls.model_json_schema()
        parameters = {
            "type": "object",
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
            "additionalProperties": False,
        }
        if "$defs" in schema:
            parameters["$defs"] = schema["$defs"]
        return parameters

class output_schema(BaseModel):
    '''
    工具输出模式基类，定义工具输出的格式。
    子类按普通 Pydantic Model 声明字段即可。
    '''

class Tool(BaseModel):
    '''
    工具基类。所有具体工具应继承此类。

    关于 input_schema / output_schema：
    - 这里存放的是具体的 schema 类（如 TextReader_input_schema），而非实例。
    - 使用 Any 类型并开启 arbitrary_types_allowed，避免 Pydantic 对类对象做字段校验。
    - 子模块中覆盖时必须带类型注解，例如：
          input_schema: Any = TextReader_input_schema
    '''
    model_config = {"arbitrary_types_allowed": True}

    # 唯一标识符
    tool_id: str = ''

    # 工具名称（即 OpenAI function.name）
    tool_name: str = ''

    # 工具描述。改造后应仅保留【功能描述】+【使用场景】，不再包含参数细节。
    # 参数说明通过 input_schema 的 Field(description="...") 提供，自动生成到 parameters 中。
    tool_description: str = ''

    # 工具的输入模式类（存放类对象，非实例）
    input_schema: Any = input_schema

    # 工具的输出模式类（存放类对象，非实例）
    output_schema: Any = output_schema

    # 引用调用该工具的 Agent 实例
    subagent: Any = None

    def is_read(self) -> bool:
        return False

    def is_write(self) -> bool:
        return False

    def is_manage(self) -> bool:
        return False

    def is_script(self) -> bool:
        return False

    def is_destructive(self) -> bool:
        return False

    def tool_permission_all(self) -> Permission:
        """Return Permission flags for this tool."""
        perms = Permission.NONE
        if self.is_read():
            perms |= Permission.READ
        if self.is_write():
            perms |= Permission.WRITE
        if self.is_manage():
            perms |= Permission.MANAGE
        if self.is_script():
            perms |= Permission.SCRIPT
        if self.is_destructive():
            perms |= Permission.DESTRUCTIVE
        return perms

    async def tool_call(self, user_input: input_schema, session: Session) -> output_schema:
        '''
        调用工具。子类必须重写此方法。
        执行结果以 output_schema 实例返回。
        '''
        raise NotImplementedError("子类必须实现 tool_call 方法")

    async def safe_call(self, user_input: input_schema, session: Session) -> output_schema:
        '''
        带有通用异常捕获的工具调用包装器。
        工具执行失败时抛出包含工具名的 RuntimeError，由 runtime_v2 执行边界记录和回传。
        '''
        try:
            return await self.tool_call(user_input, session)
        except Exception as e:
            error_msg = (
                f"[Tool error] {self.tool_name}: {str(e)}. "
                "Fix the arguments or use a different tool, then retry."
            )
            raise RuntimeError(error_msg) from e

    async def ensure_safety(
        self,
        session: Session,
        details: str,
        tool_args: dict | None = None,
    ) -> tuple[bool, str]:
        '''
        安全检查：如果工具被标记为 destructive，则必须经过审批。
        默认通过数据库等待用户审批；若启用了 YOLO 模式，则调用独立 Agent 自动判断。
        返回 (是否通过, 拒绝原因)。通过时拒绝原因为空字符串。
        '''
        from cloudra.infra.yolo_guard import YoloGuard, is_yolo_enabled

        risk_summary = next(
            (
                line.partition(":")[2].strip()
                for line in details.splitlines()
                if line.lower().startswith("action:") or line.startswith("【动作】")
            ),
            details.splitlines()[0] if details.splitlines() else "Dangerous tool call",
        )

        if is_yolo_enabled():
            guard = YoloGuard()
            return await self._yolo_judge(session, tool_args or {}, guard, risk_summary=risk_summary)

        candidate_diff = ""
        for marker in ("Unified Diff:\n", "【Unified Diff】:\n"):
            if marker in details:
                candidate_diff = details.partition(marker)[2]
                break

        return await self.request_approval(
            details,
            tool_name=self.tool_name,
            normalized_arguments=tool_args or {},
            risk_summary=risk_summary,
            candidate_diff=candidate_diff,
        )

    async def record_session_event(
        self,
        session: Session,
        event_type: str,
        data: dict,
    ) -> None:
        """尽力记录工具事件；遥测失败不能反向破坏工具主流程。"""
        from cloudra.services import session_store as _ss

        try:
            db = ConversationDB.from_path(_tool_db_path(self.subagent))
            await _ss.arecord_event(db, session.id, event_type, data)
        except Exception:
            pass

    async def _yolo_judge(
        self,
        session: Session,
        tool_args: dict,
        guard: 'YoloGuard',
        risk_summary: str = "",
    ) -> tuple[bool, str]:
        """调用 YoloGuard 做自动判断。"""
        approved, reason = await guard.judge(
            self.tool_name, tool_args, self.subagent, session, risk_summary=risk_summary
        )
        if approved:
            print("\033[92m[安全审计/YOLO]\033[0m 自动审批通过。")
            return True, ""
        else:
            reason_text = reason or "YOLO Agent 认为该操作存在风险"
            print(f"\033[91m[安全审计/YOLO]\033[0m 自动审批拒绝。原因: {reason_text}")
            return False, reason_text

    async def request_approval(
        self,
        details: str,
        *,
        tool_name: str = "",
        normalized_arguments: dict | None = None,
        risk_summary: str = "",
        candidate_diff: str = "",
    ) -> tuple[bool, str]:
        handler = _APPROVAL_HANDLER.get()
        if handler is None:
            # v1 时代"SQLite + 事件总线等待"的审批回退已随旧服务层删除。
            raise RuntimeError(
                "no approval handler installed: runtime_v2 LegacyToolExecutor always sets one"
            )
        # runtime_v2 上下文：审批请求与等待由内核 broker 承担，
        # 不碰 conversation SQLite。
        return await handler(
            details=details,
            tool_name=tool_name,
            normalized_arguments=normalized_arguments or {},
            risk_summary=risk_summary,
            candidate_diff=candidate_diff,
        )

    def tool_schema_json(self) -> dict:
        '''
        返回标准 OpenAI function 格式，可直接用于 client.chat.completions.create(..., tools=[...])。
        优先读取实例级别的 tool_description，使动态生成的描述能够生效。
        '''
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.tool_description,
                "parameters": self.input_schema.to_parameters_schema(),
            }
        }
