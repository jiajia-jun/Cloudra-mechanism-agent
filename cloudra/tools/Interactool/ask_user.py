import asyncio
import re
from typing import Any, Optional

from pydantic import Field

from cloudra.session_class import Session
from cloudra.tools_class import Tool, input_schema, output_schema

description = (
    "向用户提出问题并等待回答。当 Agent 需要澄清需求、确认操作或收集额外信息时使用。"
    "调用后会在终端打印问题并阻塞等待用户输入，用户的回答将返回给 Agent 作为上下文。"
    "如果用户想拒绝回答或拒绝执行某项操作，可以输入 '拒绝:<原因>' 或 'reject:<原因>'，"
    "工具会返回 rejected=True 并将原因放入 reason/answer 中。"
)


class AskUser_input_schema(input_schema):
    question: str = Field(
        description="要向用户提出的具体问题。建议清晰、简洁，并说明需要用户回答什么。"
    )
    default_answer: Optional[str] = Field(
        default=None,
        description="默认答案。如果用户直接按回车（不输入内容），则返回此默认值。"
    )
    allow_reject: bool = Field(
        default=True,
        description="是否允许用户拒绝回答。若允许，用户可输入 '拒绝:<原因>' 或 'reject:<原因>'。"
    )


class AskUser_output_schema(output_schema):
    is_success: bool = Field(description="是否成功获取用户回答")
    rejected: bool = Field(default=False, description="用户是否明确拒绝了该请求")
    answer: str = Field(default="", description="用户的回答内容（如果用户未回答且有默认值，则返回默认值；如果用户拒绝，则返回拒绝原因）")
    reason: str = Field(default="", description="用户拒绝时填写的具体原因（正常回答时为空）")
    message: str = Field(default="", description="状态或提示信息")


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
            # input() 是同步阻塞调用，使用 asyncio.to_thread 避免阻塞事件循环
            raw_answer = await asyncio.to_thread(input, prompt_text + "\n请输入您的回答: ")
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
                        reason_raw = await asyncio.to_thread(
                            input, "请说明拒绝原因（可直接回车跳过）: "
                        )
                        reason = reason_raw.strip()
                    return AskUser_output_schema(
                        is_success=False,
                        rejected=True,
                        answer=reason,
                        reason=reason,
                        message="用户拒绝了该请求。" + (f"原因: {reason}" if reason else "未说明原因。")
                    )

            if not answer and default_answer is not None:
                answer = default_answer
                message = f"用户未输入，已使用默认值: {default_answer}"
            else:
                message = "已成功获取用户回答。"

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
                    message=f"检测到非交互式环境，已使用默认值: {default_answer}"
                )
            return AskUser_output_schema(
                is_success=False,
                rejected=False,
                answer="",
                reason="",
                message="非交互式环境无法获取用户输入，且未提供默认值。"
            )
        except Exception as e:
            return AskUser_output_schema(
                is_success=False,
                rejected=False,
                answer="",
                reason="",
                message=f"获取用户输入时发生异常: {str(e)}"
            )


def get_class():
    return AskUser
