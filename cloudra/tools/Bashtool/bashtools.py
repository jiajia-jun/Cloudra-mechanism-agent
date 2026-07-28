import asyncio
from typing import Any

from pydantic import Field

from cloudra.agent import Agent
from cloudra.session_class import Session
from cloudra.tools.core.command_analyzer import BashCommandClassifier
from cloudra.tools.core.permission_model import Permission, check_permission
from cloudra.tools_class import Tool, input_schema, output_schema


class Bashtools_input_schema(input_schema):
    command: str = Field(description='需要执行的命令。')
    # review：用 LLM 可理解的一句话描述该命令用途，方便前端展示与审批信息可读性。
    task_description: str = Field(
        description='一句话描述这条命令要完成的任务（用于前端展示与审批上下文）。',
        default='',
    )
    timeout: int = Field(description='', default=60)


class Bashtools_output_schema(output_schema):
    result: str = Field(description='bash工具结果。')
    task_description: str = Field(description='该命令的任务描述。')
    run_command: str = Field(description='调用的bash指令。')


class Bashtools(Tool):
    tool_id: str = 't-1'
    tool_name: str = 'bashtools'
    # 存放 schema 类对象而非实例；用 Any 是因为基类 Tool 已声明为 Any，
    # 开启 arbitrary_types_allowed 后 pydantic 不会对类对象做字段校验。
    input_schema: Any = Bashtools_input_schema
    output_schema: Any = Bashtools_output_schema
    subagent: Agent = None
    tool_description: str = (
        "执行搜索、环境检查、构建和测试等终端命令。"
        "不要用 Bash、sed、重定向、tee 或临时脚本修改工作区文件；"
        "已有文件使用 text_reader + edit_file，新建文件使用 text_writer。"
    )

    def __init__(self, subagent: Agent = None, **data) -> None:
        super().__init__(**data)
        self.subagent = subagent
        # 进行中的终端命令追踪（task_description -> command）：挂在工具实例上，
        # Session 只是内存镜像，不再承载工具运行态。
        self._terminal_commands: dict = {}
        if subagent is not None:
            availables = self.allowed_tools_lst(subagent)
            tool_str = self._format_tool_list(availables)
            # review：显式判断空列表，避免对 None 或空字符串做隐式转换。
            if availables:
                desc = (
                    f"可执行的命令有：\n{tool_str}\n"
                    "本工具用于搜索、环境检查、构建和测试。不要用 Bash、sed、"
                    "重定向、tee 或临时脚本修改工作区文件；请改用 edit_file/text_writer。"
                )
            else:
                desc = '当前没有可调用工具。'
            self.tool_description = desc

    def _format_tool_list(self, tools: list[str]) -> str:
        lines = []
        for i in range(0, len(tools), 5):
            lines.append(' '.join(tools[i:i + 5]))
        return '\n'.join(lines)

    def tool_permission_all(self) -> Permission:
        # Bashtools is special: its permissions depend on the actual command.
        # Return NONE so that check_permission doesn't block it at the tool level.
        # Command-level permission is enforced by has_command_permission().
        return Permission.NONE

    def has_command_permission(self, command: str) -> bool:
        # review：subagent 为 None 时不能默认放行全部权限，只允许只读命令，堵安全漏洞。
        if self.subagent is None:
            analysis = BashCommandClassifier.classify(command)
            return analysis.permissions == Permission.READ
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

        # review：subagent 为 None 时只允许读命令。
        if subagent is None:
            agent_perms = Permission.READ
        else:
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
        task_description = input_instance.task_description or command

        if not self.has_command_permission(command):
            result = f'没有权限执行该命令: {command}'
            return Bashtools_output_schema(result=result, task_description=task_description, run_command=command)

        # 触发安全检查
        analysis = BashCommandClassifier.classify(command)
        if analysis.permissions & (Permission.DESTRUCTIVE | Permission.SCRIPT):
            details = (
                f"【动作】: 执行危险终端命令\n"
                f"【任务描述】: {task_description}\n"
                f"【执行指令】: {command}"
            )
            approved, denial_reason = await self.ensure_safety(session, details=details, tool_args=input_instance.model_dump(mode="json"))
            if not approved:
                result_msg = "【安全拦截】该危险指令已被拒绝执行。"
                if denial_reason:
                    result_msg += f"\n拒绝原因: {denial_reason}"
                return Bashtools_output_schema(
                    result=result_msg,
                    task_description=task_description,
                    run_command=command
                )

        process = await asyncio.create_subprocess_shell(
            command,
            cwd=getattr(self.subagent, "working_directory", None),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        self._terminal_commands[task_description] = command

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
            return Bashtools_output_schema(result=result, task_description=task_description, run_command=command)
        except Exception as e:
            print(e)
            result = f'命令执行失败:{e}'
            self._terminal_commands.pop(task_description, None)
            # Use safer decoding for stderr too
            err_msg = decode_output(stderr) if 'stderr' in locals() else str(e)
            return Bashtools_output_schema(result=err_msg, task_description=task_description, run_command=command)

        self._terminal_commands.pop(task_description, None)
        result = decode_output(stdout)
        if stderr:
            result += "\n" + decode_output(stderr)
        return Bashtools_output_schema(result=result, task_description=task_description, run_command=command)


def get_class():
    return Bashtools
