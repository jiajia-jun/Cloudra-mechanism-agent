import time
import httpx
import openai 
import os
from cloudra.agent import Agent
import asyncio
import json
from datetime import datetime
from cloudra.log_class import Log
from cloudra.tools_class import input_schema,get_tools
from cloudra.tools import get_tools_lst
from cloudra.session_class import Session
from cloudra.config import get_config
from cloudra.database import get_database_path, ConversationDB


# 每次 reasoning 前等待外部事件的最长时间（秒）
EXTERNAL_EVENT_POLL_INTERVAL = 0.5


def dynamic_deep_merge(buffer_dict: dict, delta_dict: dict) -> dict:
    """通用动态拼接工具：不硬编码任何字段名，自动合并字符串，自动递归字典。

    注意：tool_call 中的 'type' 和 'name' 是固定枚举值，收到重复 chunk 时应
    直接覆盖，而不是字符串累加；否则会出现 'functionfunction...' 这种非法值，
    导致部分 provider（如 Xiaomi token-plan）返回 400。
    """
    # 这些字段在 OpenAI tool_call chunk 中是固定值，不应累加。
    overwrite_fields = {"type", "name"}

    for key, value in delta_dict.items():
        if isinstance(value, dict):
            # 如果是嵌套字典（比如 'function'），递归进去拼接
            if key not in buffer_dict:
                buffer_dict[key] = {}
            dynamic_deep_merge(buffer_dict[key], value)

        elif isinstance(value, str):
            # 固定值字段直接覆盖，其余字符串字段累加。
            if key in overwrite_fields:
                buffer_dict[key] = value
            else:
                if key not in buffer_dict:
                    buffer_dict[key] = ""
                buffer_dict[key] += value

        else:
            # 如果是数字或其他类型（比如 'index'），直接覆盖/初始化
            buffer_dict[key] = value

    return buffer_dict

