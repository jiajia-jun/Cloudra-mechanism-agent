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


def _format_content(content: Any, max_len: int = 1000) -> str:
    """把任意 content 转为可读的截断文本。"""
    if content is None:
        return ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                parts.append(str(part))
                continue
            part_type = part.get("type", "text")
            if part_type == "text":
                parts.append(str(part.get("text", "")))
            elif part_type == "image_url":
                image_url = part.get("image_url", {})
                url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
                parts.append(f"[图片: {url}]")
            else:
                parts.append(str(part))
        text = "\n".join(parts)
    elif isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)

    if len(text) > max_len:
        text = text[:max_len] + "...[截断]"
    return text


async def _format_recent_context(agent, limit: int = 5, max_len_per_msg: int = 1000) -> str:
    """格式化当前 Agent 上下文中最近 N 条消息，供 YOLO 判断使用。"""
    if agent.context_manager is None:
        return "<无上下文>"

    try:
        context = await agent.context_manager.load()
    except Exception:
        return "<读取上下文失败>"

    messages = context[-limit:] if len(context) > limit else context
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = _format_content(msg.get("content"), max_len=max_len_per_msg)
        lines.append(f"[{role}] {content}")
    return "\n\n".join(lines)


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
        recent_context = await _format_recent_context(agent)
        args_summary = _format_content(tool_args, max_len=1000)

        prompt = (
            f"{YOLO_SYSTEM_PROMPT}\n\n"
            f"[当前任务]\n{getattr(agent, 'query', '')}\n\n"
            f"[执行者]\n{getattr(agent, 'name', 'Unknown Agent')}\n\n"
            f"[待审批操作]\n"
            f"工具: {tool_name}\n"
            f"参数: {args_summary}\n\n"
            f"[最近 5 条上下文]\n{recent_context}\n\n"
            "请只返回 JSON，格式如下：\n"
            '{"approved": true/false, "reason": "简要说明"}'
        )

        client = self._client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": YOLO_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=500,
        )
        content = response.choices[0].message.content or ""

        # 尝试解析 JSON
        try:
            # 先尝试直接解析；如果 LLM 包在 markdown code block 里，先提取
            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`").strip()
                if raw.lower().startswith("json"):
                    raw = raw[4:].strip()
            result = json.loads(raw)
            approved = bool(result.get("approved", False))
            reason = str(result.get("reason", "")).strip()
            return approved, reason
        except Exception as e:
            # 解析失败视为拒绝，并把原始输出作为原因
            return False, f"YOLO 判断输出无法解析: {content}"
