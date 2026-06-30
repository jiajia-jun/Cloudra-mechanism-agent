from pydantic import BaseModel, Field
from typing import Any
import os
from pydantic_core import PydanticUndefined
from cloudra.subagents import Subagent_hash
from cloudra.session_class import Session
# HACK: 这里原本缺少 import，属于历史遗留问题；get_tools_lst 定义在 tools/__init__.py
from cloudra.tools import get_tools_lst
from cloudra.tools.core.permission_model import Permission, check_permission


def get_tools() -> list[dict]:
    '''
    将tools模块中的对象加载为 OpenAI function 格式的 dict 列表。
    供 agent.py 的 llm_call() 直接传入 tools 参数。
    '''
    tools = get_tools_lst()
    tools_list = []
    for tool in tools:
        # NOTE: tool_schema_json 已改为实例方法（原为类方法），因此 tool 必须是实例对象。
        # 这会让 __init__ 中动态拼接的 tool_description 真正进入 LLM 可见的 schema。
        tool_json = tool.tool_schema_json()
        tools_list.append(tool_json)
    return tools_list


class input_schema(BaseModel):
    '''
    工具输入模式基类，定义工具需要的输入参数和格式。

    子类用法示例：
        class MyInput(input_schema):
            query: str = Field(description="搜索关键词")
            max_results: int = Field(default=10, description="最大返回条数")

    通过 to_parameters_schema() 可自动生成符合 OpenAI Function Calling 规范的 parameters 字典。
    '''

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
        return parameters

    @classmethod
    def from_args(cls, arg_dict: dict) -> "input_schema":
        '''从 LLM 返回的 arguments dict 构造输入实例，带 Pydantic 类型校验。'''
        return cls(**arg_dict)

    def toClass(self, arg_dict: dict) -> "input_schema":
        '''
        兼容旧接口，供 reAct.py 调用。
        实际调用链通常为 tool.input_schema.toClass(tool_args)，此时 self 为 input_schema 子类本身。
        '''
        # 当通过类调用时（如 TextReader_input_schema.toClass(args)），self 即为类对象
        if isinstance(self, type) and issubclass(self, input_schema):
            return self(**arg_dict)
        return self.__class__(**arg_dict)

    def toJson(self) -> dict:
        '''实例序列化为 dict，用于日志或上下文回传。'''
        return self.model_dump(mode="json")


class output_schema(BaseModel):
    '''
    工具输出模式基类，定义工具输出的格式。
    子类按普通 Pydantic Model 声明字段即可。
    '''

    def toJson(self) -> dict:
        return self.model_dump(mode="json")


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
        工具执行失败时抛出包含工具名的 RuntimeError，由 reAct.act_result() 统一捕获并回传给 LLM。
        '''
        try:
            return await self.tool_call(user_input, session)
        except Exception as e:
            error_msg = f"【工具执行异常】{self.tool_name}: {str(e)}"
            raise RuntimeError(error_msg) from e 

    async def ensure_safety(self, session: Session, details: str) -> tuple[bool, str]:
        '''
        安全检查：如果工具被标记为 destructive，则必须经过 Coordinator 审批。
        返回 (是否通过, 拒绝原因)。通过时拒绝原因为空字符串。
        '''
        from cloudra.config import get_config
        db_path = os.path.join(get_config().data_dir, 'tasks', 'database.db')
        
        # 获取当前 Agent 名称
        agent_name = self.subagent.name if self.subagent else "Unknown Agent"
        
        # 格式化详细信息
        full_details = f"【发起 Agent】: {agent_name}\n{details}"
        
        print(f"\n\033[91m[安全审计]\033[0m 正在申请危险操作审批...\n{full_details}")
        
        return await self.request_approval(db_path, session.id, full_details)

    async def request_approval(self, db_path: str, session_id: str, details: str) -> tuple[bool, str]:
        import sqlite3
        import asyncio
        import time

        con = sqlite3.connect(db_path, timeout=10)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO approvals (session_id, details, state, denial_reason) VALUES (?, ?, ?, ?)",
            (session_id, details, 'pending', '')
        )
        approval_id = cur.lastrowid
        con.commit()
        con.close()

        # 轮询等待审批结果
        while True:
            await asyncio.sleep(2)
            con = sqlite3.connect(db_path, timeout=10)
            cur = con.cursor()
            cur.execute("SELECT state, denial_reason FROM approvals WHERE id = ?", (approval_id,))
            row = cur.fetchone()
            con.close()

            if row:
                state, denial_reason = row
                if state == 'approved':
                    print(f"\033[92m[安全审计]\033[0m 审批通过。")
                    return True, ''
                elif state == 'denied':
                    reason = denial_reason or ''
                    if reason:
                        print(f"\033[91m[安全审计]\033[0m 审批拒绝。原因: {reason}")
                    else:
                        print(f"\033[91m[安全审计]\033[0m 审批拒绝。")
                    return False, reason
            
            # 可选：在终端提示等待中
            # print(".", end="", flush=True)

    @classmethod
    def _get_field_default(cls, field_name: str):
        '''获取类字段的默认值，兼容 Pydantic v2（类级别无法直接访问普通字段）。'''
        field = cls.model_fields.get(field_name)
        if field and field.default is not PydanticUndefined:
            return field.default
        return None

    def tool_schema_json(self) -> dict:
        '''
        返回标准 OpenAI function 格式，可直接用于 client.chat.completions.create(..., tools=[...])。
        优先读取实例级别的 tool_description，使动态生成的描述能够生效。
        '''
        # HACK: 这里用 getattr + or fallback 链是因为 Pydantic v2 的类字段默认值在实例上可能
        # 被 shadow，但某些情况下实例属性又还没覆盖。动态 description（如 Bashtools 的权限列表、
        # GetSkill 的 skills 列表）必须在 __init__ 之后才能确定，因此必须是实例方法而非类方法。
        # 如果后续有更好方式（如 descriptor / property），可替换掉这个 ugly fallback。
        description = getattr(self, 'tool_description', '') or self._get_field_default('tool_description') or ''
        return {
            "type": "function",
            "function": {
                "name": getattr(self, 'tool_name', '') or self._get_field_default('tool_name') or '',
                "description": description,
                "parameters": (self._get_field_default('input_schema') or input_schema).to_parameters_schema(),
            }
        }

    def toJson(self) -> dict:
        '''
        实例级序列化，主要用于日志或调试。
        若需获取 OpenAI schema，请使用类方法 tool_schema_json()。
        '''
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "tool_description": self.tool_description,
        }

    @classmethod
    def build_input(cls, arg_dict: dict) -> input_schema:
        '''
        将 LLM 返回的参数字典转换为 input_schema 实例。
        供 reAct.py 调用，替代原有的 tool.input_schema.toClass(tool_args)。
        '''
        schema_cls = cls._get_field_default('input_schema') or input_schema
        return schema_cls.from_args(arg_dict)
