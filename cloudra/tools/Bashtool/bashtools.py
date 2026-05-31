from cloudra.session_class import Session
from typing import Any
import asyncio
from cloudra.tools_class import Tool, input_schema, output_schema
from cloudra.agent import Agent
import uuid
from pydantic import Field

from cloudra.tools.core.permission_model import Permission, check_permission
from cloudra.tools.core.command_analyzer import BashCommandClassifier


class Bashtools_input_schema(input_schema):
    command: str = Field(description='需要执行的命令。')
    terminal_id: str = Field(
        description='命令执行的终端编号，用于区分不同的终端，可自行指定，通过这个功能可以实现并发执行。',
        default_factory=lambda: str(uuid.uuid4())
    )
    timeout: int = Field(description='', default=60)


class Bashtools_output_schema(output_schema):
    result: str = Field(description='bash工具结果。')
    terminal_id: str = Field(description='输入或已默认的uuid。')
    run_command: str = Field(description='调用的bash指令。')


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
            tool_str = self._format_tool_list(availables)
            if not tool_str:
                tool_str = "无可调用工具"
            self.tool_description = f'''
您可调用的工具有：{tool_str}
请自行书写指令运行，在需要用到bash工具时调用。
'''

    def _format_tool_list(self, tools: list[str]) -> str:
        lines = []
        for i in range(0, len(tools), 5):
            lines.append(' '.join(tools[i:i+5]))
        return '\n'.join(lines)

    def tool_permission_all(self) -> Permission:
        # Bashtools is special: its permissions depend on the actual command.
        # Return NONE so that check_permission doesn't block it at the tool level.
        # Command-level permission is enforced by has_command_permission().
        return Permission.NONE

    def has_command_permission(self, command: str) -> bool:
        if self.subagent is None:
            return True
        analysis = BashCommandClassifier.classify(command)
        agent_perms = self.subagent.permission_all()
        return check_permission(agent_perms, analysis.permissions)

    def allowed_tools_lst(self, subagent: Agent = None) -> list[str]:
        """
        Return a list of command names the agent is allowed to use.
        """
        all_cmds = (
            BashCommandClassifier.READ_CMDS
            | BashCommandClassifier.WRITE_CMDS
            | BashCommandClassifier.SCRIPT_CMDS
            | BashCommandClassifier.DESTRUCTIVE_CMDS
        )

        if subagent is None:
            return sorted(all_cmds)

        agent_perms = subagent.permission_all()
        allowed = []

        for cmd in sorted(all_cmds):
            perms = Permission.NONE
            if cmd in BashCommandClassifier.READ_CMDS:
                perms |= Permission.READ
            if cmd in BashCommandClassifier.WRITE_CMDS:
                perms |= Permission.WRITE
            if cmd in BashCommandClassifier.SCRIPT_CMDS:
                perms |= Permission.SCRIPT
            if cmd in BashCommandClassifier.DESTRUCTIVE_CMDS:
                perms |= Permission.DESTRUCTIVE

            if check_permission(agent_perms, perms):
                allowed.append(cmd)

        return allowed

    async def tool_call(self, input_instance: Bashtools_input_schema, session: Session) -> Bashtools_output_schema:
        command = input_instance.command
        timeout = input_instance.timeout
        terminal_id = input_instance.terminal_id

        if not self.has_command_permission(command):
            result = f'没有权限执行该命令: {command}'
            return Bashtools_output_schema(result=result, terminal_id=terminal_id, run_command=command)

        # 触发安全检查
        analysis = BashCommandClassifier.classify(command)
        if analysis.permissions & (Permission.DESTRUCTIVE | Permission.SCRIPT):
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
        
        def decode_output(data: bytes) -> str:
            if not data:
                return ""
            import platform
            try:
                return data.decode('utf-8')
            except UnicodeDecodeError:
                if platform.system() == 'Windows':
                    for enc in ['gbk', 'cp936', 'cp437']:
                        try:
                            return data.decode(enc)
                        except UnicodeDecodeError:
                            continue
                return data.decode('utf-8', errors='replace')

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
            # Use safer decoding for stderr too
            err_msg = decode_output(stderr) if 'stderr' in locals() else str(e)
            return Bashtools_output_schema(result=err_msg, terminal_id=terminal_id, run_command=command)
        
        del session.tool_calling[terminal_id]
        result = decode_output(stdout)
        if stderr:
            result += "\n" + decode_output(stderr)
        return Bashtools_output_schema(result=result, terminal_id=terminal_id, run_command=command)


def get_class():
    return Bashtools
