
import os
import sqlite3
from agent import Agent
import asyncio
import json
from log_class import Log
from tools_class import input_schema,get_tools
from tools import get_tools_lst
from session_class import Session


def dynamic_deep_merge(buffer_dict: dict, delta_dict: dict) -> dict:
    """通用动态拼接工具：不硬编码任何字段名，自动合并字符串，自动递归字典"""
    for key, value in delta_dict.items():
        if isinstance(value, dict):
            # 如果是嵌套字典（比如 'function'），递归进去拼接
            if key not in buffer_dict:
                buffer_dict[key] = {}
            dynamic_deep_merge(buffer_dict[key], value)
            
        elif isinstance(value, str):
            # 如果是字符串（比如 'id', 'name', 'arguments'），执行累加操作
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
    database_path: str = 'tasks/database.db'
    
    def __init__(self , agent: Agent, prompt: str = ""):
        self.agent = agent
        # 如果调用者显式提供了 prompt（即 Coordinator 定义的），则优先使用它实现任务隔离
        self.prompt = prompt if prompt else agent.prompt
        self.log = Log(agent.name)
        self.log.session = None
        
        conv_id = getattr(agent, 'conversation_id', 'default')
        if conv_id and conv_id != 'default':
            log_path = os.path.join('conversations', conv_id, 'logs', agent.name)
        else:
            log_path = os.path.join('logs', agent.name)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        self.log = Log(agent.name, log_path=log_path)
        self.log.session = None
        self.session_create()

    async def run(self):
        '''
        reAct的核心方法，执行agent的任务。
        '''
        while self._continue:
            self.session.state = 'thinking'
            tool_calls = self.reasoning()
            
            # 如果没有工具调用且有内容，或者已经停止
            if not tool_calls:
                # 检查最后一条消息内容
                content = self.agent.context[-1].get('content', '')
                if content:
                    self.session.state = 'sleeping'
                    # 更新数据库结果
                    con = sqlite3.connect(self.database_path, timeout=10)
                    cur = con.cursor()
                    cur.execute(
                        "UPDATE session SET state = ?, result = ? WHERE session_id = ?",
                        ('sleeping', content, self.session.id)
                    )
                    con.commit()
                    con.close()
                    return content
            
            self.session.state = 'acting'
            stopped = await self.act_result(tool_calls)
            
            if stopped:
                self.session.state = 'sleeping'
                content = self.agent.context[-1].get('content', '任务已完成')
                return content

    def reasoning(self) -> list:
        '''
        reAct的推理方法，分析agent的上下文和工具，决定下一步行动。
        '''
        agent = self.agent
        # 使用统一的 prompt
        agent.prompt = self.prompt
        response = agent.llm_call()
        final_response = ''
        reasoning_content = ''
        tool_calls = []
        message = None
        
        if agent.is_stream:
            tool_call_buffer = {}  
            self.log.update_content(f'{Color.CYAN}{agent.name}[reasoning]:{Color.END}\n')
            
            reasoning_buffer = ""
            
            for chunk in response:
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
                    
                    for tc_data in tool_call_buffer.values():
                        tool_calls.append(tc_data)
                        func_name = tc_data.get('function', {}).get('name', 'Unknown')
                        self.log.update_content(new_content=f"{Color.GREEN}工具调用: {func_name}{Color.END}\n")
            
            tool_call_buffer.clear()
             
        else:
            message = response.choices[0].message
            final_response = message.content
            if hasattr(message, 'reasoning_content') and message.reasoning_content:
                reasoning_content = message.reasoning_content
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
        
        agent.update_context(new_block)
        return tool_calls

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
        stop_requested = False
        
        for tool_call in tool_calls:
            tool_name = tool_call.get('function', {}).get('name', 'Unknown')
            tool_call_id = tool_call.get('id')
            tool_args_raw = tool_call.get('function', {}).get('arguments', {})
            
            try:
                if isinstance(tool_args_raw, str):
                    tool_args = json.loads(tool_args_raw)
                else:
                    tool_args = tool_args_raw
            except json.JSONDecodeError as e:
                # 如果 JSON 解析失败，将错误作为工具结果返回给 Agent
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': f"【系统错误】工具参数解析失败 (JSON Error): {str(e)}。请确保参数格式正确。"
                }
                self.agent.update_context(result_block)
                self.log.update_content(f"{Color.RED}参数解析失败: {tool_name}{Color.END}\n")
                continue
            
            if tool_name == 'stop':
                self._continue = False
                stop_requested = True
            
            self.log.update_content(f"{Color.YELLOW}执行工具: {tool_name}{Color.END}\n")
            
            for tool in tools_list:
                # NOTE: get_tools_lst() 现在返回实例对象（不再是类），因此直接用 tool.tool_name 匹配。
                if tool.tool_name == tool_name:
                    # 需要注入 subagent 的工具（bashtools、SubAgentLauncher）
                    # 由于 get_tools_lst() 已预先无参实例化，这些工具的 subagent 为 None，
                    # 这里需要重新实例化并注入当前 agent。
                    if tool_name in ('bashtools', 'SubAgentLauncher'):
                        tool_instance = tool.__class__(subagent=self.agent)
                    else:
                        tool_instance = tool  # 其他工具直接用预生成的实例
                    input_schema_class = tool_instance.input_schema
                    input_instance = input_schema_class(**tool_args)
                    session.state = 'waiting'
                    acts.append(tool_instance.tool_call(input_instance, session))
                    tool_call_ids.append(tool_call_id)
                    break
        
        if acts:
            # 使用 return_exceptions=True，确保单个工具崩溃不影响其他工具，且能捕获异常
            tool_results = await asyncio.gather(*acts, return_exceptions=True)
            
            # 每个工具结果单独作为一条消息
            for tool_result, tool_call_id in zip(tool_results, tool_call_ids):
                if isinstance(tool_result, Exception):
                    # 如果工具执行抛出了异常，将错误信息反馈给 Agent
                    content = f"【系统错误】工具执行发生异常: {str(tool_result)}"
                    self.log.update_content(f"{Color.RED}工具异常: {str(tool_result)}{Color.END}\n")
                else:
                    content = json.dumps(tool_result.toJson())
                
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': content
                }
                self.agent.update_context(result_block)
            
            session.state = 'thinking'

        return stop_requested

    def session_create(self) -> None:
        '''
        创建session，记录agent的整个生命周期。
        Session 文件放在 agent 所属 conversation 的 sessions/ 目录下。
        同时写入数据库作为单一事实来源。
        '''
        session_id = f'{self.agent.id}_?'
        conv_id = getattr(self.agent, 'conversation_id', 'default')
        if conv_id and conv_id != 'default':
            _path = os.path.join('conversations', conv_id, 'sessions', session_id + '.json')
        else:
            _path = os.path.join('sessions', session_id + '.json')
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        session_ = Session(id=session_id, path=_path)
        session_.id = f'{self.agent.id}_{session_.create_time}'
        self.session = session_
        self.log.session = session_

        # 数据库为单一事实来源：创建即入库
        con = sqlite3.connect(self.database_path, timeout=10)
        cur = con.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute(
            "INSERT OR IGNORE INTO session (session_id, state, result) VALUES (?, ?, ?)",
            (session_.id, 'sleeping', '')
        )
        con.commit()
        con.close()
        return
    
    def kill(self):
        session = self.session
        session.state = 'killed'
        session.upload_json()
        self._continue = False
        # 同步数据库
        con = sqlite3.connect(self.database_path, timeout=10)
        cur = con.cursor()
        cur.execute(
            "UPDATE session SET state = ? WHERE session_id = ?",
            ('killed', session.id)
        )
        con.commit()
        con.close()


