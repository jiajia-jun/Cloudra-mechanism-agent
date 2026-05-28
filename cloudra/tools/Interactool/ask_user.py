import asyncio
from pydantic import Field
from typing import Any, Optional
from cloudra.tools_class import Tool, input_schema, output_schema
from cloudra.session_class import Session


description = (
    "向用户提出问题并等待回答。当 Agent 需要澄清需求、确认操作或收集额外信息时使用。"
    "调用后会在终端打印问题并阻塞等待用户输入，用户的回答将返回给 Agent 作为上下文。"
)


class AskUser_input_schema(input_schema):
    question: str = Field(
        description="要向用户提出的具体问题。建议清晰、简洁，并说明需要用户回答什么。"
    )
    default_answer: Optional[str] = Field(
        default=None,
        description="默认答案。如果用户直接按回车（不输入内容），则返回此默认值。"
    )


class AskUser_output_schema(output_schema):
    is_success: bool = Field(description="是否成功获取用户回答")
    answer: str = Field(default="", description="用户的回答内容（如果用户未回答且有默认值，则返回默认值）")
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

        # 获取当前 Agent 名称，用于提示用户
        agent_name = self.subagent.name if self.subagent else "Agent"

        # 构造提问文本
        prompt_lines = [f"\n{'='*50}"]
        prompt_lines.append(f"【来自 {agent_name} 的提问】")
        prompt_lines.append(f"{question}")
        if default_answer is not None:
            prompt_lines.append(f"[直接回车将使用默认值: {default_answer}]")
        prompt_lines.append("="*50)
        prompt_text = "\n".join(prompt_lines)

        try:
            # input() 是同步阻塞调用，使用 asyncio.to_thread 避免阻塞事件循环
            raw_answer = await asyncio.to_thread(input, prompt_text + "\n请输入您的回答: ")
            answer = raw_answer.strip()

            if not answer and default_answer is not None:
                answer = default_answer
                message = f"用户未输入，已使用默认值: {default_answer}"
            else:
                message = "已成功获取用户回答。"

            return AskUser_output_schema(
                is_success=True,
                answer=answer,
                message=message
            )

        except EOFError:
            # 在非交互式环境（如管道输入）中可能出现
            if default_answer is not None:
                return AskUser_output_schema(
                    is_success=True,
                    answer=default_answer,
                    message=f"检测到非交互式环境，已使用默认值: {default_answer}"
                )
            return AskUser_output_schema(
                is_success=False,
                answer="",
                message="非交互式环境无法获取用户输入，且未提供默认值。"
            )
        except Exception as e:
            return AskUser_output_schema(
                is_success=False,
                answer="",
                message=f"获取用户输入时发生异常: {str(e)}"
            )


def get_class():
    return AskUser
