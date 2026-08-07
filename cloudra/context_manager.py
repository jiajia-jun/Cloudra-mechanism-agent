"""统一的 Agent 上下文管理器。

ContextManager 是 Agent 上下文的唯一真相来源，负责：
1. 从 JSON 文件加载/持久化上下文
2. 提供异步 append/replace 接口
3. 把原始上下文按模型能力渲染成可直接发给 LLM 的消息列表
4. 接收外部事件（邮件、计算任务状态变化等）并注入上下文
5. 事件驱动：外部事件通过 IPC 直接推送，不再轮询数据库
"""

import asyncio
import base64
import inspect
import json
import os
import time
from collections.abc import Awaitable, Callable
from typing import Optional

from cloudra import events, paths
from cloudra.config import get_config
from cloudra.database import ConversationDB, aretry_on_locked, get_database_path
from cloudra.fs_utils import atomic_write_json
from cloudra.llm_client import LLMClient
from cloudra.token_estimator import TokenEstimator

# 本地图片扩展名到 MIME 类型的映射
_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _context_file_path(agent_id: str, conversation_id: str, session_id: Optional[str] = None) -> str:
    """返回指定 agent 在指定 conversation 下的上下文文件路径。

    如果提供 session_id，则把上下文文件放到 conversations/{conv_id}/contexts/sessions/
    目录下，以 {agent_id}_{session_id}.json 命名，确保同一 conversation 内的不同子任务
    拥有独立的上下文文件，避免任务间相互污染。
    """
    base = paths.contexts_dir(conversation_id)
    if session_id:
        base = base / 'sessions'
    os.makedirs(base, exist_ok=True)
    return str(paths.context_path(conversation_id, agent_id, session_id))


def _db_path(conversation_id: Optional[str] = None) -> str:
    """返回指定 conversation 的任务数据库路径。"""
    return get_database_path(conversation_id)


# Supervisor 建议消息在上下文中的标记，用于定位更新
SUPERVISOR_ADVICE_MARKER = "[Supervisor]"

# 压缩梗概消息的内容前缀：持久化压缩与手动 compact 共用，
# 用于在下一轮压缩时识别旧梗概并折叠进新梗概（避免梗概无限累积）。
COMPACT_SUMMARY_MARKER = "[上下文压缩提示]"

# Auto-compaction keeps a small completed-turn tail. Ten assistant turns can
# itself occupy most of a 64k half-window in tool-heavy sessions, leaving the
# compressor above budget immediately after it runs.
AUTO_COMPACT_KEEP_ASSISTANT = 4

# Parallelize independent map chunks, but keep the fan-out conservative so one
# long conversation cannot monopolize the FOLLOWER endpoint.
COMPACTION_CONCURRENCY = 3

CompactionProgress = Callable[[dict], Awaitable[None] | None]