class Color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class reAct:
    session: Session 
    agent: Agent
    prompt: str
    log: Log
    _continue : bool = True
    database_path: str = ''
    undos: list = []
    _reset_count: int = 0
    
    def __init__(self, agent: Agent, query: str = "", session_id: str = None):
        self.agent = agent
        # query 是本次任务要求，应该作为 user 消息进入上下文，
        # 绝不能覆盖 agent.prompt（身份 prompt）。
        if query:
            agent.query = query
        self.log = Log(agent.name)
        self.log.session = None
            
        data_dir = get_config().data_dir
        conv_id = getattr(agent, 'conversation_id', 'default')
        if conv_id and conv_id != 'default':
            log_path = os.path.join(data_dir, 'conversations', conv_id, 'logs', agent.name)
        else:
            log_path = os.path.join(data_dir, 'logs', agent.name)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # 按 conversation 隔离 SQLite，避免并发 benchmark 时全局锁竞争。
        self.database_path = get_database_path(conv_id)

        self.log = Log(agent.name, log_path=log_path)
        self.log.session = None
        self.session_create(session_id)

    async def _poll_and_inject_external_events(self):
        """轮询外部事件并注入到当前 Agent 上下文。"""
        if self.agent.context_manager is None:
            return
        events = await self.agent.context_manager.poll_external_events()
        for event in events:
            await self.agent.update_context({
                "role": "system",
                "content": f"【{event['event_type']}】{event['content']}"
            })
            self.log.update_content(
                f"{Color.YELLOW}[外部事件] {event['event_type']}: {self._truncate(event['content'], 200)}{Color.END}\n"
            )

    async def run(self):
        '''
        reAct的核心方法，执行agent的任务。
        '''
        # 确保上下文管理器已初始化，并加载初始上下文
        await self.agent.get_context()
        
        while self._continue:
            self.session.state = 'thinking'
            
            # 每轮推理前，轮询并注入外部事件
            await self._poll_and_inject_external_events()
            
            tool_calls = await self.reasoning()
            
            # 如果没有工具调用且有内容，或者已经停止
            if not tool_calls:
                # 检查最后一条消息内容
                context = await self.agent.get_context()
                content = context[-1].get('content', '') if context else ''
                if content:
                    self.session.state = 'sleeping'
                    # 更新数据库结果
                    db = ConversationDB.from_path(self.database_path)
                    async with db.aconnect() as con:
                        await con.execute(
                            "UPDATE session SET state = ?, result = ? WHERE session_id = ?",
                            ('sleeping', content, self.session.id)
                        )
                        await con.commit()
                    return content
            
            self.session.state = 'acting'
            stopped = await self.act_result(tool_calls)
            
            if stopped:
                self.session.state = 'sleeping'
                context = await self.agent.get_context()
                content = context[-1].get('content', '任务已完成') if context else '任务已完成'
                if self.agent.id != 'a-0':
                    await self.agent.clear_context()
                    print(f"Agent {self.agent.name}上下文已释放！")
                return content

    async def reasoning(self) -> list:
        '''
        reAct的推理方法，分析agent的上下文和工具，决定下一步行动。
        '''
        agent = self.agent
        # agent.prompt 是身份 prompt，必须保留，不允许被任务要求覆盖。
        response = await agent.llm_call()
        final_response = ''
        reasoning_content = ''
        tool_calls = []
        message = None
        
        if agent.is_stream:
            tool_call_buffer = {}  
            self.log.update_content(f'{Color.CYAN}{agent.name}[reasoning]:{Color.END}\n')
            
            reasoning_buffer = ""
            try:
                for chunk in response:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta
                    finish_reason = choice.finish_reason
                    token = delta.content
                
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        reasoning_buffer += delta.reasoning_content

                    if token:
                        final_response += token
                        self.log.update_content(token)

                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            tc_idx = tc_chunk.index
                            chunk_dict = tc_chunk.model_dump(exclude_none=True)

                            if tc_idx not in tool_call_buffer:
                                tool_call_buffer[tc_idx] = {}

                            tool_call_buffer[tc_idx] = dynamic_deep_merge(
                                tool_call_buffer[tc_idx], 
                                chunk_dict
                            )

                    if finish_reason == 'tool_calls' or (finish_reason == 'stop' and tool_call_buffer):
                        if reasoning_buffer:
                            self.log.update_content(f"{Color.DARKCYAN}[thinking]{reasoning_buffer}{Color.END}\n")
                            reasoning_content = reasoning_buffer
                            reasoning_buffer = ""
                    
                        for tc_data in tool_call_buffer.values():
                            tool_calls.append(tc_data)
                            func_name = tc_data.get('function', {}).get('name', 'Unknown')
                            self.log.update_content(new_content=f"{Color.GREEN}工具调用: {func_name}{Color.END}\n")
            
                tool_call_buffer.clear()
                # 流式输出结束时，如果还有未打印的 reasoning_content，补打出来
                if reasoning_buffer:
                    self.log.update_content(f"{Color.DARKCYAN}[thinking]{reasoning_buffer}{Color.END}\n")
            except (httpx.HTTPError, openai.APIConnectionError) as e:
                self.log.update_content(
                        new_content=f"{Color.RED}[reasoning步骤]出现网络错误：{e}，{2 ** (self._reset_count+1)}秒后重试"
                        )
                self._reset_count += 1
                time.sleep(2 ** self._reset_count)
                # 重试，只是网络问题的话让用户自行等待或者切断程序
                return self.reasoning()
            except Exception as e:
                self.log.update_content(new_content=f"{Color.RED}[reasoning步骤]未知的错误：{e}")
                raise e

             
        else:
            message = response.choices[0].message
            final_response = message.content
            if hasattr(message, 'reasoning_content') and message.reasoning_content:
                reasoning_content = message.reasoning_content
            # 非流式模式下，模型返回的 reasoning_content 也打印出来
            if reasoning_content:
                self.log.update_content(f"{Color.DARKCYAN}[thinking]{reasoning_content}{Color.END}\n")
            self.log.update_content(f'{Color.CYAN}{agent.name}[reasoning]:{Color.END}\n{final_response}\n')
            
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_calls.append(tool_call.model_dump(exclude_none=True))

        # 构建完整的 assistant 消息写入上下文
        if message:  # 非stream模式
            new_block = message.model_dump(exclude_none=True)
        else:  # stream模式
            new_block = {'role': 'assistant'}
            if reasoning_content:
                new_block['reasoning_content'] = reasoning_content
            if final_response:
                new_block['content'] = final_response
            else:
                new_block['content'] = None
            
            if tool_calls:
                new_block['tool_calls'] = tool_calls
        
        # 延迟加载逻辑：如果有 tool_calls，先存入 undos 缓冲区
        if tool_calls:
            self.undos.append(new_block)
        elif not self._is_empty_assistant_block(new_block):
            await agent.update_context(new_block)
            
        return tool_calls

    @staticmethod
    def _is_empty_assistant_block(block: dict) -> bool:
        """判断一条消息是否为没有有效载荷的 assistant 空消息。"""
        if block.get("role") != "assistant":
            return False
        has_content = bool(block.get("content"))
        has_reasoning = bool(block.get("reasoning_content"))
        has_tool_calls = bool(block.get("tool_calls"))
        return not (has_content or has_reasoning or has_tool_calls)

    async def _commit_undos(self):
        '''将缓冲区中的消息提交到上下文。'''
        while self.undos:
            await self.agent.update_context(self.undos.pop(0))

    @staticmethod
    def _truncate(text: str, max_len: int = 200) -> str:
        '''截断长文本，用于日志展示。'''
        if not text:
            return text
        if len(text) > max_len:
            return text[:max_len] + '...'
        return text

    def _summarize_args(self, tool_name: str, args: dict) -> str:
        '''生成工具参数的可读摘要，避免把完整大文件内容打印到日志。'''
        if not args:
            return ''
        # 对常见大字段做截断
        display = {}
        for k, v in args.items():
            s = str(v)
            display[k] = self._truncate(s, max_len=300)
        summary = json.dumps(display, ensure_ascii=False)
        return self._truncate(summary, max_len=600)

    def _summarize_result(self, tool_name: str, result: dict) -> str:
        '''生成工具结果的可读摘要。'''
        # 优先取常用字段
        text = (
            result.get('message')
            or result.get('result')
            or result.get('content')
            or json.dumps(result, ensure_ascii=False)
        )
        return self._truncate(str(text), max_len=400)

    async def act_result(self, tool_calls: list):
        '''
        并发执行 reasoning 阶段收集到的 tool_calls。
        tool_calls 为标准 OpenAI 格式的 dict 列表。
        返回 bool：是否检测到 stop 工具并请求终止循环。
        '''
        session = self.session
        tools_list = get_tools_lst()
        
        # 并发执行所有工具调用
        acts = []
        tool_call_ids = []
        tool_names = []
        stop_requested = False
        
        for tool_call in tool_calls:
            tool_name = tool_call.get('function', {}).get('name', 'Unknown')
            tool_call_id = tool_call.get('id')
            tool_args_raw = tool_call.get('function', {}).get('arguments', {})
            
            try:
                if isinstance(tool_args_raw, str):
                    # strict=False 允许 JSON 字符串中出现未转义的换行/控制字符，
                    # 这是 LLM 生成 text_writer 等多行参数时的常见情况。
                    tool_args = json.loads(tool_args_raw, strict=False)
                else:
                    tool_args = tool_args_raw
            except json.JSONDecodeError as e:
                # 如果 JSON 解析失败，将错误作为工具结果返回给 Agent
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': f"【系统错误】工具参数解析失败 (JSON Error): {str(e)}。请确保参数格式正确。"
                }
                await self._commit_undos()
                await self.agent.update_context(result_block)
                self.log.update_content(f"{Color.RED}参数解析失败: {tool_name}{Color.END}\n")
                continue
            
            if tool_name == 'stop':
                self._continue = False
                stop_requested = True
            
            args_summary = self._summarize_args(tool_name, tool_args)
            self.log.update_content(
                f"{Color.YELLOW}执行工具: {tool_name}{Color.END}"
                f"{(' 参数: ' + args_summary) if args_summary else ''}\n"
            )
            
            found = False
            for tool in tools_list:
                # NOTE: get_tools_lst() 现在返回实例对象（不再是类），因此直接用 tool.tool_name 匹配。
                if tool.tool_name == tool_name:
                    # 统一注入当前 agent 到工具实例中，以便工具内部获取上下文和进行安全审计
                    # 我知道这是很粗糙的设计，因为Agent不应该承载这么多的上下文信息，但不妨把
                    # Agent看成一个运行状态机，reAct专注过程，Agent专注状态
                    tool_instance = tool.__class__(subagent=self.agent)
                    
                    input_schema_class = tool_instance.input_schema
                    input_instance = input_schema_class(**tool_args)
                    session.state = 'waiting'
                    acts.append(tool_instance.safe_call(input_instance, session))
                    tool_call_ids.append(tool_call_id)
                    tool_names.append(tool_name)
                    found = True
                    break
            
            if not found:
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': f"【系统错误】找不到工具: {tool_name}。请检查工具名称是否正确。"
                }
                await self._commit_undos()
                await self.agent.update_context(result_block)
        
        # 记录 tool_call_id 到工具名的映射，方便结果日志展示
        id_to_name = dict(zip(tool_call_ids, tool_names))

        if acts:
            # 使用 return_exceptions=True，确保单个工具崩溃不影响其他工具，且能捕获异常
            tool_results = await asyncio.gather(*acts, return_exceptions=True)
            await self._commit_undos()
            
            # 每个工具结果单独作为一条消息
            for tool_result, tool_call_id in zip(tool_results, tool_call_ids):
                tool_name = id_to_name.get(tool_call_id, 'Unknown')
                image_path = None
                if isinstance(tool_result, Exception):
                    # 如果工具执行抛出了异常，将错误信息反馈给 Agent
                    content = f"【系统错误】工具执行发生异常: {str(tool_result)}"
                    self.log.update_content(f"{Color.RED}工具异常: {tool_name}: {str(tool_result)}{Color.END}\n")
                else:
                    result_dict = tool_result.toJson()
                    content = json.dumps(result_dict)
                    # 自动提取图片路径（如果工具输出中包含该字段）
                    if result_dict.get('image_path'):
                        image_path = result_dict.get('image_path')
                    summary = self._summarize_result(tool_name, result_dict)
                    status_color = Color.GREEN if result_dict.get('is_success', result_dict.get('is_written', result_dict.get('stopped', True))) else Color.RED
                    self.log.update_content(
                        f"{status_color}工具完成: {tool_name} -> {summary}{Color.END}\n"
                    )
                
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': content
                }
                if image_path:
                    result_block['image_path'] = image_path
                    
                await self.agent.update_context(result_block)
            
            session.state = 'thinking'

        return stop_requested

    def session_create(self, session_id: str = None) -> None:
        '''
        创建session，记录agent的整个生命周期。
        Session 文件放在 agent 所属 conversation 的 sessions/ 目录下。
        同时写入数据库作为单一事实来源。
        '''
        data_dir = get_config().data_dir
        if not self.database_path:
            self.database_path = get_database_path(getattr(self.agent, 'conversation_id', 'default'))
        conv_id = getattr(self.agent, 'conversation_id', 'default')
        # 如果调用方指定了 session_id（如 SubAgentLauncher），则直接使用；否则按时间生成。
        session_id = session_id if session_id else f'{self.agent.id}_{datetime.now().isoformat()}'
        if conv_id and conv_id != 'default':
            _path = os.path.join(data_dir, 'conversations', conv_id, 'sessions', session_id + '.json')
        else:
            _path = os.path.join(data_dir, 'sessions', session_id + '.json')
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        session_ = Session(id=session_id, path=_path)
        self.session = session_
        self.log.session = session_

        # 数据库为单一事实来源：创建即入库
        db = ConversationDB.from_path(self.database_path)
        with db.connect() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO session (session_id, state, result) VALUES (?, ?, ?)",
                (session_.id, 'sleeping', '')
            )
            con.commit()
        return
    
    def kill(self):
        session = self.session
        session.state = 'killed'
        session.upload_json()
        self._continue = False
        # 同步数据库
        db = ConversationDB.from_path(self.database_path)
        with db.connect() as con:
            cur = con.cursor()
            cur.execute(
                "UPDATE session SET state = ? WHERE session_id = ?",
                ('killed', session.id)
            )
            con.commit()


class Coordinator_reAct(reAct):
    '''
    协调者agent的react进程
    '''
    session: Session

    def __init__(self, agent: Agent):
        # Coordinator 的身份 prompt 已包含 ReAct 工作指南，
        # 这里不再传入额外 query，让 agent.query（用户原始输入）作为第一条 user 消息。
        super().__init__(agent=agent)
        self.log.is_main = True

    async def run(self):
        result = await super().run()
        return result
