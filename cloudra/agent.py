import os
import json
import sys
import copy
from cloudra.tools_class import Tool, get_tools
from cloudra.tools import get_tools_lst
from pydantic import BaseModel
from typing import Union
from openai import OpenAI, Stream
from openai.types.chat import ChatCompletion,ChatCompletionChunk
from dotenv import load_dotenv
from cloudra.tools.core.permission_model import Permission, check_permission

load_dotenv()

ChatResponse = Union[ChatCompletion, Stream[ChatCompletionChunk]]

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
    13.agent上下文（context）
    14.agent输出方式（is_stream）

    该类的其他方法:
    权限：has_write_permission，has_read_permission，script_run_permission，destructive_permission(均为布尔值输出)
    llm_call方法：调用llm，输出ChatResponse或ChatStream
    后续可能加入的方法：调用本地专用模型，不能通过openai接口，因此待定，可以上github上看看有没有开源的逆合成分析模型等
    '''
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

    #agent使用模型最大token
    max_tokens: int

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

    context: list = []

    conversation_id: str

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
        return check_permission(agent_perms, tool_perms)


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
    
    def get_context(self) -> list:
        '''
        在后续子类中加载上下文。
        '''
        return []

    def _context_path(self) -> str:
        '''
        根据 conversation_id 返回上下文文件路径。
        '''
        from cloudra.config import get_config
        data_dir = get_config().data_dir
        if self.conversation_id and self.conversation_id != 'default':
            return os.path.join(data_dir, 'conversations', self.conversation_id, 'contexts', self.id + '.json')
        return os.path.join(data_dir, 'contexts', self.id + '.json')

    def _encode_image(self, image_path: str) -> str:
        """将本地图片转为 Base64"""
        import base64
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def llm_call(self) -> ChatResponse:
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
                # HACK: 硬编码注入 subagent，使 Bashtools 的动态 description 生效
                if tool.tool_name == 'bashtools':
                    tool = tool.__class__(subagent=self)
                available_tool_classes.append(tool.tool_schema_json())
        
        client = OpenAI(api_key=self._api_key ,
                        base_url=self.llm_site ,
                        )

        def build_messages(use_multimodal=True):
            content = []
            content.append({"role": "system", "content": self.prompt})
            for context_block in self.context:
                msg = copy.deepcopy(dict(context_block))
                if 'role' not in msg: msg['role'] = 'user'
                
                # 处理多模态逻辑
                if isinstance(msg.get('content'), list):
                    new_content = []
                    for part in msg['content']:
                        if isinstance(part, dict) and part.get('type') == 'image_url':
                            path = part.get('image_url', {}).get('url')
                            if use_multimodal:
                                # 尝试构建 Base64
                                try:
                                    if path and os.path.exists(path):
                                        base64_image = self._encode_image(path)
                                        ext = os.path.splitext(path)[1].lower().replace('.', '')
                                        mime = f"image/{ext}" if ext in ['png', 'jpeg', 'jpg', 'webp'] else "image/png"
                                        new_content.append({
                                            "type": "image_url",
                                            "image_url": {"url": f"data:{mime};base64,{base64_image}"}
                                        })
                                    else:
                                        new_content.append({"type": "text", "text": f"[图片缺失: {path}]"})
                                except Exception as e:
                                    new_content.append({"type": "text", "text": f"[图片加载失败: {path}]"})
                            else:
                                # 降级模式：转为纯文本
                                new_content.append({"type": "text", "text": f"[图片: {path} (当前模型不支持视觉)]"})
                        else:
                            new_content.append(part)
                    msg['content'] = new_content if use_multimodal else "\n".join([p.get('text', '') for p in new_content])
                
                if 'content' not in msg:
                    msg['content'] = str(msg.get('assistant', msg)) if 'assistant' in msg else None
                
                if 'reasoning_content' in msg:
                    msg['reasoning_content'] = str(msg['reasoning_content']) if msg['reasoning_content'] else None
                
                content.append(msg)
            return content

        # 尝试第一次调用（完整多模态）
        try:
            messages = build_messages(use_multimodal=True)
            if available_tool_classes:
                return client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p,
                    stream=self.is_stream,
                    tools=available_tool_classes,
                )
            else:
                return client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p,
                    stream=self.is_stream
                )
        except Exception as e:
            # 捕获 400 错误（通常是由于不支持 image_url 引起的）
            err_msg = str(e).lower()
            if "image_url" in err_msg or "unknown variant" in err_msg or "400" in err_msg:
                print(f"\033[93m[系统预警]\033[0m 当前模型或接口不支持多模态内容，正在切换至“纯文本降级模式”重试...")
                # 重新构建纯文本消息列表
                messages = build_messages(use_multimodal=False)
                # 第二次调用（纯文本降级）
                if available_tool_classes:
                    return client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        top_p=self.top_p,
                        stream=self.is_stream,
                        tools=available_tool_classes,
                    )
                else:
                    return client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        top_p=self.top_p,
                        stream=self.is_stream
                    )
            else:
                # 其他类型的错误，原样抛出
                print(f"\033[91m[LLM 异常]\033[0m {e}")
                raise e
    
    def update_context(self, new_block: dict) -> None:
        '''
        更新上下文，新增一个块。
        确保每条消息都有 role 字段。
        文件路径根据 conversation_id 隔离。
        '''
        if 'role' not in new_block:
            new_block['role'] = 'user'
        
        # 提取 image_path（如果存在）
        image_path = new_block.pop('image_path', None)
        
        # 如果包含图片，将 content 构建为 OpenAI 标准的 list 结构，但 URL 暂存本地路径
        if image_path:
            text_content = new_block.get('content', "查看此图片内容：")
            new_block['content'] = [
                {"type": "text", "text": text_content if text_content else "查看此图片内容："},
                {
                    "type": "image_url", 
                    "image_url": {"url": image_path}
                }
            ]
        elif 'content' not in new_block:
            new_block['content'] = str(new_block)
                
        self.context.append(new_block)
        context_path = self._context_path()
        os.makedirs(os.path.dirname(context_path), exist_ok=True)
        with open(context_path, 'w', encoding='utf-8') as f:
            json.dump(self.context, f, ensure_ascii=False, indent=4)
    




class Coordinator(Agent):
    '''
    父agent，用于协调子agent。仅拥有管理工具。
    '''
    id: str = 'a-0'

    name: str = 'coordinator'

    type: str = 'coordinator'

    model: str = os.environ.get('COORDINATOR_MODEL')

    llm_site: str = os.environ.get('COORDINATOR_URL')

    _api_key: str = os.environ.get('COORDINATOR_KEY')

    temperature: float = 1.0

    max_tokens: int = 2000

    top_p: float = 1.0

    frequency_penalty: float = 0.0

    presence_penalty: float = 0.0

    prompt: str = '''
    你处在一个体系中，这个体系的名字叫做Cloudra。
    而你是一个多agent协作体系的协调者，你将直接对接用户的需求，将用户的需求拆解成一个个子任务，分发给子agent完成。在子agent发射后，你仍然拥有行动的能力，请用最理性实事求是的态度与用户说明情况。
    '''

    #由用户输入总任务。
    query: str

    is_stream: bool = True

    context: list = []

    def __init__(self, **data):
        super().__init__(**data)
        cwd = os.getcwd()
        self.prompt += f"\n\n当前项目的工作目录是: {cwd}\n在分发任务给子 Agent 时，请务必提供相关的绝对路径，确保它们能在正确的目录下操作。"
        self.context = self.get_context()

    def has_manage_permission(self) -> bool:
        '''
        协调者允许访问子agent。
        '''
        return True

    def get_context(self) -> list:
        '''
        加载上下文，但需要另行写入新增上下文
        '''
        system_json = {
            "role": "system",
            "content": self.prompt
        }
        query_json = {
            "role": "user",
            "content": self.query
        }
        context_path = self._context_path()
        os.makedirs(os.path.dirname(context_path), exist_ok=True)
        if os.path.isfile(context_path):
            try:
                with open(context_path, 'r', encoding='utf-8') as f:
                    self.context = json.load(f)
            except json.JSONDecodeError:
                print(f'无法解析JSON文件：{context_path}')
                exc_type, exc_value, exc_traceback = sys.exc_info()
                if exc_traceback is not None:
                    print(f'错误发生在文件 {exc_traceback.tb_frame.f_code.co_filename} 的第 {exc_traceback.tb_lineno} 行')
                    raise json.JSONDecodeError("无法解析JSON文件", context_path, exc_traceback.tb_lineno)
                else:
                    raise json.JSONDecodeError("无法解析JSON文件", context_path, 0)
        else:
            self.context = [system_json, query_json]
            with open(context_path, 'w', encoding='utf-8') as f:
                json.dump(self.context, f, ensure_ascii=False, indent=4)

        return self.context
    

        
class Follower(Agent):
    '''
    子agent大类，后续有细分类型，再定义子类。
    '''
    id: str

    name: str

    type: str = 'follower'

    model: str = os.environ.get('FOLLOWER_MODEL')

    llm_site: str = os.environ.get('FOLLOWER_URL')

    _api_key: str = os.environ.get('FOLLOWER_KEY')

    temperature: float = 1.0

    max_tokens: int = 2000

    top_p: float = 1.0

    frequency_penalty: float = 0.0

    presence_penalty: float = 0.0

    prompt: str

    query: str

    is_stream: bool = False

    context: list = []

    def __init__(self, **data):
        super().__init__(**data)
        self.context = self.get_context()

    def get_context(self) -> list:
        '''
        加载上下文，确保包含 prompt 和 query。
        '''
        system_json = {"role": "system", "content": self.prompt}
        query_json = {"role": "user", "content": self.query}
        
        context_path = self._context_path()
        os.makedirs(os.path.dirname(context_path), exist_ok=True)
        
        if os.path.isfile(context_path):
            try:
                with open(context_path, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    # 只有当历史为空或仅包含 system message 时才插入 query
                    if not history or (len(history) == 1 and history[0].get('role') == 'system'):
                        self.context = [system_json, query_json]
                    else:
                        self.context = history
            except:
                self.context = [system_json, query_json]
        else:
            self.context = [system_json, query_json]
        
        # 立即持久化，防止多进程环境下读取到空文件
        with open(context_path, 'w', encoding='utf-8') as f:
            json.dump(self.context, f, ensure_ascii=False, indent=4)
            
        return self.context

    def has_read_permission(self) -> bool:
        return True
    
