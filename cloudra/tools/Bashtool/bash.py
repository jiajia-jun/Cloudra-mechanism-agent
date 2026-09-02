import asyncio
from typing import Any

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.core.agent import Agent
from cloudra.tools.core.bash_habit_guard import bash_file_write_warning
from cloudra.tools.core.command_analyzer import BashCommandClassifier
from cloudra.tools.core.coord_guard import handwritten_coord_warning
from cloudra.tools.core.observation_offload import cap_observation
from cloudra.tools.core.permission_model import Permission, check_permission


class Bash_input_schema(input_schema):
    command: str = Field(description='The command to execute.')
    # review：用 LLM 可理解的一句话描述该命令用途，方便前端展示与审批信息可读性。
    task_description: str = Field(
        description='One-sentence description of what this command should accomplish (shown in the UI and approval context).',
        default='',
    )
    timeout: int = Field(description='Command timeout in seconds; the command is killed when it exceeds this limit.', default=60)


class Bash_output_schema(output_schema):
    result: str = Field(description='Bash tool result.')
    task_description: str = Field(description='Task description of this command.')
    run_command: str = Field(description='The bash command that was invoked.')
    exit_code: int = Field(
        default=0,
        description='Command exit code: 0 means success, non-zero means failure. '
        'Always judge success by the exit code, not by guessing from stdout.',
    )


class Bash(Tool):
    tool_id: str = 't-1'
    tool_name: str = 'bash'
    # 存放 schema 类对象而非实例；用 Any 是因为基类 Tool 已声明为 Any，
    # 开启 arbitrary_types_allowed 后 pydantic 不会对类对象做字段校验。
    input_schema: Any = Bash_input_schema
    output_schema: Any = Bash_output_schema
    subagent: Agent = None
    tool_description: str = (
        "Run terminal commands for search, environment checks, builds, and tests; judge success by exit code. "
        "Use for: running tests, installing dependencies, inspecting the environment, invoking CLI tools. "
        "Do not use for: modifying workspace files — never edit files with Bash, sed, redirection, tee, or throwaway scripts; "
        "edit existing files with text_reader + edit_file, create new files with text_writer. "
        "Note: embedding coordinate blocks in the command text (e.g. writing .gjf/.xyz via heredoc) triggers a harness warning; "
        "coordinates must come from tools such as smiles_to_mol / format_converter / qm_input_writer."
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
                    f"Available commands:\n{tool_str}\n"
                    "This tool is for search, environment checks, builds, and tests; judge success by exit code. "
                    "Do not use it to modify workspace files — do not use Bash, sed, redirection, tee, or throwaway scripts; "
                    "use edit_file / text_writer instead. "
                    "Note: embedding coordinate blocks in the command text (e.g. writing .gjf/.xyz via heredoc) triggers a harness warning; "
                    "coordinates must come from tools such as smiles_to_mol / format_converter / qm_input_writer."
                )
            else:
                desc = 'No shell commands are currently permitted in this context.'
            self.tool_description = desc

    def _format_tool_list(self, tools: list[str]) -> str:
        lines = []
        for i in range(0, len(tools), 5):
            lines.append(' '.join(tools[i:i + 5]))
        return '\n'.join(lines)

    def tool_permission_all(self) -> Permission:
        # Bash is special: its permissions depend on the actual command.
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

    async def tool_call(self, input_instance: Bash_input_schema, session: Session) -> Bash_output_schema:
        command = input_instance.command
        timeout = input_instance.timeout
        task_description = input_instance.task_description or command

        if not self.has_command_permission(command):
            result = f'No permission to run this command: {command}'
            return Bash_output_schema(result=result, task_description=task_description, run_command=command, exit_code=126)

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
            cmd_preview = command if len(command) <= 60 else f"{command[:57]}..."
            details = (
                f"Action: Execute shell command ({cmd_preview})\n"
                f"Task: {task_description}\n"
                f"Command: {command}"
            )
            approved, denial_reason = await self.ensure_safety(
                session,
                details=details,
                tool_args=input_instance.model_dump(mode="json"),
            )
            if not approved:
                result_msg = (
                    "[Safety block] The command was rejected and was not executed. "
                    "Next: explain to the user why the command was needed, adjust the approach, "
                    "or choose a safer alternative."
                )
                if denial_reason:
                    result_msg += f"\nRejection reason: {denial_reason}"
                return Bash_output_schema(
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
            result = 'Command timed out!'
            return Bash_output_schema(result=result, task_description=task_description, run_command=command, exit_code=124)
        except Exception as e:
            print(e)
            result = f'Command failed: {e}'
            self._terminal_commands.pop(task_description, None)
            # Use safer decoding for stderr too
            err_msg = decode_output(stderr) if 'stderr' in locals() else str(e)
            return Bash_output_schema(result=err_msg, task_description=task_description, run_command=command, exit_code=1)

        self._terminal_commands.pop(task_description, None)
        exit_code = process.returncode if process.returncode is not None else 0
        stdout_text = decode_output(stdout)
        stderr_text = decode_output(stderr)
        result = stdout_text
        if stderr_text:
            result += ("\n" if result else "") + stderr_text
        if exit_code != 0:
            result = f"[Command failed] exit_code={exit_code}. Output:\n{result}"
        result = await cap_observation(
            result,
            root=getattr(self.subagent, "working_directory", None),
            stem="bash",
        )
        if guard_warning:
            result = f"{guard_warning}\n\n{result}"
        return Bash_output_schema(result=result, task_description=task_description, run_command=command, exit_code=exit_code)


def get_class():
    return Bash
