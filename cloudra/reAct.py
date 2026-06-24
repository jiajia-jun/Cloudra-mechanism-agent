import time
import httpx
import openai 
import os
import sqlite3
from cloudra.agent import Agent
import asyncio
import json
from datetime import datetime
from cloudra.log_class import Log
from cloudra.tools_class import input_schema,get_tools
from cloudra.tools import get_tools_lst
from cloudra.session_class import Session
from cloudra.config import get_config


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
    database_path: str = ''
    undos: list = []
    _reset_count: int = 0
    
    def __init__(self , agent: Agent, prompt: str = "", session_id: str = None):
        self.agent = agent
        # 如果调用者显式提供了 prompt（即 Coordinator 定义的），则优先使用它实现任务隔离
        self.prompt = prompt if prompt else agent.prompt
        self.log = Log(agent.name)
        self.log.session = None
            
        data_dir = get_config().data_dir
        conv_id = getattr(agent, 'conversation_id', 'default')
        if conv_id and conv_id != 'default':
            log_path = os.path.join(data_dir, 'conversations', conv_id, 'logs', agent.name)
        else:
            log_path = os.path.join(data_dir, 'logs', agent.name)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        self.log = Log(agent.name, log_path=log_path)
        self.log.session = None
        self.session_create(session_id)

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
            try:
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
        else:
            agent.update_context(new_block)
            
        return tool_calls

    def _commit_undos(self):
        '''将缓冲区中的消息提交到上下文。'''
        while self.undos:
            self.agent.update_context(self.undos.pop(0))

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
                self._commit_undos()
                self.agent.update_context(result_block)
                self.log.update_content(f"{Color.RED}参数解析失败: {tool_name}{Color.END}\n")
                continue
            
            if tool_name == 'stop':
                self._continue = False
                stop_requested = True
            
            self.log.update_content(f"{Color.YELLOW}执行工具: {tool_name}{Color.END}\n")
            
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
                    found = True
                    break
            
            if not found:
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': f"【系统错误】找不到工具: {tool_name}。请检查工具名称是否正确。"
                }
                self._commit_undos()
                self.agent.update_context(result_block)
        
        if acts:
            # 使用 return_exceptions=True，确保单个工具崩溃不影响其他工具，且能捕获异常
            tool_results = await asyncio.gather(*acts, return_exceptions=True)
            self._commit_undos()
            
            # 每个工具结果单独作为一条消息
            for tool_result, tool_call_id in zip(tool_results, tool_call_ids):
                image_path = None
                if isinstance(tool_result, Exception):
                    # 如果工具执行抛出了异常，将错误信息反馈给 Agent
                    content = f"【系统错误】工具执行发生异常: {str(tool_result)}"
                    self.log.update_content(f"{Color.RED}工具异常: {str(tool_result)}{Color.END}\n")
                else:
                    result_dict = tool_result.toJson()
                    content = json.dumps(result_dict)
                    # 自动提取图片路径（如果工具输出中包含该字段）
                    if result_dict.get('image_path'):
                        image_path = result_dict.get('image_path')
                
                result_block = {
                    'role': 'tool',
                    'tool_call_id': tool_call_id,
                    'content': content
                }
                if image_path:
                    result_block['image_path'] = image_path
                    
                self.agent.update_context(result_block)
            
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
            self.database_path = os.path.join(data_dir, 'tasks', 'database.db')
        conv_id = getattr(self.agent, 'conversation_id', 'default')
        # 如果调用方指定了 session_id（如 SubAgentLauncher），则直接使用；否则按时间生成。
        session_id = session_id if session_id else f'{self.agent.id}_{datetime.now().isoformat()}'
        if conv_id and conv_id != 'default':
            _path = os.path.join(data_dir, 'conversations', conv_id, 'sessions', session_id + '.json')
        else:
            _path = os.path.join(data_dir, 'sessions', session_id + '.json')
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        session_ = Session(id=session_id, path=_path)
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
        data_dir = get_config().data_dir
        db_path = os.path.join(data_dir, 'tasks', 'database.db')
        super().__init__(
            agent=agent,
            prompt=(
                '# Role: 最高级任务协调者 (Coordinator)\n\n'
                '## 核心使命\n'
                '你掌控着整个 Cloudra 系统的运行。你的任务是接收用户复杂的化学科研需求，通过科学的拆解与指派，调动子 Agent 协作完成目标。\n\n'
                '## 核心职责与权力\n'
                '1. **任务拆解 (Decomposition)**: 将模糊的需求转化为清晰、逻辑连贯的子任务。使用 `SubAgentLauncher` 启动子 Agent。\n'
                '2. **全程监控 (Oversight)**: 当子 Agent 完成后，如果 `SubAgentLauncher` 返回的摘要信息不足以辅助决策，你必须调用 `get_subagent_report` 来获取该任务的完整执行过程（包含推理、工具调用及详细结论）。\n'
                '3. **环境塑造 (Environment Injection)**: 子 Agent (a-1, a-2, a-3) 是你的数字化肢体。你必须通过 `reasoning_prompt` 为它们注入：\n'
                '   - **临时身份**: 明确它们在当前任务中的角色。\n'
                '   - **行动范围**: 明确可以调用的工具，并**显式禁止**不相关的危险操作。\n'
                '   - **背景上下文**: 提供完成任务所需的关键信息或文件路径。\n'
                '3. **绝对路径原则**: 所有的文件操作、路径描述必须使用**绝对路径**以确保多进程环境下的执行准确性。\n'
                '4. **安全合规 (Safety Audit)**: 系统已启用危险操作审计。当子 Agent 执行 `TextWriter` 或 `bashtools` 下的危险指令时，将进入人工审批流。请告知子 Agent 在执行此类操作前，必须在 Thought 中清晰阐述理由。\n'
                '5. **视觉锚点说明 (Visual Anchors)**: 在你的历史上下文中，可能会出现包含本地文件路径（如 `/path/to/image.png`）的 `image_url` 块。这些是系统内部的视觉锚点，代表你此前已“看到”或生成的图像。你无需解析路径字符串本身，只需将其视为对话中特定视觉信息的占位符即可。\n'
                '6. **专家分工 (Specialized Roles)**: \n'
                '   - **Visionary (a-4)**: 系统的“双眼”。它是视觉识别、图表解析和图像数据提取的唯一专家。任何涉及“看图、读图、分析图”的任务应指派给它。\n'
                '   - **Writer (a-2)**: 系统的“双手”。它擅长文档产出和代码编写（包括调用绘图工具生成图片），但它不具备专业的视觉分析能力。\n'
                '   - **Operator (a-5)**: 系统的“重装步兵”。专门执行危险操作、环境配置、大型脚本和大规模文件管理。它拥有最高权限，但其动作必须严审。\n'
                '   - **Coder (a-6)**: 系统的“架构师”。专注于高质量算法实现、科学计算脚本编写及代码重构。它是解决复杂逻辑和自动化工作流的首选专家。\n'
                '7. **结果评估与答复**: 你是唯一有权决定任务终结的人。汇总所有子任务成果后，给出最终、专业的回复并调用 `stop` 工具退出。\n\n'
                '## 工作指南\n'
                '- **严谨性**: 对于化学实验参数、文献结论，必须追求 100% 的准确性。\n'
                '- **隔离性**: 尽量让子任务独立，减少子 Agent 间的耦合。'
            )
        )
        self.database_path = db_path
        self.query = agent.query
        self.log.is_main = True

    async def run(self):
        result = await super().run()
        
        # 任务结束后，检查是否有新邮件并提醒
        try:
            from cloudra.tools.Interactool.email_reader import EmailReader, EmailReader_input_schema
            reader = EmailReader(subagent=self.agent)
            # 仅检查是否有未读邮件，不输出具体内容以节省 token
            inbox = await reader.tool_call(EmailReader_input_schema(count=1, only_unread=True), self.session)
            if inbox.success and inbox.emails:
                print(f"\n{Color.YELLOW}[系统提醒] 收件箱中有新的未读邮件，可能包含用户的最新反馈或指令。{Color.END}")
                # 向上下文注入一条系统提醒，让 Agent 知道有新消息
                self.agent.update_context({
                    "role": "system", 
                    "content": "【系统提醒】收件箱中有新的未读邮件，可能包含用户的最新反馈或指令，请在必要时调用 email_reader 查看。"
                })
        except Exception:
            pass # 忽略检查失败
            
        return result
