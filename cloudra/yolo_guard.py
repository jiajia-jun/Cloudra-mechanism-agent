"""YOLO 模式安全守卫。

当环境变量 ``CLOUDRA_YOLO_MODE=true`` 时，不再通过数据库等待用户审批，
而是调用一个独立的 LLM Agent 自动判断危险操作是否合理。

除进程级环境变量外，也支持按 Session 启用：API 服务在会话任务内通过
``set_session_yolo`` 设置 contextvar，只对当前会话生效，互不影响。
"""

import contextvars
import json
import os
import re
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from cloudra.config import get_config


def _load_prompt(name: str) -> str:
    """从 cloudra/prompts/ 目录加载指定 prompt 文件。"""
    prompts_dir = Path(__file__).parent / "prompts"
    prompt_path = prompts_dir / f"{name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"找不到 prompt 文件: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


YOLO_SYSTEM_PROMPT = _load_prompt("yolo_guard")


# 按 Session 的 YOLO 开关：asyncio task 内设置后只影响该任务及其派生的协程，
# 进程内并发的其他会话不受影响。缺省回落到进程级环境变量（CLI 路径）。
_SESSION_YOLO: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "cloudra_session_yolo", default=False
)


def set_session_yolo(enabled: bool) -> contextvars.Token:
    """为当前异步上下文启用/关闭 Session 级 YOLO，返回可复位的 token。"""
    return _SESSION_YOLO.set(enabled)


def is_yolo_enabled() -> bool:
    """检查当前是否启用了 YOLO 全自动模式（Session 级优先，回落环境变量）。"""
    if _SESSION_YOLO.get():
        return True
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
        cfg = get_config().follower
        self.model = cfg.model
        self.base_url = cfg.url
        self.api_key = cfg.key

    def _client(self) -> AsyncOpenAI:
        if not self.model or not self.base_url or not self.api_key:
            raise RuntimeError(
                "YOLO 模式需要 Follower LLM 配置（model / url / key）。"
                "请运行 `cloudra config init` 进行配置。"
            )
        return AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

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
                "description": "提交针对当前拦截操作的安全审计结论。**尽可能使用该工具进行审批！！**",
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
        request_kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": YOLO_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            # thinking 模型思考段会吃掉输出预算，500 可能截断 tool_call 的 JSON
            max_tokens=2000,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "submit_approval_decision"}}
        )

        # 依次降级尝试，覆盖两类受限端点：
        # 1) 只允许 temperature=1 的 reasoning 模型；
        # 2) 开启 thinking 后拒绝强制 tool_choice 的模型
        #    （去掉 tool_choice 后由下方 content 解析兜底）。
        temp1 = dict(request_kwargs)
        temp1["temperature"] = 1.0
        auto_choice = dict(request_kwargs)
        auto_choice.pop("tool_choice", None)
        temp1_auto = dict(auto_choice)
        temp1_auto["temperature"] = 1.0
        candidate_kwargs = [request_kwargs, temp1, auto_choice, temp1_auto]

        response = None
        last_error: Exception | None = None
        for kwargs in candidate_kwargs:
            try:
                response = await client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                last_error = e
                msg = str(e).lower()
                # 参数类限制：继续尝试下一个降级变体
                if any(k in msg for k in ("temperature", "tool_choice", "thinking")):
                    continue
                # 请求头/限流类拦截：换 UA 重试当前变体
                if any(k in msg for k in ("blocked", "access denied", "forbidden", "too many requests", "rate limit")):
                    print(f"\033[93m[LLM fallback] YOLO 默认请求头被拦截，尝试自定义请求头: {e}\033[0m")
                    client2 = AsyncOpenAI(
                        api_key=self.api_key,
                        base_url=self.base_url,
                        default_headers={"User-Agent": "curl/7.68.0"}
                    )
                    try:
                        response = await client2.chat.completions.create(**kwargs)
                        break
                    except Exception as e2:
                        return False, f"YOLO fallback 网络异常: {e2}"
                return False, f"YOLO 网络异常: {e}"

        if response is None:
            return False, f"YOLO 全部降级重试失败: {last_error}"

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
                    pass

                # 兼容不支持 function calling 的模型返回的 XML 格式
                xml_approved = re.search(
                    r"<parameter\s*=\s*approved\s*>\s*(true|false)\s*</parameter>",
                    content, re.IGNORECASE
                )
                xml_reason = re.search(
                    r"<parameter\s*=\s*reason\s*>(.*?)</parameter>",
                    content, re.DOTALL
                )
                if xml_approved:
                    approved = xml_approved.group(1).lower() == "true"
                    reason = xml_reason.group(1).strip() if xml_reason else ""
                    return approved, reason

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
