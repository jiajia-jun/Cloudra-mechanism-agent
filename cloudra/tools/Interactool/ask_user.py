import asyncio
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Awaitable, Callable, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema

# 可插拔输入处理器：TUI 等前端注册后，ask_user 不再使用裸 input()，
# 而是把问题交给前端收集答案。签名: async (prompt_text: str) -> str
_input_handler: Optional[Callable[[str], Awaitable[str]]] = None
_context_input_handler: ContextVar[
    Optional[Callable[[str], Awaitable[str]]]
] = ContextVar("cloudra_ask_user_handler", default=None)


def set_input_handler(handler: Optional[Callable[[str], Awaitable[str]]]) -> None:
    """注册/清除 ask_user 的输入处理器（TUI 启动时注册，退出时清除）。"""
    global _input_handler
    _input_handler = handler


@contextmanager
def use_input_handler(handler: Callable[[str], Awaitable[str]]):
    """Scope an input handler to one Session task.

    API sessions may run concurrently, so a process-global callback would send
    one Agent's question to another Session. Context variables follow asyncio
    task boundaries and keep the legacy TUI handler as a fallback.
    """

    token = _context_input_handler.set(handler)
    try:
        yield
    finally:
        _context_input_handler.reset(token)


async def _read_input(prompt_text: str) -> str:
    """优先走已注册的前端处理器，否则退回终端 input()（API/子进程场景）。"""
    scoped_handler = _context_input_handler.get()
    if scoped_handler is not None:
        return await scoped_handler(prompt_text)
    if _input_handler is not None:
        return await _input_handler(prompt_text)
    return await asyncio.to_thread(input, prompt_text)

description = (
    "Ask the user a question and block until they answer; the answer is returned to the Agent as context. "
    "The user may type '拒绝:<reason>' to refuse; the tool then returns rejected=True and the reason. "
    "Use for: clarifying unclear requirements, confirming a critical action, or information only the user knows. "
    "Do not use for: ending a finished task (use stop), or questions you can look up yourself."
)


class AskUser_input_schema(input_schema):
    question: str = Field(
        description="The specific question to ask the user. Keep it clear and concise, and say what you need them to answer."
    )
    default_answer: Optional[str] = Field(
        default=None,
        description="Default answer. Returned if the user presses Enter without typing anything."
    )
    allow_reject: bool = Field(
        default=True,
        description="Whether the user may refuse. If allowed, they can type '拒绝:<reason>' or 'reject:<reason>'."
    )


class AskUser_output_schema(output_schema):
    is_success: bool = Field(description="Whether a user answer was obtained")
    rejected: bool = Field(default=False, description="Whether the user explicitly refused the request")
    answer: str = Field(default="", description="The user's answer (the default if they skipped; the refusal reason if they refused)")
    reason: str = Field(default="", description="Reason given when the user refused (empty on a normal answer)")
    message: str = Field(default="", description="Status or hint")


class AskUser(Tool):
    tool_id: str = 't-12'
    tool_name: str = 'ask_user'
    tool_description: str = description
    input_schema: Any = AskUser_input_schema
    output_schema: Any = AskUser_output_schema

    def is_read(self) -> bool:
        return True

    async def tool_call(self, user_input: AskUser_input_schema, session: Session) -> AskUser_output_schema:
        question = user_input.question
        default_answer = user_input.default_answer
        allow_reject = user_input.allow_reject

        # 获取当前 Agent 名称，用于提示用户
        agent_name = self.subagent.name if self.subagent else "Agent"

        # 构造提问文本
        prompt_lines = [f"\n{'='*50}"]
        prompt_lines.append(f"【来自 {agent_name} 的提问】")
        prompt_lines.append(f"{question}")
        if default_answer is not None:
            prompt_lines.append(f"[直接回车将使用默认值: {default_answer}]")
        if allow_reject:
            prompt_lines.append("[如需拒绝，请输入 '拒绝:<原因>' 或 'reject:<原因>']")
        prompt_lines.append("="*50)
        prompt_text = "\n".join(prompt_lines)

        try:
            # input() 是同步阻塞调用，使用 asyncio.to_thread 避免阻塞事件循环；
            # TUI 注册处理器后则改由前端收集输入。
            raw_answer = await _read_input(prompt_text + "\n请输入您的回答: ")
            answer = raw_answer.strip()

            # 检测拒绝输入：
            #   - 精确输入 "拒绝" / "reject"
            #   - 或 "拒绝:<原因>" / "reject:<原因>"（支持中英文冒号）
            if allow_reject:
                reason = ""
                is_reject = False
                lowered = answer.lower()
                if lowered in ("拒绝", "reject"):
                    is_reject = True
                else:
                    reject_match = re.match(r'^(?:拒绝|reject)\s*[:：]\s*(.*)$', answer, re.IGNORECASE)
                    if reject_match:
                        is_reject = True
                        reason = reject_match.group(1).strip()

                if is_reject:
                    # 如果没有给出原因，再追问一次
                    if not reason:
                        reason_raw = await _read_input("请说明拒绝原因（可直接回车跳过）: ")
                        reason = reason_raw.strip()
                    return AskUser_output_schema(
                        is_success=False,
                        rejected=True,
                        answer=reason,
                        reason=reason,
                        message="The user rejected the request. " + (f"Reason: {reason}" if reason else "No reason was given.")
                    )

            if not answer and default_answer is not None:
                answer = default_answer
                message = f"No user input; the default was used: {default_answer}"
            else:
                message = "User answer obtained successfully."

            return AskUser_output_schema(
                is_success=True,
                rejected=False,
                answer=answer,
                reason="",
                message=message
            )

        except EOFError:
            # 在非交互式环境（如管道输入）中可能出现
            if default_answer is not None:
                return AskUser_output_schema(
                    is_success=True,
                    rejected=False,
                    answer=default_answer,
                    reason="",
                    message=f"Non-interactive environment detected; the default was used: {default_answer}"
                )
            return AskUser_output_schema(
                is_success=False,
                rejected=False,
                answer="",
                reason="",
                message="Cannot get user input in a non-interactive environment, and no default was provided. "
                        "Retry with default_answer set, or proceed without asking."
            )
        except Exception as e:
            return AskUser_output_schema(
                is_success=False,
                rejected=False,
                answer="",
                reason="",
                message=f"An exception occurred while getting user input: {str(e)}"
            )


def get_class():
    return AskUser
