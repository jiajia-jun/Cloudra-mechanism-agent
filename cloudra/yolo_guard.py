"""YOLO 模式安全守卫。

当环境变量 ``CLOUDRA_YOLO_MODE=true`` 时，不再通过数据库等待用户审批，
而是调用一个独立的 LLM Agent 自动判断危险操作是否合理。
"""

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI


def _load_prompt(name: str) -> str:
    """从 cloudra/prompts/ 目录加载指定 prompt 文件。"""
    prompts_dir = Path(__file__).parent / "prompts"
    prompt_path = prompts_dir / f"{name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"找不到 prompt 文件: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


YOLO_SYSTEM_PROMPT = _load_prompt("yolo_guard")


def is_yolo_enabled() -> bool:
    """检查当前是否启用了 YOLO 全自动模式。"""
    return os.environ.get("CLOUDRA_YOLO_MODE", "").lower() in ("1", "true", "yes", "on")


def _format_content_multimodal(content: Any, max_len: int = 1000) -> list:
    """把任意 content 转为大模型可识别的多模态对象列表（保留图片结构）。"""
    if content is None:
        return []
    
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                parts.append({"type": "text", "text": str(part)})
                continue
            part_type = part.get("type", "text")
            if part_type == "text":
                text = str(part.get("text", ""))
                if len(text) > max_len:
                    text = text[:max_len] + "...[截断]"
                parts.append({"type": "text", "text": text})
            elif part_type == "image_url":
                # 保留原生图片结构
                parts.append(part)
            else:
                parts.append({"type": "text", "text": str(part)})
        return parts
    elif isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)

    if len(text) > max_len:
        text = text[:max_len] + "...[截断]"
    return [{"type": "text", "text": text}]


def _format_content(content: Any, max_len: int = 1000) -> str:
    """保留旧的纯文本转换，用于提取 args 等。"""
    parts = _format_content_multimodal(content, max_len)
    text_parts = []
    for p in parts:
        if p.get("type") == "text":
            text_parts.append(p.get("text", ""))
        elif p.get("type") == "image_url":
            text_parts.append("[图片]")
    return "\n".join(text_parts)


async def _format_recent_context_multimodal(agent, limit: int = 5, max_len_per_msg: int = 1000) -> list:
    """格式化当前 Agent 上下文中最近 N 条消息，并保留多模态结构供 YOLO 使用。"""
    if agent.context_manager is None:
        return [{"type": "text", "text": "<无上下文>"}]

    try:
        context = await agent.context_manager.load()
    except Exception:
        return [{"type": "text", "text": "<读取上下文失败>"}]

    messages = context[-limit:] if len(context) > limit else context
    final_parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        final_parts.append({"type": "text", "text": f"\n[{role}] "})
        final_parts.extend(_format_content_multimodal(msg.get("content"), max_len=max_len_per_msg))
        
    return final_parts


class YoloGuard:
    """独立的安全判断 Agent。"""

    def __init__(self):
        self.model = os.environ.get("FOLLOWER_MODEL")
        self.base_url = os.environ.get("FOLLOWER_URL")
        self.api_key = os.environ.get("FOLLOWER_KEY")

    def _client(self) -> OpenAI:
        if not self.model or not self.base_url or not self.api_key:
            raise RuntimeError(
                "YOLO 模式需要 FOLLOWER_MODEL / FOLLOWER_URL / FOLLOWER_KEY 环境变量"
            )
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    async def judge(
        self,
        tool_name: str,
        tool_args: dict,
        agent,
        session,
    ) -> tuple[bool, str]:
        """判断当前工具调用是否应该被允许执行。"""
        # 提取多模态上下文
        recent_context_parts = await _format_recent_context_multimodal(agent)
        args_summary = _format_content(tool_args, max_len=1000)

        prefix_text = (
            f"[当前任务]\n{getattr(agent, 'query', '')}\n\n"
            f"[执行者]\n{getattr(agent, 'name', 'Unknown Agent')}\n\n"
            f"[待审批操作]\n"
            f"工具: {tool_name}\n"
            f"参数: {args_summary}\n\n"
            f"[最近 5 条上下文]\n"
        )

        # 组装最终的 user content 数组（支持图文混排）
        user_content = [{"type": "text", "text": prefix_text}]
        user_content.extend(recent_context_parts)

        tools = [{
            "type": "function",
            "function": {
                "name": "submit_approval_decision",
                "description": "提交针对当前拦截操作的安全审计结论。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "approved": {
                            "type": "boolean",
                            "description": "是否允许该操作执行。允许为 true，拒绝为 false。"
                        },
                        "reason": {
                            "type": ["string", "null"],
                            "description": "简要说明允许或拒绝的理由。如无特殊说明可为空或忽略。"
                        }
                    },
                    "required": ["approved"]
                }
            }
        }]

        client = self._client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": YOLO_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=500,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "submit_approval_decision"}}
        )

        try:
            # 强制提取 Tool Call 参数，彻底杜绝大模型啰嗦文本导致的解析错误
            message = response.choices[0].message
            # 某些 provider 不返回 tool_calls 而是返回 content，做兼容处理
            if not message.tool_calls:
                content = message.content or ""
                # 尝试从 content 中解析 JSON
                try:
                    result = json.loads(content)
                    approved = bool(result.get("approved", False))
                    raw_reason = result.get("reason")
                    reason = str(raw_reason).strip() if raw_reason is not None else ""
                    return approved, reason
                except Exception:
                    return False, f"YOLO 未返回 tool_call，且 content 无法解析: {content[:200]}"

            tool_call = message.tool_calls[0]
            result = json.loads(tool_call.function.arguments)
            approved = bool(result.get("approved", False))
            
            # 支持 NoneType 处理
            raw_reason = result.get("reason")
            reason = str(raw_reason).strip() if raw_reason is not None else ""
            
            return approved, reason
        except Exception as e:
            return False, f"YOLO Tool Call 结构提取失败: {e}"