class Coordinator_reAct(reAct):
    '''
    协调者agent的react进程
    '''
    session: Session

    def __init__(self, agent: Agent):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, 'tasks', 'database.db')
        super().__init__(
            agent=agent,
            prompt=(
                '**你是一个最高级别的任务协调者（Coordinator）。你掌控着整个系统的运行。**\n'
                '你的核心职责与权力：\n'
                '1. **任务拆解与隔离**：将用户需求拆解为独立的子任务。通过 `SubAgentLauncher` 分发任务。\n'
                '2. **定义子 Agent 行为**：子 Agent (a-1, a-2, a-3) 只是你的工具，它们的“人格”和“规则”由你通过 `reasoning_prompt` 动态决定。为了任务隔离，请务必在 `reasoning_prompt` 中明确它们的任务范围和行为禁令（例如：“你现在的身份是纯净的文案录入员，只允许调用 text_writer，严禁搜索”）。\n'
                '3. **绝对路径导航**：必须在指令中提供工作目录的绝对路径。\n'
                '4. **结果评估与终结**：你是唯一有权决定任务是否完成的人。汇总子任务结果后，给出最终答复并调用 stop 结束。\n'
                '**记住：你是系统的大脑，子 Agent 的所有行为都应在你的严密定义的 prompt 框架下运行。**'
            )
        )
        self.database_path = db_path
        self.query = agent.query
        self.log.is_main = True
