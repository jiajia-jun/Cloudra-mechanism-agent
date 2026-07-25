import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from cloudra.config import get_config
from cloudra.context_manager import ContextManager
from cloudra.llm_client import ChatResponse, LLMClient
from cloudra.memory import get_memory_manager
from cloudra.tools import ToolEntry, get_tools_lst
from cloudra.tools.core.permission_model import Permission, check_permission
from cloudra.tools_class import Tool


def load_prompt(agent_name: str) -> str:
    """
    从 prompts/{agent_name}.md 加载对应 Agent 的 prompt。
    便于将 prompt 与代码分离，统一在 prompts/ 目录下管理。
    """
    prompts_dir = Path(__file__).parent / 'prompts'
    prompt_path = prompts_dir / f"{agent_name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"找不到 prompt 文件: {prompt_path}")
    return prompt_path.read_text(encoding='utf-8')


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

    #agent身份prompt，如：“你是一个多agent协作体系的协调器......”
    prompt: str

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

    def _init_context_manager(self) -> None:
        '''初始化本 Agent 的 ContextManager。'''
        self.context_manager = ContextManager(
            agent_id=self.id,
            conversation_id=self.conversation_id,
            prompt=self.prompt,
            query=self.query,
            session_id=getattr(self, 'session_id', None),
        )

    async def get_context(self) -> list:
        '''
        加载上下文。ContextManager 是上下文的唯一真相来源。
        '''
        if self.context_manager is None:
            self._init_context_manager()
        return await self.context_manager.load()

    async def update_context(self, new_block: dict) -> None:
        '''
        更新上下文，新增一个块。
        确保每条消息都有 role 字段。
        文件路径根据 conversation_id 隔离。
        '''
        if self.context_manager is None:
            self._init_context_manager()
        await self.context_manager.append(new_block)

    async def clear_context(self) -> None:
        '''清空上下文（通常用于任务结束后释放）。'''
        if self.context_manager is None:
            self._init_context_manager()
        await self.context_manager.clear()

    def check_permission(self, tool: ToolEntry | Tool) -> bool:
        if isinstance(tool, Tool):
            tool_instance = tool
        else:
            tool_instance = tool.instantiate()
        tool_perms = tool_instance.tool_permission_all()
        agent_perms = self.permission_all()
        return check_permission(agent_perms, tool_perms)


    def get_available_tools(self) -> list:
        tools = get_tools_lst()
        available_tools = []
        for tool in tools:
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
            self._llm_client = LLMClient(api_key=self._api_key, base_url=self.llm_site)
        return self._llm_client

    async def _build_request_kwargs(self) -> dict:
        """组装一次 chat completions 的请求参数（工具 schema + 上下文消息）。"""
        if self._tools_schema_cache is None:
            tool_entries = get_tools_lst()
            available_tool_classes = []
            for entry in tool_entries:
                if self.check_permission(entry):
                    tool_instance = entry.instantiate(subagent=self)
                    available_tool_classes.append(tool_instance.tool_schema_json())
            self._tools_schema_cache = available_tool_classes
        available_tool_classes = self._tools_schema_cache

        if self.context_manager is None:
            self._init_context_manager()
        messages = await self.context_manager.build_messages(
            supports_vision=self.supports_vision,
            max_context_tokens=self.context_window // 2 if self.context_window else None,
        )

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
        return await self._get_llm_client().create_with_retry(**request_kwargs)

    async def _llm_call_once(self) -> ChatResponse:
        '''单次调用llm接口（不做瞬时错误重试；三级 fallback 仍由 LLMClient 完成）。'''
        request_kwargs = await self._build_request_kwargs()
        return await self._get_llm_client().create(**request_kwargs)


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

    context_window: int = 1000000

    top_p: Optional[float] = None  # None = 不发送 top_p，用服务商默认值

    frequency_penalty: float = 0.0

    presence_penalty: float = 0.0

    prompt: str = load_prompt('coordinator')

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
        self._api_key = self._api_key or cfg.key
        cwd = self.working_directory or os.getcwd()
        # 列出工作目录顶层内容，帮助 Coordinator 知道当前有哪些文件/文件夹可用
        listing_lines = []
        try:
            for name in sorted(os.listdir(cwd)):
                # 跳过隐藏目录/文件和常见缓存目录，避免污染 prompt
                if name.startswith('.') or name in ('__pycache__', '__init__.py'):
                    continue
                full_path = os.path.join(cwd, name)
                listing_lines.append(f"{name}/" if os.path.isdir(full_path) else name)
        except Exception:
            listing_lines = ["<无法读取目录内容>"]

        listing_str = "\n".join(listing_lines) if listing_lines else "<空目录>"
        self.prompt += (
            f"\n\n当前项目的工作目录是: {cwd}\n"
            f"工作目录顶层内容:\n{listing_str}\n"
            "在分发任务给子 Agent 时，请务必提供相关的绝对路径，确保它们能在正确的目录下操作。"
        )

        # 加载 Coordinator 的长期记忆到身份 prompt
        self._inject_memory_to_prompt()

    def _inject_memory_to_prompt(self) -> None:
        """把全局 MEMORY.md 的内容注入到 Coordinator 的身份 prompt。"""
        try:
            conv_id = getattr(self, 'conversation_id', None)
            manager = get_memory_manager(conversation_id=conv_id)
            memory_text = manager.load()
            if memory_text and memory_text.strip():
                self.prompt += (
                    "\n\n## 长期记忆（从过往任务中积累的经验）\n\n"
                    "以下经验来自 MEMORY.md，在执行任务时优先遵循：\n\n"
                    f"{memory_text.strip()}\n\n"
                    "如果你从这些经验中学到了新的可复用原则，请调用 `update_memory` 工具更新记忆。"
                )
        except Exception as e:
            # 记忆加载失败不应阻止 Coordinator 启动
            print(f"[Coordinator] 加载长期记忆失败: {e}")

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

    def get_available_tools(self) -> list:
        '''
        Coordinator 实际可见的工具列表。
        简化设计：Coordinator 可以使用所有工具，不再按模块白名单过滤。
        '''
        return super().get_available_tools()


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

    context_window: int = 1000000

    top_p: Optional[float] = None  # None = 不发送 top_p，用服务商默认值

    frequency_penalty: float = 0.0

    presence_penalty: float = 0.0

    prompt: str

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
