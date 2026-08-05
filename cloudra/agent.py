import hashlib
import json
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, PrivateAttr

from cloudra import __version__, events
from cloudra.config import get_config
from cloudra.context_manager import SUPERVISOR_ADVICE_MARKER, ContextManager
from cloudra.database import ConversationDB
from cloudra.llm_client import ChatResponse, LLMClient
from cloudra.runtime.prompt_assembler import (
    PromptAssembler,
    PromptAssembly,
    load_role_prompt,
)
from cloudra.runtime_profile import filter_tools_for_runtime
from cloudra.token_estimator import TokenEstimator
from cloudra.tools import ToolEntry, get_tools_lst
from cloudra.tools.core.permission_model import Permission, check_permission
from cloudra.tools_class import Tool

# todo 提醒注入间隔（推理轮数）：每 N 轮提醒一次模型读取任务清单
_TODO_REMIND_EVERY = 10

# 模型给出结论但未调用 stop 时，注入一次目标确认提醒（一次性 force）
_GOAL_CONFIRM_REMINDER = (
    "【系统】你刚刚给出了结论但没有调用 stop 工具。注意：任务只有在调用 stop "
    "工具后才会真正结束。请用 goal_set 重新确认目标与完成判据，或 todo_read 查看任务清单，"
    "判断目标是否真正达成：若已完成，调用 stop 并填入最终答案收尾；若未完成，继续推进。"
)


def load_prompt(agent_name: str) -> str:
    """兼容入口：调用时读取角色 prompt，不做模块级缓存。"""
    return load_role_prompt(agent_name)


