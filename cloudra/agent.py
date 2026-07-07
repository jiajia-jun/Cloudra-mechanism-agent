import os
from pathlib import Path
from typing import Optional, Union

from openai import OpenAI, Stream
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from pydantic import BaseModel

from cloudra.config import get_config
from cloudra.context_manager import ContextManager
from cloudra.tools import get_tools_lst
from cloudra.tools.core.permission_model import Permission, check_permission
from cloudra.tools_class import Tool

ChatResponse = Union[ChatCompletion, Stream[ChatCompletionChunk]]


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
    top_p: float = 1.0

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

    def check_permission(self, tool: type[Tool] | Tool) -> bool:
        '''
        检查子agent的权限。
        tool 可以是 Tool 类或已实例化的 Tool 对象。
        '''
        # NOTE: 为了兼容 get_tools_lst() 现在返回实例对象，这里先判断是否是已实例化的 Tool。
        if isinstance(tool, Tool):
            tool_instance = tool
        else:
            tool_instance = tool()
        tool_perms = tool_instance.tool_permission_all()
        agent_perms = self.permission_all()
        return check_permission(agent_perms, tool_perms)    #No its not a recursion


    def get_available_tools(self) -> list:
        '''
        逐个过滤tools父类池，得到子类池，该类的工具权限：
        is_read [ ]
        is_write [ ]
        is_manage [ ]
        is_script [ ]
        is_destructive [ ]
        '''
        tools = get_tools_lst()
        available_tools = []
        for tool in tools:
            if self.check_permission(tool):
                # NOTE: get_tools_lst() 现已返回实例对象，无需再 tool() 构造。
                # 需要注入 subagent 的 Bashtools/SubAgentLauncher 已在 reAct.py 中按需重新实例化。
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

    def _context_path(self) -> str:
        '''
        根据 conversation_id 返回上下文文件路径。
        保留此方法以兼容旧代码，但新代码应优先使用 ContextManager。
        '''
        from cloudra.config import get_config
        data_dir = get_config().data_dir
        if self.conversation_id and self.conversation_id != 'default':
            return os.path.join(data_dir, 'conversations', self.conversation_id, 'contexts', self.id + '.json')
        return os.path.join(data_dir, 'contexts', self.id + '.json')

    async def llm_call(self) -> ChatResponse:
        '''
        调用llm接口。
        输出：
        1.若实例的is_stream为True，则返回ChatStream对象(一个文本块生成器)
        2.若实例的is_stream为False，则返回ChatResponse对象
        '''
        tool_classes = get_tools_lst()
        available_tool_classes = []
        for tool in tool_classes:
            if self.check_permission(tool):
                # 重新实例化并注入当前 Agent，使依赖 subagent 的动态 tool_description 生效。
                # 同时避免直接修改 get_tools_lst() 返回的全局缓存实例。
                tool_instance = tool.__class__(subagent=self)
                available_tool_classes.append(tool_instance.tool_schema_json())

        client = OpenAI(
            api_key=self._api_key,
            base_url=self.llm_site,
        )

        if self.context_manager is None:
            self._init_context_manager()
        messages = await self.context_manager.build_messages(
            supports_vision=self.supports_vision,
            max_context_tokens=self.context_window // 2 if self.context_window else None,
        )

        # 最终防御：再次过滤 assistant 空消息，避免某些 provider 因
        # messages[N] 为空而返回 400 Param Incorrect。
        messages = self.context_manager._drop_empty_assistant_messages(messages)

        request_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stream": self.is_stream,
        }
        if available_tool_classes:
            request_kwargs["tools"] = available_tool_classes

        try:
            return client.chat.completions.create(**request_kwargs)
        except Exception as e:
            print(f"\033[91m[LLM 异常]\033[0m {e}")
            raise


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

    max_tokens: int = 8192

    context_window: int = 1000000

    top_p: float = 1.0

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
        cwd = os.getcwd()
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

    def has_manage_permission(self) -> bool:
        '''
        协调者允许访问子agent。
        '''
        return True

    def has_write_permission(self) -> bool:
        '''
        Coordinator 允许使用简单的 write 工具（如输出最终报告、发送邮件），
        但不拥有 script 和 destructive 权限，不能自己执行脚本或危险操作。
        '''
        return True

    def get_available_tools(self) -> list:
        '''
        Coordinator 实际可见的工具列表。
        虽然拥有 write 权限，但只允许使用白名单中的 write 工具；
        化学工具、脚本执行、破坏性工具等复杂任务必须委派给子 Agent。
        '''
        write_tool_allowlist = {'text_writer', 'email_sender'}
        tools = super().get_available_tools()
        available_tools = []
        for tool in tools:
            module = getattr(tool.__class__, '__module__', '')
            # Coordinator 不直接处理化学/脚本类工具
            if 'Chemtool' in module or 'Bashtool' in module:
                continue
            if tool.tool_name in write_tool_allowlist:
                available_tools.append(tool)
                continue
            if not (tool.is_write() or tool.is_script() or tool.is_destructive()):
                available_tools.append(tool)
        return available_tools


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

    max_tokens: int = 4096

    context_window: int = 1000000

    top_p: float = 1.0

    frequency_penalty: float = 0.0

    presence_penalty: float = 0.0

    prompt: str

    query: str

    is_stream: bool = False

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


def get_class():
    """兼容旧导入，返回 Agent 基类。"""
    return Agent
