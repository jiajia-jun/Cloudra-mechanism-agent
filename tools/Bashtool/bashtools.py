from session_class import Session
from typing import Any
import asyncio
from tools_class import Tool, input_schema, output_schema
from agent import Agent
import uuid
from pydantic import Field

bashtool_pool = [
'grep', 'awk', 'sed', 'cd', 'ls', 
'pwd', 'rm', 'mkdir', 'mv' ,'cp' ,
'find', 'head', 'tail', 'python', 
'pip', 'conda', 'git', 'docker',
'docker-compose', 'kubectl', 'kubectx',
'kubens', 'ssh', 'source', 'export', 'node',
'npm', 'yarn', 'curl', 'wget', 'tar',
'top', 'ps', 'whoami', 'uname', 'id',
'ifconfig', 'netstat', 'lsof', 'ps',
'netstat', 'lsof', 'netstat','ping',
'cargo', 'go', 'whoami', 'nproc',
'echo', '>' , '>>', 'sep', '&&', '||',

]

scripttool_pool = [
'python', 'bash', 'sh',
'cargo', 'yarn', 'cargo', 'go' ,'g16'
]

readtool_pool = [
'ls', 'pwd', 'cat', 'head', 'tail',
'grep', 'find', 'wc', 'id', 'whoami',
'curl', 'top', 'ps', 'ifconfig',
'netstat', 'lsof', 'ping'
]

writetool_pool = [
'awk', 'sed', 'echo', '>>', '>',
]

managetool_pool = []

destructivetool_pool = [
'rm', 'mv', 'cp', 'git', 'docker', 
'kubectl', 'kubectx', 'kubens', 'ssh', 
'docker-compose', 'pip', 'conda', 'npm', 
'export', 'source', 'wget', 'tar', 'node',
'cargo', 'go', '>'
]





class Bashtools_input_schema(input_schema):

    command: str = Field(description = '需要执行的命令。')

    terminal_id: str = Field(description = '命令执行的终端编号，用于区分不同的终端，可自行指定，通过这个功能可以实现并发执行。', 
                             default_factory = lambda: str(uuid.uuid4()))

    timeout: int = Field(description = '',default = 60)

class Bashtools_output_schema(output_schema):

    result: str = Field(description = 'bash工具结果。')
    terminal_id: str = Field(description = '输入或已默认的uuid。')
    run_command: str = Field(description = '调用的bash指令。')


class Bashtools(Tool):

    tool_id: str = 't-1'
    tool_name: str = 'bashtools'
    input_schema: Any = Bashtools_input_schema
    output_schema: Any = Bashtools_output_schema
    subagent: Agent = None
    tool_description: str = 'bash工具，用于执行终端命令'

    def __init__(self, subagent: Agent = None, **data) -> None:
        super().__init__(**data)
        self.subagent = subagent
        if subagent is not None:
            availables = self.allowed_tools_lst(subagent)
            count = 0
            tool_str = ''
            for t in availables:
                tool_str += t + ' '
                count += 1
                if count % 5 == 0:
                    tool_str += '\n'
            if not tool_str:
                tool_str = "无可调用工具"
            self.tool_description = f'''
您可调用的工具有：{tool_str}
请自行书写指令运行，在需要用到bash工具时调用。
'''

        

    def is_script(self, command: str) -> bool:
        for command_block in scripttool_pool:
            if command_block in command:
                return True
        return False
    
    def is_destructive(self, command: str):
        for command_block in destructivetool_pool:
            if command_block in command:
                return True
        return False

    def is_read(self, command: str):
        for command_block in readtool_pool:
            if command_block in command:
                return True
        return False

    def is_write(self, command: str):
        for command_block in writetool_pool:
            if command_block in command:
                return True
        return False

    def is_manage(self, command: str):
        return False

    def permission_all(self, command: str) -> list:
        return [self.is_read(command), self.is_write(command), self.is_manage(command), self.is_script(command), self.is_destructive(command)]
    
    def allowed_tools_lst(self, subagent: Agent = None) -> list:
        if subagent is None:
            return bashtool_pool
        
        pool = bashtool_pool
        agent_permission = subagent.permission_all()
        
        allowed_tools = []
        for tool in pool:
            tool_permission = self.permission_all(tool)
            flag = True
            for tool_perm,agent_perm in zip(tool_permission, agent_permission):
                if tool_perm and not agent_perm:
                    flag = False
                    break
            if flag:
                allowed_tools.append(tool)
        
        return allowed_tools
    
    def tool_permission_all(self) -> list:
        return [False, False, False, False, False]
    
    def has_command_permission(self, command: str) -> bool:
        if self.subagent is None:
            return True
        tool_perms = self.permission_all(command)
        agent_perms = self.subagent.permission_all()
        for tp, ap in zip(tool_perms, agent_perms):
            if tp and not ap:
                return False
        return True
    
    async def tool_call(self, input_instance: Bashtools_input_schema, session: Session) -> Bashtools_output_schema:
        command = input_instance.command
        timeout = input_instance.timeout
        terminal_id = input_instance.terminal_id
        
        if not self.has_command_permission(command):
            result = f'没有权限执行该命令: {command}'
            return Bashtools_output_schema(result=result, terminal_id=terminal_id, run_command=command)

        # 触发安全检查
        if self.is_destructive(command) or self.is_script(command):
            details = (
                f"【动作】: 执行危险终端命令\n"
                f"【终端 ID】: {terminal_id}\n"
                f"【执行指令】: {command}"
            )
            if not await self.ensure_safety(session, details=details):
                return Bashtools_output_schema(
                    result="【安全拦截】该危险指令已被拒绝执行。",
                    terminal_id=terminal_id,
                    run_command=command
                )

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        session.tool_calling[terminal_id] = command
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            result = '命令执行超时！'
            return Bashtools_output_schema(result=result, terminal_id=terminal_id, run_command=command)
        except Exception as e:
            print(e)
            result = f'命令执行失败:{e}'
            del session.tool_calling[terminal_id]
            return Bashtools_output_schema(result=stderr.decode('utf-8'), terminal_id=terminal_id, run_command=command)
        del session.tool_calling[terminal_id]
        result = stdout.decode('utf-8')
        if stderr:
            result += stderr.decode('utf-8')
        return Bashtools_output_schema(result=result, terminal_id=terminal_id, run_command=command)



def get_class():
    return Bashtools