class ContextManager:
    """管理单个 Agent 的上下文生命周期与外部事件注入。"""

    def __init__(
        self,
        agent_id: str,
        conversation_id: str,
        prompt: Optional[str],
        query: str,
        db_path: Optional[str] = None,
        session_id: Optional[str] = None,
        on_compaction_progress: Optional[CompactionProgress] = None,
    ):
        self.agent_id = agent_id
        self.conversation_id = conversation_id or 'default'
        # 仅作为直接使用 ContextManager 时的动态身份层兼容入口；不会持久化。
        self.prompt = prompt
        self.query = query
        self.session_id = session_id
        self.context_file = _context_file_path(agent_id, self.conversation_id, session_id)
        self.db_path = db_path or _db_path(self.conversation_id)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # 上下文实例缓存：本实例是 context_file 生命周期内的唯一写者，
        # 首次 load 后驻留内存，避免每条消息都全量读盘 + json 解析。
        self._context_cache: Optional[list] = None
        # 压缩用的 LLM 传输层客户端缓存，避免每次压缩都新建连接池。
        self._llm_client: Optional[LLMClient] = None
        self._on_compaction_progress = on_compaction_progress

    async def _report_compaction(self, **payload) -> None:
        """Best-effort progress callback; telemetry must never break compact."""
        callback = self._on_compaction_progress
        if callback is None:
            return
        try:
            result = callback(payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            pass

    def _initial_context(self) -> list:
        """构造可持久化历史；身份 system prompt 由请求期 assembler 提供。

        query 为空时（状态展示等只读用途构造的 ContextManager）不能落一条
        空 user 消息——它会留在历史里，导致后续 LLM 请求被严格端点以
        "user message must not be empty" 拒绝（400）。
        """
        if not self.query:
            return []
        return [{"role": "user", "content": self.query}]

    @staticmethod
    def _is_legacy_identity_message(context: list) -> bool:
        """识别旧格式首条 identity system message。"""
        if len(context) < 2:
            return False
        first, second = context[0], context[1]
        if first.get("role") != "system" or second.get("role") != "user":
            return False
        content = first.get("content", "")
        if not isinstance(content, str):
            return False
        return not (
            content.startswith(SUPERVISOR_ADVICE_MARKER)
            or content.startswith("[上下文压缩提示]")
        )

    async def _migrate_legacy_identity(self, context: list) -> list:
        if not self._is_legacy_identity_message(context):
            return context
        migrated = context[1:]
        await self.replace(migrated)
        return migrated

    async def load(self) -> list:
        """加载上下文；若文件不存在则初始化并保存。

        首次读取后驻留实例缓存（本实例是该文件的唯一写者），
        后续 load 不再触碰磁盘。

        解析失败时只读返回空、绝不回写磁盘：TUI 状态栏等只读实例以
        query="" 构造，若在解析失败分支里执行 replace(_initial_context())，
        会把 [] 覆盖回上下文文件，一次性冲掉整段对话历史（历史故障根因，
        见 _drop_empty_user_messages 的回归说明）。
        """
        if self._context_cache is not None:
            return self._context_cache
        if os.path.isfile(self.context_file):
            try:
                def read_context() -> list:
                    with open(self.context_file, 'r', encoding='utf-8') as f:
                        return json.load(f)

                self._context_cache = await asyncio.to_thread(read_context)
                return await self._migrate_legacy_identity(self._context_cache)
            except json.JSONDecodeError as e:
                # 文件损坏或与并发写入竞争读到半截：只读返回空并告警，
                # 恢复由调用方通过正常 append 路径完成，禁止直接回写。
                print(
                    f"[ContextManager] 上下文文件解析失败（只读返回空，不回写）: "
                    f"{self.context_file}, 错误: {e}"
                )
                self._context_cache = []
                return self._context_cache

        self._context_cache = self._initial_context()
        await self.replace(self._context_cache)
        return self._context_cache

    async def replace(self, context: list) -> None:
        """全量替换上下文并持久化到文件（同时刷新实例缓存）。

        写入采用临时文件 + 原子改名（``os.replace``），保证外部只读进程
        （TUI 状态栏、ContextScreen 等）并发读取时永远读到完整内容，
        不会因看到写入中的半截文件而解析失败。
        """
        self._context_cache = context

        def write_context() -> None:
            atomic_write_json(self.context_file, context, indent=4)

        await asyncio.to_thread(write_context)

    async def append(self, new_block: dict) -> None:
        """追加一条消息到上下文，并持久化。"""
        if 'role' not in new_block:
            new_block['role'] = 'user'

        # 提取 image_path（如果存在），构建 OpenAI 标准 image_url 结构
        image_path = new_block.pop('image_path', None)
        if image_path:
            text_content = new_block.get('content', "查看此图片内容：")
            new_block['content'] = [
                {"type": "text", "text": text_content if text_content else "查看此图片内容："},
                {"type": "image_url", "image_url": {"url": image_path}},
            ]
        elif 'content' not in new_block:
            new_block['content'] = str(new_block)

        context = await self.load()
        context.append(new_block)
        await self.replace(context)

    async def set_supervisor_advice(self, advice_text: str) -> None:
        """设置/更新 Supervisor 建议。

        Supervisor 建议位于初始 query 之后、事件层/对话历史之前。
        如果已存在 Supervisor 建议，则替换；否则紧跟初始 query 插入。
        """
        context = await self.load()
        # 包装时附上引导语：提醒模型在后续决策中优先参考 Supervisor 的意见
        advice_msg = {
            "role": "system",
            "content": (
                f"{SUPERVISOR_ADVICE_MARKER}\n{advice_text}\n"
                "【注意】以上是 Supervisor 对本阶段方向的审查意见，"
                "请在后续推理、任务拆解与工具选择中优先参考并据此调整。"
            ),
        }

        # 查找现有的 Supervisor 建议消息
        existing_idx = None
        for i, msg in enumerate(context):
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if isinstance(content, str) and content.startswith(SUPERVISOR_ADVICE_MARKER):
                    existing_idx = i
                    break

        if existing_idx is not None:
            context[existing_idx] = advice_msg
        else:
            # 身份 prompt 不持久化；初始 query 通常位于索引 0。
            insert_idx = 1 if context and context[0].get("role") == "user" else 0
            context.insert(insert_idx, advice_msg)

        await self.replace(context)

    async def clear_supervisor_advice(self) -> None:
        """清除当前上下文中的 Supervisor 建议。"""
        context = await self.load()
        context = [
            msg for msg in context
            if not (
                msg.get("role") == "system"
                and isinstance(msg.get("content", ""), str)
                and msg.get("content", "").startswith(SUPERVISOR_ADVICE_MARKER)
            )
        ]
        await self.replace(context)

    def _is_supervisor_advice(self, msg: dict) -> bool:
        """判断一条消息是否是 Supervisor 建议。"""
        if msg.get("role") != "system":
            return False
        content = msg.get("content", "")
        if isinstance(content, str):
            return content.startswith(SUPERVISOR_ADVICE_MARKER)
        if isinstance(content, list):
            text = "\n".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )
            return text.startswith(SUPERVISOR_ADVICE_MARKER)
        return False

    async def build_messages(
        self,
        supports_vision: bool = False,
        vision_history_limit: int = 10,
        max_context_tokens: Optional[int] = None,
        identity_messages: Optional[list[dict]] = None,
        _persistent_compress_attempted: bool = False,
    ) -> list[dict]:
        """把原始上下文渲染成可直接发送给 LLM 的消息列表。

        原始上下文中图片以本地路径形式保存；此方法会根据模型是否支持视觉，
        将图片部分渲染为 OpenAI 标准的 image_url（base64 data URL）或降级为纯文本。

        为了控制上下文体积：
        1. 只有最近 ``vision_history_limit`` 轮用户消息中的图片会被保留为多模态
           内容；更早的图片会被降级为文本占位符（保留路径/描述）。
        2. 如果渲染后的总 token 数超过 ``max_context_tokens``，先做一次持久化压缩
           （历史梗概写回上下文存储，后续轮次不再重复摘要整段历史）；
           仍超预算时再退回 render-time 压缩（仅作用于当次请求的副本）。
           system prompt 和最近 10 轮对话始终被保留。
        """
        history = await self.load()
        if identity_messages is None:
            identity_messages = (
                [{"role": "system", "content": self.prompt}]
                if self.prompt is not None
                else []
            )
        raw_context = [dict(message) for message in identity_messages] + list(history)

        # 计算需要保留多模态图片的消息索引：最近 N 条 user 消息
        user_indices = [
            i for i, msg in enumerate(raw_context) if msg.get("role") == "user"
        ]
        retained_indices = (
            set(user_indices[-vision_history_limit:])
            if vision_history_limit > 0
            else set()
        )

        rendered = [
            self._render_message(
                msg,
                supports_vision=supports_vision,
                force_text_image=(i not in retained_indices),
            )
            for i, msg in enumerate(raw_context)
        ]

        rendered = self._drop_empty_assistant_messages(rendered)
        rendered = self._drop_empty_user_messages(rendered)
        rendered = self._repair_dangling_tool_calls(rendered)
        # Very large tool results make capping and token estimation measurable
        # CPU work.  They must not run on the TUI/Agent event-loop thread.
        rendered = await asyncio.to_thread(self._cap_message_sizes, rendered)

        if max_context_tokens is None:
            return rendered

        rendered_tokens = await asyncio.to_thread(
            TokenEstimator.estimate_messages,
            rendered,
        )
        if (
            rendered_tokens > max_context_tokens
            and not _persistent_compress_attempted
            and await self._compress_persistent()
        ):
            # 持久化压缩生效后从存储重渲染；标记避免同一次请求重复压缩
            return await self.build_messages(
                supports_vision=supports_vision,
                vision_history_limit=vision_history_limit,
                max_context_tokens=max_context_tokens,
                identity_messages=identity_messages,
                _persistent_compress_attempted=True,
            )

        return await self._compress_to_budget(
            rendered,
            max_context_tokens=max_context_tokens,
        )

    @staticmethod
    def _encode_image(path: str) -> str:
        """将本地图片文件编码为 Base64 字符串。"""
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _render_image_part(
        self,
        path: str,
        supports_vision: bool,
        force_text: bool = False,
    ) -> dict | list[dict]:
        """根据模型视觉能力，把图片路径渲染为 image_url 或降级文本。

        如果传入的 path 已经是 data URL，则直接透传，不做二次编码。
        当 ``force_text=True`` 时，即使模型支持视觉也会把图片降级为文本占位符，
        用于避免过早历史消息中的图片持续占用上下文 Token。
        """
        if force_text or not supports_vision:
            text = f"[图片: {path}]" if force_text else f"[图片: {path} (当前模型不支持视觉或多模态信息已过于久远)]"
            return {"type": "text", "text": text}

        if path.startswith("data:"):
            return {"type": "image_url", "image_url": {"url": path}}

        if not os.path.exists(path):
            return {"type": "text", "text": f"[图片缺失: {path}]"}

        ext = os.path.splitext(path)[1].lower()
        mime = _IMAGE_MIME_TYPES.get(ext)
        if mime is None:
            return {"type": "text", "text": f"[不支持的图片格式: {path}]"}

        try:
            base64_image = self._encode_image(path)
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{base64_image}"},
            }
        except Exception:
            return {"type": "text", "text": f"[图片加载失败: {path}]"}

    @staticmethod
    def _content_to_text(content) -> str:
        """把任意 content 安全地转成纯文本字符串。"""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(part.get("text", part)) if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)

    def _render_message(
        self,
        msg: dict,
        supports_vision: bool,
        force_text_image: bool = False,
    ) -> dict:
        """渲染单条消息：校验 role、处理 content 中的图片、整理字段。"""
        rendered = dict(msg)
        rendered.setdefault("role", "user")

        content = rendered.get("content")

        # 处理 content 为列表的情况（可能包含图片路径）
        if isinstance(content, list):
            new_parts = []
            for part in content:
                if not isinstance(part, dict):
                    new_parts.append({"type": "text", "text": str(part)})
                    continue

                if part.get("type") == "image_url":
                    image_url = part.get("image_url", {})
                    path = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
                    rendered_part = self._render_image_part(
                        path, supports_vision, force_text=force_text_image
                    )
                    # _render_image_part 在 vision 模式下返回单个 part，降级模式下返回文本 part
                    if isinstance(rendered_part, list):
                        new_parts.extend(rendered_part)
                    else:
                        new_parts.append(rendered_part)
                else:
                    new_parts.append(part)

            rendered["content"] = new_parts if supports_vision else "\n".join(
                p.get("text", "") for p in new_parts
            )
        elif not supports_vision and isinstance(content, dict):
            # 理论上不会出现，但做防御性处理
            rendered["content"] = self._content_to_text(content)

        # 清理内部字段
        rendered.pop("image_paths", None)

        # reasoning_content 仅做类型规范化
        if "reasoning_content" in rendered:
            rendered["reasoning_content"] = str(rendered["reasoning_content"]) if rendered["reasoning_content"] else None

        return rendered

    @staticmethod
    def _drop_empty_assistant_messages(messages: list[dict]) -> list[dict]:
        """过滤掉 assistant 角色的空消息。

        部分模型/接口要求 assistant 消息至少提供 content、reasoning_content
        或 tool_calls 之一。如果某条 assistant 消息三者皆空，直接丢弃会避免
        后续 LLM 调用返回 400 (Param Incorrect)。
        """
        cleaned = []
        for msg in messages:
            if msg.get("role") != "assistant":
                cleaned.append(msg)
                continue

            has_content = bool(msg.get("content"))
            has_reasoning = bool(msg.get("reasoning_content"))
            has_tool_calls = bool(msg.get("tool_calls"))

            if has_content or has_reasoning or has_tool_calls:
                cleaned.append(msg)
            # else: 空 assistant 消息直接丢弃

        return cleaned

    @staticmethod
    def _drop_empty_user_messages(messages: list[dict]) -> list[dict]:
        """过滤掉 user 角色的空消息。

        严格端点（如 kimi-for-coding）会以 400 拒绝 content 为空的 user 消息
        ("must not be empty")。空 user 消息没有语义价值——历史上曾由只读
        ContextManager（query=""）意外持久化——直接在请求期丢弃。
        带图片等多模态部分的 user 消息视为非空。
        """
        cleaned = []
        for msg in messages:
            if msg.get("role") != "user":
                cleaned.append(msg)
                continue
            content = msg.get("content")
            if content is None:
                continue
            if isinstance(content, str):
                if content.strip():
                    cleaned.append(msg)
                continue
            if isinstance(content, list):
                has_parts = any(
                    (isinstance(part, dict) and part.get("type") == "image_url")
                    or (isinstance(part, dict) and str(part.get("text", "")).strip())
                    for part in content
                )
                if has_parts:
                    cleaned.append(msg)
                continue
            cleaned.append(msg)

        return cleaned

    @staticmethod
    def _repair_dangling_tool_calls(messages: list[dict]) -> list[dict]:
        """修补悬挂的 tool_calls。

        OpenAI 协议要求：带 tool_calls 的 assistant 消息，其后必须紧跟与每个
        tool_call_id 对应的 tool 响应，否则端点会拒绝整个请求（400）。
        Session 在"assistant 发起调用"与"结果写回上下文"之间被打断/取消时，
        上下文会留下没有响应的 tool_calls，导致该对话后续所有请求都 400。
        这里为缺失响应的 tool_call 补一条说明性的 tool 消息（幂等：已被响应
        覆盖的 id 不会重复补）。
        """
        answered = {
            msg.get("tool_call_id")
            for msg in messages
            if msg.get("role") == "tool" and msg.get("tool_call_id")
        }
        repaired = []
        for msg in messages:
            repaired.append(msg)
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls") or []
            for call in tool_calls:
                call_id = call.get("id") if isinstance(call, dict) else None
                if call_id and call_id not in answered:
                    repaired.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": "【系统提示】该工具调用在执行完成前被打断/取消，没有返回结果。",
                    })
                    answered.add(call_id)
        return repaired

    # 单条消息内容的硬顶（字符数）：一条巨型工具结果（如整份 PDF 的乱码文本）
    # 就能撑爆模型上下文，而历史梗概压缩对单条超大消息无解。
    MAX_MESSAGE_CHARS = 40_000

    @classmethod
    def _cap_message_sizes(cls, messages: list[dict]) -> list[dict]:
        """给单条消息的内容加硬顶，超出部分截断并注明原始长度。

        历史压缩（_compress_to_budget）的兜底是"梗概仍超预算就保留原文"，
        所以一条数百万 token 的巨型消息（典型：PDF 二进制当文本塞进工具结果）
        会直接越过压缩机制把请求打到 400。这里在渲染期对每条消息截断，
        system 消息（身份 prompt、梗概）保持不变。
        """
        capped = []
        for msg in messages:
            if msg.get("role") == "system":
                capped.append(msg)
                continue
            content = msg.get("content")
            if isinstance(content, str) and len(content) > cls.MAX_MESSAGE_CHARS:
                msg = dict(msg)
                msg["content"] = (
                    content[: cls.MAX_MESSAGE_CHARS]
                    + f"\n\n[... 内容过长已截断，原始共 {len(content)} 字符 ..."
                )
            elif isinstance(content, list):
                new_parts = []
                for part in content:
                    if (
                        isinstance(part, dict)
                        and part.get("type") == "text"
                        and isinstance(part.get("text"), str)
                        and len(part["text"]) > cls.MAX_MESSAGE_CHARS
                    ):
                        part = dict(part)
                        part["text"] = (
                            part["text"][: cls.MAX_MESSAGE_CHARS]
                            + f"\n\n[... 内容过长已截断，原始共 {len(part['text'])} 字符 ..."
                        )
                    new_parts.append(part)
                if new_parts != content:
                    msg = dict(msg)
                    msg["content"] = new_parts
            capped.append(msg)
        return capped

    async def _summarize_history(self, history: list[dict]) -> str:
        """Summarize history, using hierarchical chunks when history is oversized."""
        cfg = get_config().follower
        model = cfg.model
        base_url = cfg.url
        api_key = cfg.key

        if not model or not base_url or not api_key:
            raise RuntimeError(
                "缺少 FOLLOWER 配置（model / url / key），"
                "无法生成历史消息梗概。请运行 `cloudra config init` 进行配置。"
            )

        input_limit = max(8_000, min(64_000, int(cfg.context_window or 128_000) // 2))

        def partition(items: list[str]) -> list[list[str]]:
            expanded: list[str] = []
            for item in items:
                if TokenEstimator.estimate_text(item) <= input_limit:
                    expanded.append(item)
                    continue
                # A single CJK-heavy message can exceed the token budget even
                # after the general 40k-character cap. Splitting at at most
                # input_limit characters is conservative for all estimator
                # character classes and keeps each summary request valid.
                expanded.extend(
                    item[offset : offset + input_limit]
                    for offset in range(0, len(item), input_limit)
                )
            chunks: list[list[str]] = []
            current: list[str] = []
            current_tokens = 0
            for item in expanded:
                item_tokens = TokenEstimator.estimate_text(item) + 2
                if current and current_tokens + item_tokens > input_limit:
                    chunks.append(current)
                    current = []
                    current_tokens = 0
                current.append(item)
                current_tokens += item_tokens
            if current:
                chunks.append(current)
            return chunks

        def prepare_chunks() -> list[list[str]]:
            # Apply the same per-message safety cap even for manual compact
            # callers, then turn messages into summary input.  Both operations
            # may scan hundreds of thousands of characters.
            capped_history = self._cap_message_sizes(
                [dict(msg) for msg in history]
            )
            lines: list[str] = []
            for msg in capped_history:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = [
                        str(part.get("text", ""))
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    content = "\n".join(text_parts)
                lines.append(f"[{role}] {content}")
            return partition(lines)

        async def summarize_text(history_text: str) -> str:
            prompt = (
                "请将以下对话历史压缩成一段简洁的梗概，保留关键信息（如任务目标、"
                "已完成的子任务、重要结论、文件路径、失败原因等），丢弃细节和重复内容。"
                "梗概将用于替代原始历史消息发送给后续模型，因此必须让后续模型理解当前状态。"
                "\n\n--- 历史对话 ---\n\n"
                f"{history_text}\n\n"
                "--- 梗概 ---"
            )

            if self._llm_client is None:
                self._llm_client = LLMClient(api_key=api_key, base_url=base_url)
            response = await self._llm_client.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个专门压缩对话历史的助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=1.0,
            )
            summary = response.choices[0].message.content
            return summary.strip() if summary else "[历史消息过长，未能生成有效梗概]"

        limiter = asyncio.Semaphore(COMPACTION_CONCURRENCY)

        async def summarize_layer(
            chunks: list[list[str]],
            *,
            level: int,
        ) -> list[str]:
            total = len(chunks)
            completed = 0
            await self._report_compaction(
                stage="started" if level == 1 else "reducing",
                level=level,
                completed=0,
                total=total,
            )

            async def run_chunk(chunk: list[str]) -> str:
                nonlocal completed
                async with limiter:
                    result = await summarize_text("\n\n".join(chunk))
                completed += 1
                await self._report_compaction(
                    stage="progress",
                    level=level,
                    completed=completed,
                    total=total,
                )
                return result

            tasks = [asyncio.create_task(run_chunk(chunk)) for chunk in chunks]
            try:
                # gather preserves chunk order even though requests complete out
                # of order, so the reduction prompt remains deterministic.
                return await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

        try:
            chunks = await asyncio.to_thread(prepare_chunks)
            summaries = await summarize_layer(chunks, level=1)
            # Map-reduce: levels depend on the previous level, while chunks in
            # one level are independent and safely run with bounded concurrency.
            level = 1
            while len(summaries) > 1:
                level += 1
                reduction_lines = [
                    f"[分段梗概 {index + 1}] {summary}"
                    for index, summary in enumerate(summaries)
                ]
                reduction_chunks = await asyncio.to_thread(
                    partition,
                    reduction_lines,
                )
                summaries = await summarize_layer(reduction_chunks, level=level)
            await self._report_compaction(
                stage="completed",
                level=level,
                completed=1,
                total=1,
            )
            return summaries[0] if summaries else "[没有可压缩的历史消息]"
        except BaseException as exc:
            await self._report_compaction(
                stage="failed",
                error=str(exc),
            )
            raise

    async def _compress_persistent(self) -> bool:
        """超预算时先做持久化压缩：把历史梗概一次性写回上下文存储。

        旧的 render-time 压缩（_compress_to_budget）只作用于当次请求的消息副本，
        导致超预算期间每一轮推理都要对整段历史重新做一次 LLM 摘要——每轮摘要
        内容都不同（KV cache 全灭），延迟与花费随任务长度线性恶化。这里把梗概
        写回存储，后续轮次从压缩后的上下文出发，只有再次长到超预算时才触发
        下一次摘要（天然增量）；旧的梗概会被折叠进新梗概，不会无限累积。

        返回是否发生了持久化压缩（无可压缩历史或梗概生成失败时为 False，
        调用方退回 render-time 压缩兜底）。
        """
        context = await self.load()

        # 可压缩内容 = 非 system 消息 + 旧的压缩梗概（折叠进新梗概）；
        # 其余 system 消息（Supervisor 建议等）原样保留在前面。
        pinned_system: list[dict] = []
        compressible: list[dict] = []
        for msg in context:
            content = msg.get("content", "")
            is_summary = (
                msg.get("role") == "system"
                and isinstance(content, str)
                and content.startswith(COMPACT_SUMMARY_MARKER)
            )
            if msg.get("role") == "system" and not is_summary:
                pinned_system.append(msg)
            else:
                compressible.append(msg)

        # 自动压缩只保护最近几个 assistant 回合。完整上下文仍在压缩前持久化，
        # 梗概保留旧任务状态；较小的尾窗避免工具密集型会话压完仍超过半窗。
        tail_count = 0
        assistant_seen = 0
        for msg in reversed(compressible):
            tail_count += 1
            if msg.get("role") == "assistant":
                assistant_seen += 1
            if assistant_seen >= AUTO_COMPACT_KEEP_ASSISTANT:
                break

        tail = compressible[-tail_count:] if tail_count else []
        history = compressible[:-tail_count] if tail_count else compressible
        if not history:
            return False

        try:
            # Rendering already refuses to send an unbounded individual tool
            # result to the main model. Apply the same cap before asking the
            # summary model, otherwise an oversized raw result can make compact
            # fail forever precisely when it is most needed.
            summary = await self._summarize_history(history)
        except Exception as e:
            print(
                f"\033[93m[ContextManager]\033[0m 持久化压缩的梗概生成失败，"
                f"退回 render-time 压缩: {e}"
            )
            return False

        summary_msg = {
            "role": "system",
            "content": (
                f"{COMPACT_SUMMARY_MARKER} 以下是由历史对话生成的梗概，"
                "保留了关键任务状态、结论和文件路径：\n\n"
                f"{summary}"
            ),
        }
        await self.replace(pinned_system + [summary_msg] + tail)
        return True

    async def _compress_to_budget(
        self,
        messages: list[dict],
        max_context_tokens: int,
    ) -> list[dict]:
        """在不超过 token 预算的前提下压缩消息列表。

        重要约定：
        - 仅压缩“历史消息”（最近 10 条 assistant 消息之前的内容）。
        - 最近 10 轮对话原封不动保留，避免丢失刚发生的关键信息。
        - 历史消息不会直接删除，而是通过 FOLLOWER 配置的大模型生成梗概后替换。
        - 如果梗概生成失败，保留原始历史消息不压缩（宁可多花 token 也不丢失信息）。
        """
        if not messages:
            return messages

        total = await asyncio.to_thread(
            TokenEstimator.estimate_messages,
            messages,
        )
        if total <= max_context_tokens:
            return messages

        # 分离 system 消息
        system_messages = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # 最近 10 轮：从后往前数，遇到 10 条 assistant 为止。
        # 以 assistant 而非 user 计数，是因为一次用户请求可能产生多条 assistant
        # 回复（例如工具调用后的多次响应），assistant 更能代表“一轮完成”。
        tail_count = 0
        assistant_seen = 0
        for msg in reversed(non_system):
            tail_count += 1
            if msg.get("role") == "assistant":
                assistant_seen += 1
            if assistant_seen >= 10:
                break

        tail = non_system[-tail_count:] if tail_count else []
        history = non_system[:-tail_count] if tail_count else non_system

        if not history:
            # 没有可压缩的历史，直接返回原消息
            return messages

        # 调用 LLM 生成历史梗概
        try:
            summary = await self._summarize_history(history)
        except Exception as e:
            print(
                f"\033[93m[ContextManager]\033[0m 历史消息梗概生成失败，"
                f"保留原始历史消息不压缩: {e}"
            )
            return messages

        summary_msg = {
            "role": "system",
            "content": (
                f"{COMPACT_SUMMARY_MARKER} 以下是由历史对话生成的梗概，"
                "保留了关键任务状态、结论和文件路径：\n\n"
                f"{summary}"
            ),
        }
        candidate = system_messages + [summary_msg] + tail

        candidate_tokens = await asyncio.to_thread(
            TokenEstimator.estimate_messages,
            candidate,
        )
        if candidate_tokens <= max_context_tokens:
            return candidate

        # 如果梗概仍然超长，返回原始消息（不进一步删除或兜底）
        print(
            f"\033[93m[ContextManager]\033[0m 警告：生成的历史梗概仍超过 "
            f"{max_context_tokens} token 预算，本次请求保留完整上下文。"
        )
        return messages

    async def compact(self, keep_recent: int = 4) -> dict:
        """手动压缩持久化上下文。

        保留最近 ``keep_recent`` 条消息原样不变，将其余历史通过 FOLLOWER 配置的
        大模型生成一段梗概，并以 system 消息形式替换到上下文开头。压缩后的上下文
        会在后续 ``build_messages`` 时正常参与渲染。

        Args:
            keep_recent: 保留的最近消息条数，必须 >= 1，默认 4。

        Returns:
            统计字典，包含 ``original_count``、``new_count``、
            ``summary_length``、``compressed``、可选 ``reason``。
        """
        if keep_recent < 1:
            raise ValueError("keep_recent 必须 >= 1")

        context = await self.load()
        original_count = len(context)

        if original_count <= keep_recent:
            return {
                "original_count": original_count,
                "new_count": original_count,
                "summary_length": 0,
                "compressed": False,
                "reason": f"上下文仅 {original_count} 条消息，未超过保留窗口 {keep_recent} 条",
            }

        history = context[:-keep_recent]
        tail = context[-keep_recent:]

        summary = await self._summarize_history(history)

        summary_msg = {
            "role": "system",
            "content": (
                f"{COMPACT_SUMMARY_MARKER} 以下是由历史对话生成的梗概，"
                "保留了关键任务状态、结论和文件路径：\n\n"
                f"{summary}"
            ),
        }
        new_context = [summary_msg] + list(tail)
        await self.replace(new_context)

        return {
            "original_count": original_count,
            "new_count": len(new_context),
            "summary_length": len(summary),
            "compressed": True,
        }

    async def clear(self) -> None:
        """清空上下文文件（用于任务结束后释放上下文）。"""
        await self.replace([])

    # ------------------------------------------------------------------
    # 外部事件接口
    # ------------------------------------------------------------------

    @staticmethod
    async def inject_event(
        conversation_id: str,
        agent_id: str,
        event_type: str,
        content: str,
        db_path: Optional[str] = None,
    ) -> None:
        """外部生产者调用，将事件写入 context_events 表。

        该方法是静态方法，因为生产者通常不持有目标 Agent 的 ContextManager 实例。
        """
        path = db_path or _db_path(conversation_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        db = ConversationDB.from_path(path)

        async def insert_event() -> None:
            async with db.aconnect() as con:
                await con.execute(
                    """
                    INSERT INTO context_events (conversation_id, agent_id, event_type, content, state, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (conversation_id, agent_id, event_type, content, 'pending', time.time())
                )
                await con.commit()

        await aretry_on_locked(insert_event)
        await events.aemit(
            conversation_id,
            "external_event",
            agent_id=agent_id,
            event_type=event_type,
            content=content,
        )


    async def drain_pending_events(self) -> list[dict]:
        """读取并消费属于本 agent 的 pending 外部事件（用于离线恢复或启动补拉）。"""
        db = ConversationDB.from_path(self.db_path)

        async def poll() -> list[dict]:
            found = []
            async with db.aconnect() as con:
                cur = await con.execute(
                    """
                    SELECT id, event_type, content FROM context_events
                    WHERE conversation_id = ? AND agent_id = ? AND state = 'pending'
                    ORDER BY created_at ASC
                    """,
                    (self.conversation_id, self.agent_id),
                )
                rows = await cur.fetchall()
                if rows:
                    event_ids = [r[0] for r in rows]
                    await con.execute(
                        "UPDATE context_events SET state = 'delivered' WHERE id IN ({})".format(
                            ",".join("?" * len(event_ids))
                        ),
                        event_ids,
                    )
                    await con.commit()
                    found = [
                        {"id": r[0], "event_type": r[1], "content": r[2]}
                        for r in rows
                    ]
            return found

        return await aretry_on_locked(poll)

    # 兼容性别名：旧测试与外部调用仍使用 poll_external_events
    poll_external_events = drain_pending_events

    async def has_pending_events(self) -> bool:
        """检查是否有待处理的外部事件。"""
        db = ConversationDB.from_path(self.db_path)

        async def count_pending() -> bool:
            async with db.aconnect() as con:
                cur = await con.execute(
                    """
                    SELECT COUNT(*) FROM context_events
                    WHERE conversation_id = ? AND agent_id = ? AND state = 'pending'
                    """,
                    (self.conversation_id, self.agent_id),
                )
                row = await cur.fetchone()
                return row[0] > 0 if row else False

        return await aretry_on_locked(count_pending)
