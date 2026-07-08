import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional, Union

import requests

from openai import OpenAI, Stream
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from pydantic import BaseModel

from cloudra.config import get_config
from cloudra.context_manager import ContextManager
from cloudra.memory import get_memory_manager
from cloudra.tools import get_tools_lst
from cloudra.tools.core.permission_model import Permission, check_permission
from cloudra.tools_class import Tool

ChatResponse = Union[ChatCompletion, Stream[ChatCompletionChunk]]


class _ResponseDictWrapper:
    """把 requests 返回的 dict 包装成同时支持属性访问和 model_dump 的对象。"""

    __slots__ = ("_data",)

    def __init__(self, data: Any):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        try:
            val = self._data[name]
        except (KeyError, TypeError):
            raise AttributeError(name)
        return self._wrap(val)

    def model_dump(self, **kwargs) -> Any:
        return self._data

    @classmethod
    def _wrap(cls, val: Any) -> Any:
        if isinstance(val, dict):
            return cls(val)
        if isinstance(val, list):
            return [cls._wrap(x) for x in val]
        return val

    def __repr__(self) -> str:
        return f"_ResponseDictWrapper({self._data!r})"


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

    # 兼容被中转站拦截的 OpenAI 客户端：启用后改用 requests 发送请求
    _curl_mode: bool = False

    # 启用 OpenAI 客户端 + 自定义请求头（比 requests 更规范）
    _use_custom_headers: bool = False

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

    def _is_fallback_trigger(self, exc: Exception) -> bool:
        """判断异常是否由中转站拦截/流控导致，需要切到 requests fallback。"""
        msg = str(exc).lower()
        # 常见被拦截/流控关键词
        blocked_keywords = (
            "blocked",
            "your request was blocked",
            "access denied",
            " forbidden",
            "too many requests",
            "rate limit",
            "cloudflare",
            "bad gateway",
            "connection reset",
        )
        return any(k in msg for k in blocked_keywords)

    def _serialize_openai_payload(self, kwargs: dict) -> dict:
        """把 kwargs 里的 pydantic/model 对象序列化为纯 dict，供 requests 使用。"""

        def _to_dict(obj: Any) -> Any:
            if hasattr(obj, "model_dump"):
                return obj.model_dump(exclude_none=True)
            if hasattr(obj, "dict"):
                return obj.dict(exclude_none=True)
            if isinstance(obj, dict):
                return {k: _to_dict(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_to_dict(x) for x in obj]
            return obj

        return _to_dict(kwargs)

    async def _chat_completions_via_requests(self, **kwargs) -> ChatResponse:
        """异步包装：把同步的 requests 调用放到线程池执行，避免阻塞事件循环。"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._chat_completions_via_requests_sync,
            kwargs,
        )

    def _chat_completions_via_requests_sync(self, kwargs: dict) -> ChatResponse:
        """使用 requests 直接调用 chat completions，模拟 openai 接口返回结构。"""
        url = f"{self.llm_site.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.68.0",
            "Accept": "application/json",
        }
        payload = self._serialize_openai_payload(kwargs)
        stream = payload.get("stream", False)

        if stream:
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    stream=True,
                    timeout=120,
                )
                resp.raise_for_status()
                return self._stream_response(resp)
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
                # 部分中转站不支持 SSE，退化为非流式并包装成单 chunk 生成器
                print("\033[93m[LLM fallback] 流式连接被重置，退化为非流式返回\033[0m")
                payload["stream"] = False
                stream = False

        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        if stream:
            return self._json_to_single_chunk_stream(data)
        return _ResponseDictWrapper(data)

    def _openai_client_with_custom_headers(self) -> OpenAI:
        """返回带自定义 User-Agent 的 OpenAI 客户端，用于二级 fallback。"""
        return OpenAI(
            api_key=self._api_key,
            base_url=self.llm_site,
            default_headers={"User-Agent": "curl/7.68.0"},
        )

    def _json_to_single_chunk_stream(self, data: dict):
        """把非流式响应包装成单 chunk 流生成器，兼容 reAct 的流式消费代码。"""
        message = data.get("choices", [{}])[0].get("message", {})
        chunk_data = {
            "id": data.get("id", ""),
            "object": "chat.completion.chunk",
            "created": data.get("created", 0),
            "model": data.get("model", ""),
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": message.get("content", ""),
                        "tool_calls": message.get("tool_calls"),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        return iter([_ResponseDictWrapper(chunk_data)])

    def _stream_response(self, resp) -> Any:
        """解析 SSE 流，生成与 openai 兼容的 chunk 对象。"""

        def _iter_chunks():
            buffer = ""
            for raw in resp.iter_content(chunk_size=1024):
                if not raw:
                    continue
                buffer += raw.decode("utf-8", errors="replace")
                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    data_line = ""
                    for line in block.splitlines():
                        if line.startswith("data:"):
                            data_line = line[5:].strip()
                            break
                    if data_line == "[DONE]":
                        continue
                    if data_line:
                        try:
                            chunk = json.loads(data_line)
                        except json.JSONDecodeError:
                            continue
                        yield _ResponseDictWrapper(chunk)

        return _iter_chunks()

    async def llm_call(self) -> ChatResponse:
        '''
        调用llm接口。
        输出：
        1.若实例的is_stream为True，则返回ChatStream对象(一个文本块生成器)
        2.若实例的is_stream为False，则返回ChatResponse对象

        新增三级 fallback，用于应对中转站对 OpenAI 客户端请求头的拦截：
        1. OpenAI 客户端 + 默认请求头
        2. OpenAI 客户端 + 自定义 User-Agent（curl/7.68.0）
        3. requests 库 + 自定义 User-Agent（放到线程池执行，避免阻塞事件循环）

        一旦某一级成功，该 Agent 实例会记住这一级，后续调用优先使用。
        '''
        tool_classes = get_tools_lst()
        available_tool_classes = []
        for tool in tool_classes:
            if self.check_permission(tool):
                # 重新实例化并注入当前 Agent，使依赖 subagent 的动态 tool_description 生效。
                # 同时避免直接修改 get_tools_lst() 返回的全局缓存实例。
                tool_instance = tool.__class__(subagent=self)
                available_tool_classes.append(tool_instance.tool_schema_json())

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

        # 三级 fallback：
        # 1. OpenAI 客户端默认请求头
        # 2. OpenAI 客户端 + 自定义 User-Agent
        # 3. requests 库（同步阻塞，但放在线程池执行）

        # Level 3: requests fallback（已彻底降级）
        if self._curl_mode:
            try:
                return await self._chat_completions_via_requests(**request_kwargs)
            except Exception as e:
                print(f"\033[91m[LLM curl 异常]\033[0m {e}")
                raise

        # Level 2: OpenAI 客户端 + 自定义请求头（之前 fallback 成功过）
        if self._use_custom_headers:
            client = self._openai_client_with_custom_headers()
            try:
                return client.chat.completions.create(**request_kwargs)
            except Exception as e:
                if self._is_fallback_trigger(e):
                    print(f"\033[93m[LLM fallback] 自定义请求头仍被拦截，切到 requests: {e}\033[0m")
                    self._curl_mode = True
                    return await self._chat_completions_via_requests(**request_kwargs)
                print(f"\033[91m[LLM 异常]\033[0m {e}")
                raise

        # Level 1: OpenAI 客户端默认请求头
        client = OpenAI(
            api_key=self._api_key,
            base_url=self.llm_site,
        )

        try:
            return client.chat.completions.create(**request_kwargs)
        except Exception as e:
            if self._is_fallback_trigger(e):
                print(f"\033[93m[LLM fallback] OpenAI 默认请求头被拦截，尝试自定义请求头: {e}\033[0m")
                self._use_custom_headers = True
                client2 = self._openai_client_with_custom_headers()
                try:
                    return client2.chat.completions.create(**request_kwargs)
                except Exception as e2:
                    if self._is_fallback_trigger(e2):
                        print(f"\033[93m[LLM fallback] 自定义请求头仍被拦截，切到 requests: {e2}\033[0m")
                        self._curl_mode = True
                        return await self._chat_completions_via_requests(**request_kwargs)
                    print(f"\033[91m[LLM 异常]\033[0m {e2}")
                    raise
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
