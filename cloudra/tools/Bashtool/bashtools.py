import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.tools.core.bash_habit_guard import bash_file_write_warning
from cloudra.tools.core.command_analyzer import BashCommandClassifier
from cloudra.tools.core.coord_guard import handwritten_coord_warning
from cloudra.tools.core.permission_model import Permission, check_permission


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
    exit_code: int = Field(
        default=0,
        description='命令退出码：0 表示成功，非 0 表示失败。'
        '务必以退出码判断命令成败，不要根据输出文本猜测。',
    )


class Bashtools(Tool):
    tool_id: str = 't-1'
    tool_name: str = 'bashtools'
    # 存放 schema 类对象而非实例；用 Any 是因为基类 Tool 已声明为 Any，
    # 开启 arbitrary_types_allowed 后 pydantic 不会对类对象做字段校验。
    input_schema: Any = Bashtools_input_schema
    output_schema: Any = Bashtools_output_schema
    subagent: Agent = None
    tool_description: str = (
        "执行搜索、环境检查、构建和测试等终端命令，以退出码判断成败。"
        "适用：运行测试、安装依赖、查看环境信息、调用命令行工具。"
        "不适用：修改工作区文件——严禁用 Bash、sed、重定向、tee 或临时脚本改文件，"
        "已有文件用 text_reader + edit_file，新建文件用 text_writer。"
        "注意：命令文本里嵌入坐标块（如 heredoc 写 .gjf/.xyz）会被 harness 警告，"
        "坐标必须来自 smiles_to_mol / format_converter / gjf_writer 等工具。"
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
                    "本工具用于搜索、环境检查、构建和测试。"
                    "不适用：修改工作区文件——不要用 Bash、sed、重定向、tee 或临时脚本，"
                    "请改用 edit_file / text_writer。"
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
            return Bashtools_output_schema(result=result, task_description=task_description, run_command=command, exit_code=126)

        # 手写坐标 / bash 写文件习惯检查：命中时**照常执行**，把警告附在结果里
        # 让模型意识到行为不当（不硬拦）。coord 命中优先：它更具体，并直接点破
        # "绕过 supervisor 审查 / DAG 系统"。从日志提取坐标的正当流程走
        # sed/grep 管道，命令里不含坐标文本，不会被误伤。
        guard_warning = (
            handwritten_coord_warning(command, path=None)
            or bash_file_write_warning(command)
        )

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
                    run_command=command,
                    exit_code=126,
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
            return Bashtools_output_schema(result=result, task_description=task_description, run_command=command, exit_code=124)
        except Exception as e:
            print(e)
            result = f'命令执行失败:{e}'
            self._terminal_commands.pop(task_description, None)
            # Use safer decoding for stderr too
            err_msg = decode_output(stderr) if 'stderr' in locals() else str(e)
            return Bashtools_output_schema(result=err_msg, task_description=task_description, run_command=command, exit_code=1)

        self._terminal_commands.pop(task_description, None)
        exit_code = process.returncode if process.returncode is not None else 0
        stdout_text = decode_output(stdout)
        stderr_text = decode_output(stderr)
        result = stdout_text
        if stderr_text:
            result += ("\n" if result else "") + stderr_text
        if exit_code != 0:
            result = f"【命令失败】exit_code={exit_code}。输出：\n{result}"
        if guard_warning:
            result = f"{guard_warning}\n\n{result}"
        return Bashtools_output_schema(result=result, task_description=task_description, run_command=command, exit_code=exit_code)


def get_class():
    return Bashtools