class Agent(BaseModel):
    '''agent父类，用于定义各类agent属性：
    1.唯一标识符（id）
    2.agent名称(name)
    3.agent类型(type)
    4.agent使用模型（model）
    5.agent使用模型url（llm_site）
    6.agent使用模型key（_api_key）
    7.agent使用模型温度（temperature）
    8.agent使用模型最大token（max_tokens）
    9.agent使用模型top_p（top_p）
    10.agent使用模型频率惩罚（frequency_penalty）
    11.agent使用模型存在惩罚（presence_penalty）
    12.agent身份prompt（prompt）
    13.agent上下文管理器（context_manager）
    14.agent输出方式（is_stream）

    该类的其他方法:
    权限：has_write_permission，has_read_permission，script_run_permission，destructive_permission(均为布尔值输出)
    llm_call方法：调用llm，输出ChatResponse或ChatStream
    后续可能加入的方法：调用本地专用模型，不能通过openai接口，因此待定，可以上github上看看有没有开源的逆合成分析模型等
    '''
    model_config = {"arbitrary_types_allowed": True}

    #唯一标识符
    id: str

    #agent名称
    name: str

    #agent类型：coordinator,researcher,...other
    type: str

    #agent使用模型
    model: str

    #agent使用模型url
    llm_site: str

    #agent使用模型key
    _api_key: str

    #agent使用模型温度
    temperature: float = 0.7

    #agent使用模型最大token（生成限制）
    max_tokens: int

    #agent使用模型上下文窗口（用于上下文压缩阈值计算）
    context_window: int = 128000

    #agent使用模型top_p
    top_p: Optional[float] = None  # None = 不发送 top_p，用服务商默认值

    #agent使用模型频率惩罚
    frequency_penalty: float = 0.0

    #agent使用模型存在惩罚
    presence_penalty: float = 0.0

    # 可选的调用方身份 prompt 覆盖；None 时由 prompt_name 在请求期加载。
    prompt: Optional[str] = None

    # prompts/{prompt_name}.md 的动态角色来源。
    prompt_name: Optional[str] = None

    #目标赋予prompt，如：“你的任务是......”
    query: str

    is_stream: bool

    # 当前 Agent 使用的模型是否支持视觉输入（多模态）
    @property
    def supports_vision(self) -> bool:
        return False

    # 可选的会话级唯一标识。子 Agent 被启动时会被赋予独立的 session_id，
    # 用于在 ContextManager 中隔离同一 conversation 下的不同子任务上下文。
    session_id: Optional[str] = None

    # 上下文管理器：Agent 上下文的唯一真相来源
    context_manager: Optional[ContextManager] = None

    conversation_id: str

    # API 会话可独立指定目录，避免修改进程级 cwd 导致并发任务互相影响。
    working_directory: Optional[str] = None

    # LLM 传输层客户端（实例级缓存，惰性构造）：
    # 三级 fallback 的级别记忆（_curl_mode/_use_custom_headers）在其中维护
    _llm_client: Optional[LLMClient] = None

    # 工具 schema 列表缓存：工具集与本 Agent 权限在进程内是静态的，
    # 无需每个推理步骤都重新实例化全部工具并重新生成 pydantic schema。
    _tools_schema_cache: Optional[list] = None
    _tools_schema_revision: Optional[tuple[str, ...]] = None

    _last_prompt_assembly: Optional[PromptAssembly] = PrivateAttr(default=None)
    _last_request_diagnostics: dict = PrivateAttr(default_factory=dict)

    # todo 提醒节流：每 _TODO_REMIND_EVERY 轮注入一次；supervisor 反对时强制注入一次
    _reasoning_round: int = 0
    _todo_reminder_force: bool = False
    # 模型给出结论但未调用 stop 时，一次性强制注入目标确认提醒
    _goal_confirm_force: bool = False

    def _init_context_manager(self) -> None:
        '''初始化本 Agent 的 ContextManager。'''
        self.context_manager = ContextManager(
            agent_id=self.id,
            conversation_id=self.conversation_id,
            prompt=self.prompt,
            query=self.query,
            session_id=getattr(self, 'session_id', None),
            on_compaction_progress=self._report_compaction_progress,
        )

    async def _report_compaction_progress(self, progress: dict) -> None:
        """Broadcast non-durable compression progress without touching SQLite."""
        await events.aemit(
            self.conversation_id,
            "context_compaction",
            agent_id=self.id,
            agent_name=self.name,
            session_id=getattr(self, "session_id", None),
            **progress,
        )

    def _ensure_context_manager(self) -> ContextManager:
        '''确保上下文管理器已初始化；返回实例。'''
        if self.context_manager is None:
            self._init_context_manager()
        return self.context_manager

    async def get_context(self) -> list:
        '''
        加载上下文。ContextManager 是上下文的唯一真相来源。
        '''
        return await self._ensure_context_manager().load()

    async def update_context(self, new_block: dict) -> None:
        '''
        更新上下文，新增一个块。
        确保每条消息都有 role 字段。
        文件路径根据 conversation_id 隔离。
        '''
        await self._ensure_context_manager().append(new_block)

    async def clear_context(self) -> None:
        '''清空上下文（通常用于任务结束后释放）。'''
        await self._ensure_context_manager().clear()

    def check_permission(self, tool: ToolEntry | Tool) -> bool:
        if isinstance(tool, Tool):
            tool_instance = tool
        else:
            tool_instance = tool.instantiate()
        tool_perms = tool_instance.tool_permission_all()
        agent_perms = self.permission_all()
        return check_permission(agent_perms, tool_perms)


    def get_available_tools(self, tools: Optional[list] = None) -> list:
        """Return tools permitted for both this Agent and the runtime.

        ``tools`` is injectable so the reAct dispatcher can apply the exact
        same checks to its current registry snapshot.
        """
        tools = filter_tools_for_runtime(get_tools_lst() if tools is None else tools)
        device_tool_names = {
            entry.tool_name
            for entry in tools
            if entry.tool_name.startswith("device.")
        }
        available_device_tools: set[str] = set()
        if device_tool_names:
            try:
                from cloudra.device_broker import DeviceBroker

                available_device_tools = (
                    DeviceBroker().available_tool_names()
                )
            except (OSError, ValueError):
                available_device_tools = set()
        available_tools = []
        for tool in tools:
            if (
                tool.tool_name in device_tool_names
                and tool.tool_name not in available_device_tools
            ):
                continue
            if self.check_permission(tool):
                available_tools.append(tool)
        return available_tools

    def has_manage_permission(self) -> bool:
        '''
        启动子agent的权限。
        '''
        return False

    def has_write_permission(self) -> bool:
        '''
        正常情况下，agent不允许写入文件，除非在子类中额外开放。
        '''
        return False

    def has_read_permission(self) -> bool:
        '''
        检查是否有读取文件的权限。
        '''
        return True

    def script_run_permission(self) -> bool:
        '''
        运行脚本的权限。
        '''
        return False

    def destructive_permission(self) -> bool:
        '''
        如rm，mkdir等对目录结构进行变化的操作。
        '''
        return False

    def permission_all(self) -> Permission:
        perms = Permission.NONE
        if self.has_read_permission():
            perms |= Permission.READ
        if self.has_write_permission():
            perms |= Permission.WRITE
        if self.has_manage_permission():
            perms |= Permission.MANAGE
        if self.script_run_permission():
            perms |= Permission.SCRIPT
        if self.destructive_permission():
            perms |= Permission.DESTRUCTIVE
        return perms

    def _get_llm_client(self) -> LLMClient:
        """返回实例级缓存的 LLM 传输层客户端（构造本身不做任何 I/O）。"""
        if self._llm_client is None:
            cfg = get_config()
            role_cfg = cfg.coordinator if getattr(self, "type", "") == "coordinator" else cfg.follower
            self._llm_client = LLMClient(
                api_key=self._api_key,
                base_url=self.llm_site,
                timeout=role_cfg.timeout,
            )
        return self._llm_client

    def _role_llm_config(self):
        """返回本 Agent 所属角色（coordinator/follower）的 LLM 配置。"""
        cfg = get_config()
        return cfg.coordinator if getattr(self, "type", "") == "coordinator" else cfg.follower

    def _native_search_adapter(self):
        """解析本 Agent 的模型原生网页搜索适配器（None = 关闭/不可用）。"""
        from cloudra.web_search_native import resolve_native_search

        role_cfg = self._role_llm_config()
        return resolve_native_search(
            base_url=self.llm_site or "",
            model=self.model or "",
            mode=role_cfg.native_search,
            params=role_cfg.native_search_params,
        )

    def _uses_responses_transport(self) -> bool:
        """原生搜索需要走 Responses API（如 DeepSeek）时返回 True。"""
        adapter = self._native_search_adapter()
        return adapter is not None and adapter.transport == "responses"

    def _todo_reminder(self) -> str:
        """返回 todo 提醒文案；该 agent 未建过清单时为空串（纯查询，不做节流）。"""
        try:
            from cloudra.tools.Plantool._store import agent_store_path, load_json

            if load_json(agent_store_path(self, "todos.json"), default=None):
                return (
                    "【系统】你正在维护一份任务清单（todo list）。本轮开始前请先调用 "
                    "todo_read 查看当前清单，确认哪一项处于进行中，再决定下一步；"
                    "完成某项后立即用 todo_write 更新状态。"
                )
        except Exception:
            pass
        return ""

    def _should_inject_todo_reminder(self) -> bool:
        """todo 提醒注入节奏：每 _TODO_REMIND_EVERY 轮一次，或 supervisor
        反对后强制注入一次（supervisor 反对是重要转向节点，模型需要重新
        对照清单校正方向）。"""
        self._reasoning_round += 1
        force = self._todo_reminder_force
        self._todo_reminder_force = False
        return force or (self._reasoning_round % _TODO_REMIND_EVERY == 0)

    def _has_goal_anchor(self) -> bool:
        """该 agent 是否设过目标锚点（调用过 goal_set）。"""
        try:
            from cloudra.tools.Plantool._store import agent_store_path, load_json

            return bool(load_json(agent_store_path(self, "goal.json"), default=None))
        except Exception:
            return False

    def _goal_confirm_reminder(self) -> str:
        """一次性目标确认提醒：仅当该 agent 设过目标锚点（goal_set）时有效。

        reAct 在「无工具调用」轮置 force 后，下一轮请求注入——即首次出现
        无工具轮时提醒模型确认 goal 是否完成、决定 stop 还是继续。
        没设过 goal 时返回空串（无目标可确认，不注入）。
        """
        if not self._goal_confirm_force:
            return ""
        self._goal_confirm_force = False
        return _GOAL_CONFIRM_REMINDER if self._has_goal_anchor() else ""

    @staticmethod
    def _tool_name_of(schema: dict) -> str:
        function = schema.get("function", {}) if isinstance(schema, dict) else {}
        return function.get("name") if isinstance(function, dict) else None

    def _get_tools_schema(self) -> list[dict]:
        """Cache schemas while invalidating when online device capabilities change."""
        # Tests and embedders may explicitly inject a fixed schema list.
        if (
            self._tools_schema_cache is not None
            and self._tools_schema_revision is None
        ):
            return self._tools_schema_cache
        available_entries = self.get_available_tools()
        revision = tuple(sorted(entry.tool_name for entry in available_entries))
        if (
            self._tools_schema_cache is None
            or self._tools_schema_revision != revision
        ):
            available_tool_classes = []
            for entry in available_entries:
                tool_instance = entry.instantiate(subagent=self)
                available_tool_classes.append(tool_instance.tool_schema_json())
            self._tools_schema_cache = available_tool_classes
            self._tools_schema_revision = revision
        return self._tools_schema_cache

    @staticmethod
    def _tool_names_from_schemas(tool_schemas: list[dict]) -> list[str]:
        names = []
        for schema in tool_schemas:
            function = schema.get("function", {}) if isinstance(schema, dict) else {}
            name = function.get("name") if isinstance(function, dict) else None
            if name:
                names.append(name)
        return names

    def _prompt_assembler(self) -> PromptAssembler:
        return PromptAssembler(
            prompt_name=self.prompt_name or self.name,
            custom_prompt=self.prompt,
            conversation_id=self.conversation_id,
            working_directory=self.working_directory,
            include_memory=self.type == "coordinator",
            observer_id=self.id,
        )

    @staticmethod
    def _device_prompt_snapshot(tool_names: list[str]) -> list[dict]:
        """Read a non-secret device snapshot without making it a hard dependency."""

        if not any(name.startswith("device.") for name in tool_names):
            return []
        try:
            from cloudra.device_broker import DeviceBroker

            broker = DeviceBroker()
            devices = broker.list_devices()
            observations = broker.recent_observations(limit=50)
            by_device: dict[str, list[dict]] = {}
            for observation in observations:
                by_device.setdefault(
                    str(observation.get("device_id", "")),
                    [],
                ).append(observation)
            for device in devices:
                device["recent_observations"] = by_device.get(
                    str(device.get("device_id", "")),
                    [],
                )
            return devices
        except Exception:
            return []

    async def _build_messages(
        self,
        tool_schemas: Optional[list[dict]] = None,
    ) -> list[dict]:
        """在请求期装配当前身份层、持久历史和环境 observation。"""
        schemas = self._get_tools_schema() if tool_schemas is None else tool_schemas
        tool_names = self._tool_names_from_schemas(schemas)
        # 有联网搜索能力：原生搜索（服务端工具不在 function 列表里）或外部 web_search 工具
        web_search_available = (
            self._native_search_adapter() is not None or "web_search" in tool_names
        )
        assembly = self._prompt_assembler().assemble(
            tool_names,
            capability_schemas=schemas,
            device_snapshot=self._device_prompt_snapshot(tool_names),
            web_search_available=web_search_available,
        )
        self._last_prompt_assembly = assembly
        target_tokens = self.context_window // 2 if self.context_window else None
        if target_tokens is not None:
            # Tool schemas and runtime observations are part of the provider's
            # prompt too. Previously they were appended after ContextManager's
            # threshold check, so actual requests could pass 50% unnoticed.
            schema_tokens = TokenEstimator.estimate_text(
                json.dumps(schemas, ensure_ascii=False, default=str)
            )
            observation_tokens = TokenEstimator.estimate_messages(
                list(assembly.observation_messages)
            )
            history_budget = max(
                1_024,
                target_tokens - schema_tokens - observation_tokens,
            )
        else:
            history_budget = None
        messages = await self._ensure_context_manager().build_messages(
            supports_vision=self.supports_vision,
            max_context_tokens=history_budget,
            identity_messages=list(assembly.identity_messages),
        )
        messages.extend(assembly.observation_messages)
        return messages

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        """返回最近一次模型请求的非敏感 prompt/tool 诊断。"""
        return dict(self._last_request_diagnostics)

    @staticmethod
    def _provider_for_diagnostics(endpoint: Optional[str]) -> str:
        """只保留 endpoint origin，避免 URL 用户信息、路径和 query 中的凭据落库。"""
        if not endpoint:
            return "<unset>"
        try:
            parsed = urlsplit(endpoint)
            if not parsed.scheme or not parsed.hostname:
                return "<custom-endpoint>"
            host = parsed.hostname
            if ":" in host:
                host = f"[{host}]"
            port = f":{parsed.port}" if parsed.port is not None else ""
            return f"{parsed.scheme}://{host}{port}"
        except (TypeError, ValueError):
            return "<custom-endpoint>"

    async def _build_request_kwargs(self) -> dict:
        """组装一次 chat completions 的请求参数（工具 schema + 上下文消息）。

        启用模型原生网页搜索时，剔除外置 ``web_search`` 工具（避免模型既走
        function call 转第三方搜索、又走 provider 端原生搜索），并通过
        ``extra_body`` 注入服务商的原生搜索参数。
        """
        available_tool_classes = self._get_tools_schema()
        native_adapter = self._native_search_adapter()
        native_name = native_adapter.name if native_adapter is not None else None
        if native_name is not None:
            available_tool_classes = [
                schema
                for schema in available_tool_classes
                if self._tool_name_of(schema) != "web_search"
            ]
        messages = await self._build_messages(available_tool_classes)
        if self._should_inject_todo_reminder():
            reminder = self._todo_reminder()
            if reminder:
                messages = [*messages, {"role": "system", "content": reminder}]
        goal_confirm = self._goal_confirm_reminder()
        if goal_confirm:
            messages = [*messages, {"role": "system", "content": goal_confirm}]

        request_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.is_stream,
        }
        # top_p 仅在显式设置时发送：k3 等严格端点只接受特定值（如 0.95），默认不发送
        if self.top_p is not None:
            request_kwargs["top_p"] = self.top_p
        if available_tool_classes:
            request_kwargs["tools"] = available_tool_classes

        if native_adapter is not None:
            role_cfg = self._role_llm_config()
            request_kwargs = native_adapter.inject(
                request_kwargs, role_cfg.native_search_params
            )

        assembly = self._last_prompt_assembly
        diagnostics = assembly.diagnostics() if assembly is not None else {}
        persisted_history = await self._ensure_context_manager().load()
        history_payload = json.dumps(
            persisted_history,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        supervisor_payload = json.dumps(
            [
                message
                for message in persisted_history
                if SUPERVISOR_ADVICE_MARKER
                in str(message.get("content", ""))
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        diagnostics.update(
            {
                "trace_id": f"llm_{uuid4().hex}",
                "runtime_version": __version__,
                "model": self.model,
                "provider": self._provider_for_diagnostics(self.llm_site),
                "native_search": native_name or "off",
                "conversation_id": self.conversation_id,
                "session_id": self.session_id,
                "agent_id": self.id,
                "agent_name": self.name,
                "message_count": len(messages),
                "estimated_prompt_tokens": (
                    TokenEstimator.estimate_messages(messages)
                    + TokenEstimator.estimate_text(
                        json.dumps(
                            available_tool_classes,
                            ensure_ascii=False,
                            default=str,
                        )
                    )
                ),
                "auto_compact_target_tokens": (
                    self.context_window // 2 if self.context_window else None
                ),
                "history_revision": (
                    "sha256:"
                    + hashlib.sha256(history_payload.encode("utf-8")).hexdigest()
                ),
                "supervisor_advice_revision": (
                    "sha256:"
                    + hashlib.sha256(
                        supervisor_payload.encode("utf-8")
                    ).hexdigest()
                ),
            }
        )
        self._last_request_diagnostics = diagnostics
        return request_kwargs

    async def llm_call(self) -> ChatResponse:
        '''调用llm接口。

        输出：
        1.若实例的is_stream为True，则返回ChatStream对象(一个文本块生成器)
        2.若实例的is_stream为False，则返回ChatResponse对象

        三级 fallback（默认请求头 → 自定义 UA → requests shim）与
        瞬时错误（429/5xx/连接错误）的指数退避重试统一由 LLMClient 完成。
        '''
        request_kwargs = await self._build_request_kwargs()
        client = self._get_llm_client()
        if self._uses_responses_transport():
            return await client.create_responses_with_retry(**request_kwargs)
        return await client.create_with_retry(**request_kwargs)

    async def _llm_call_once(self) -> ChatResponse:
        '''单次调用llm接口（不做瞬时错误重试；传输层 fallback 仍由 LLMClient 完成）。'''
        request_kwargs = await self._build_request_kwargs()
        client = self._get_llm_client()
        if self._uses_responses_transport():
            return await client.create_responses(**request_kwargs)
        return await client.create(**request_kwargs)


class Coordinator(Agent):
    '''
    父agent，用于协调子agent。仅拥有管理工具。
    '''
    id: str = 'a-0'

    name: str = 'coordinator'

    type: str = 'coordinator'

    model: Optional[str] = None

    llm_site: Optional[str] = None

    _api_key: Optional[str] = None

    temperature: float = 1.0

    # k3 等 thinking 模型的思考段极长，8192 常在 reasoning 中途耗尽导致输出被截断
    max_tokens: int = 32768

    # None = 从全局配置 coordinator.context_window 读取（__init__ 中解析）
    context_window: Optional[int] = None

    top_p: Optional[float] = None  # None = 不发送 top_p，用服务商默认值

    frequency_penalty: float = 0.0

    presence_penalty: float = 0.0

    prompt_name: Optional[str] = "coordinator"

    # 由用户输入总任务。
    query: str

    is_stream: bool = True

    @property
    def supports_vision(self) -> bool:
        """从全局配置读取协调者模型是否支持视觉输入。"""
        return get_config().coordinator.supports_vision

    def __init__(self, **data):
        super().__init__(**data)
        cfg = get_config().coordinator
        self.model = self.model or cfg.model
        self.llm_site = self.llm_site or cfg.url
        self.context_window = self.context_window or cfg.context_window
        self._api_key = self._api_key or cfg.key

    def _build_subagent_status_snapshot(self) -> str:
        """从 conversation DB 拉取子 Agent 请求与 session 状态快照（供动态 prompt 使用）。"""
        try:
            db = ConversationDB(self.conversation_id)
            with db.connect() as con:
                rows = con.execute(
                    """SELECT id, session_id, state, input_data
                    FROM subagent_requests
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT 20""",
                    (self.conversation_id,),
                ).fetchall()
                if not rows:
                    return ""

                lines = ["【当前子 Agent 任务状态】"]
                for task_id, session_id, state, input_data in rows:
                    agent_id = "unknown"
                    query = ""
                    try:
                        payload = json.loads(input_data or "{}")
                        agent_id = payload.get("agent_id", "unknown")
                        query = payload.get("query", "")[:80]
                    except Exception:
                        pass
                    lines.append(f"- task_id={task_id} agent={agent_id} state={state} query={query}")

                session_ids = [row[1] for row in rows if row[1]]
                if session_ids:
                    placeholders = ",".join("?" * len(session_ids))
                    sessions = con.execute(
                        f"SELECT session_id, state, error FROM session WHERE session_id IN ({placeholders})",
                        session_ids,
                    ).fetchall()
                    if sessions:
                        lines.append("【子 Agent Session 状态】")
                        for sid, sstate, error in sessions:
                            err = f" error={error[:60]}" if error else ""
                            lines.append(f"- session={sid} state={sstate}{err}")
                return "\n".join(lines)
        except Exception:
            return ""

    def _build_schedule_status_snapshot(self) -> str:
        """把当前待触发提醒放进动态 prompt，供 Coordinator 管理和去重。"""
        try:
            db = ConversationDB(self.conversation_id)
            with db.connect() as con:
                rows = con.execute(
                    """SELECT id, wake_at, content
                    FROM scheduled_reminders
                    WHERE conversation_id = ? AND agent_id = ? AND state = 'pending'
                    ORDER BY wake_at, id
                    LIMIT 20""",
                    (self.conversation_id, self.id),
                ).fetchall()
            if not rows:
                return ""

            lines = [
                "【当前待触发 schedule】",
                "这些提醒彼此独立且都会触发。创建新提醒前先判断旧提醒是否仍有必要；"
                "已被新安排取代或不再需要的提醒应调用 schedule(action='cancel', schedule_id=...) 取消。",
            ]
            for schedule_id, wake_at, content in rows:
                wake_iso = datetime.fromtimestamp(float(wake_at)).astimezone().isoformat(
                    timespec="seconds"
                )
                summary = " ".join(str(content).split())[:160]
                lines.append(f"- schedule_id={schedule_id} wake_at={wake_iso} message={summary}")
            return "\n".join(lines)
        except Exception:
            return ""

    async def _build_messages(
        self,
        tool_schemas: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Coordinator 每次推理前附加运行状态快照，实现动态 prompt。"""
        messages = await super()._build_messages(tool_schemas)
        snapshots = (
            self._build_subagent_status_snapshot(),
            self._build_schedule_status_snapshot(),
        )
        for snapshot in snapshots:
            if snapshot:
                messages.append({"role": "system", "content": snapshot})
        return messages

    def has_manage_permission(self) -> bool:
        '''
        协调者允许访问子agent。
        '''
        return True

    def has_write_permission(self) -> bool:
        '''
        Coordinator 允许使用简单的 write 工具（如输出最终报告、发送邮件），
        但不拥有 destructive 权限，不能执行破坏性操作。
        '''
        return True

    def script_run_permission(self) -> bool:
        '''
        Coordinator 允许运行脚本工具。
        '''
        return True

    def destructive_permission(self) -> bool:
        '''
        Coordinator 允许执行破坏性操作（如覆盖文件、删除文件）。
        简化权限设计，使 Coordinator 能直接使用所有工具。
        '''
        return True

    def get_available_tools(self, tools: Optional[list] = None) -> list:
        '''
        Coordinator 实际可见的工具列表。
        简化设计：Coordinator 可以使用所有工具，不再按模块白名单过滤。
        '''
        return super().get_available_tools(tools)


class Follower(Agent):
    '''
    子agent大类，后续有细分类型，再定义子类。
    '''
    id: str

    name: str

    type: str = 'follower'

    model: Optional[str] = None

    llm_site: Optional[str] = None

    _api_key: Optional[str] = None

    temperature: float = 1.0

    # writer 类子 Agent 要整篇写文件，4096 极易截断（JSON 参数被拦腰切断）
    max_tokens: int = 16384

    # None = 从全局配置 follower.context_window 读取（__init__ 中解析）
    context_window: Optional[int] = None

    top_p: Optional[float] = None  # None = 不发送 top_p，用服务商默认值

    frequency_penalty: float = 0.0

    presence_penalty: float = 0.0

    prompt_name: Optional[str] = None

    query: str

    # 子 Agent 也走流式：llm_chunk 事件写入各自 session 的事件表，
    # 前端按 session 展示对话式 transcript；CLI 侧子进程输出相应变为逐块实时打印。
    is_stream: bool = True

    @property
    def supports_vision(self) -> bool:
        """从全局配置读取跟随者模型是否支持视觉输入。"""
        return get_config().follower.supports_vision

    def __init__(self, **data):
        super().__init__(**data)
        cfg = get_config().follower
        self.model = self.model or cfg.model
        self.llm_site = self.llm_site or cfg.url
        self._api_key = self._api_key or cfg.key
        self.context_window = self.context_window or cfg.context_window

    def has_read_permission(self) -> bool:
        return True

    def has_write_permission(self) -> bool:
        '''
        正常情况下，agent不允许写入文件，除非在子类中额外开放。
        '''
        return False

    def script_run_permission(self) -> bool:
        '''
        运行脚本的权限。
        '''
        return False

    def destructive_permission(self) -> bool:
        '''
        如rm，mkdir等对目录结构进行变化的操作。
        '''
        return False
