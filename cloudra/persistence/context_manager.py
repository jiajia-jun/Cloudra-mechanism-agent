"""统一的 Agent 上下文管理器。

ContextManager 是 Agent 上下文的唯一真相来源，负责：
1. 从上下文文件加载/持久化上下文（JSONL 追加式；兼容旧的单 JSON 数组格式）
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

from cloudra.infra import events
from cloudra.infra.config import get_config
from cloudra.infra.llm_client import LLMClient
from cloudra.infra.token_estimator import TokenEstimator
from cloudra.persistence import paths
from cloudra.persistence.database import ConversationDB, aretry_on_locked, get_database_path
from cloudra.persistence.fs_utils import atomic_write_jsonl

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


def parse_context_text(text: str) -> tuple[list, bool]:
    """解析上下文文件内容，返回 ``(blocks, is_legacy_json)``。

    磁盘格式：
    - 新格式 JSONL：每行一个 block（``json.dumps(block)``，不带缩进）；
    - 旧格式：单个缩进 JSON 数组（历史版本全量重写整个文件，O(N²) 写放大）。

    JSONL 下无法解析的行（典型：进程崩溃在文件尾部留下的半行）跳过并告警，
    不让一条坏行毁掉整段历史。
    """
    stripped = text.lstrip()
    if not stripped:
        return [], False
    if stripped.startswith("["):
        return json.loads(text), True
    blocks: list = []
    skipped = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            blocks.append(json.loads(line))
        except json.JSONDecodeError:
            skipped += 1
    if skipped:
        print(
            f"[ContextManager] 上下文文件有 {skipped} 行无法解析"
            "（疑似崩溃遗留的半行），已跳过"
        )
    return blocks, False


def read_context_file(path: str) -> list:
    """读取上下文文件（新旧两种格式均可），返回 block 列表。

    供 ContextManager 之外的只读消费者（如 GetSubAgentReport、测试断言）使用。
    """
    with open(path, "r", encoding="utf-8") as f:
        blocks, _ = parse_context_text(f.read())
    return blocks


# Supervisor 建议消息在上下文中的标记，用于定位更新
SUPERVISOR_ADVICE_MARKER = "[Supervisor]"

# 压缩梗概消息的内容前缀：持久化压缩与手动 compact 共用，
# 用于在下一轮压缩时识别旧梗概并折叠进新梗概（避免梗概无限累积）。
# 梗概以 role=user 写入，引导模型按交接信息接续（勿再用 system，易被当成身份层忽略）。
COMPACT_SUMMARY_MARKER = "[上下文压缩提示]"
COMPACT_SUMMARY_INSTRUCTION = (
    "根据下面这份交接信息继续工作。"
    "上下文刚被压缩：`[Skill 资料]` 已在 system 层原样钉住保留，"
    "如非必要不要再次 getskill 同名 skill（核对语义请直接读已有 Skill 资料；"
    "仅当需要 `other=` 取 reference 附件、或列表中明确缺失某 skill 时才加载）。"
)

# getskill 返回被提升为 system 钉住时的前缀，压缩时不进摘要、不丢弃。
SKILL_PIN_MARKER = "[Skill 资料]"

# 需要整段保留的 skill 工具名（匹配 assistant.tool_calls[].function.name）。
SKILL_TOOL_NAMES = frozenset({"getskill"})

# 自动/请求期压缩：不再保留近几轮 toolcall 原文——工具往返体积大且易过期，
# 状态应落在工作区交接文档里（见 prompt_assembler 的交接指引）。0 = 尾部不留
# assistant/tool 回合，全部进梗概。
AUTO_COMPACT_KEEP_ASSISTANT = 0
RENDER_COMPACT_KEEP_ASSISTANT = 0

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
        # 上下文实例缓存：正常路径本实例是唯一写者，首次 load 后驻留内存。
        # inject 会另建实例写同一文件，活 Agent 用 reload_from_disk() 对齐。
        self._context_cache: Optional[list] = None
        # 首次 load 时探测到的磁盘格式：True 表示旧版单 JSON 数组，
        # 下一次 append/replace 会先迁移为 JSONL 再写入。
        self._file_is_legacy = False
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
            or content.startswith(COMPACT_SUMMARY_MARKER)
            or content.startswith(SKILL_PIN_MARKER)
        )

    async def _migrate_legacy_identity(self, context: list) -> list:
        if not self._is_legacy_identity_message(context):
            return context
        migrated = context[1:]
        await self.replace(migrated)
        return migrated

    async def load(self) -> list:
        """加载上下文；若文件不存在则初始化并保存。

        同时支持新旧两种磁盘格式（见 ``parse_context_text``）：读到旧版
        单 JSON 数组格式时正常返回内容，并标记 ``_file_is_legacy``，
        下一次写（append/replace）会迁移为 JSONL——旧会话永远不会读不出。

        首次读取后驻留实例缓存（正常路径本实例是该文件的唯一写者），
        后续 load 不再触碰磁盘。inject 路径会另建 ContextManager 往同一
        文件 append，活着的 Agent 应先 ``reload_from_disk()`` 再读。

        解析失败时只读返回空、绝不回写磁盘：TUI 状态栏等只读实例以
        query="" 构造，若在解析失败分支里执行 replace(_initial_context())，
        会把 [] 覆盖回上下文文件，一次性冲掉整段对话历史（历史故障根因，
        见 _drop_empty_user_messages 的回归说明）。
        """
        if self._context_cache is not None:
            return self._context_cache
        if os.path.isfile(self.context_file):
            try:
                def read_context() -> tuple[list, bool]:
                    with open(self.context_file, 'r', encoding='utf-8') as f:
                        return parse_context_text(f.read())

                self._context_cache, self._file_is_legacy = await asyncio.to_thread(read_context)
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

    async def reload_from_disk(self) -> list:
        """丢弃实例缓存并从磁盘重读。

        inject 路径会另建 ContextManager 把 user 行落到同一文件；活着的
        Agent 实例必须能看见那一行，否则 ``_consume_external_events`` 会
        按过期缓存再写一条【user_message】系统行。
        """
        self._context_cache = None
        return await self.load()

    async def replace(self, context: list) -> None:
        """全量替换上下文并持久化到文件（同时刷新实例缓存）。

        磁盘格式为 JSONL（每行一个 block）。写入采用临时文件 + 原子改名
        （``os.replace``），保证外部只读进程（TUI 状态栏、ContextScreen 等）
        并发读取时永远读到完整内容，不会因看到写入中的半截文件而解析失败。
        """
        self._context_cache = context
        self._file_is_legacy = False

        def write_context() -> None:
            atomic_write_jsonl(self.context_file, context)

        await asyncio.to_thread(write_context)

    async def append(self, new_block: dict) -> None:
        """追加一条消息到上下文，并持久化。

        正常路径只向文件追加一行 JSON（一个 block 一行），不再像旧实现那样
        每次全量重写整个文件（长会话下总写入量从 O(N²) 降为 O(N)）。
        例外走全量 ``replace``：磁盘上仍是旧版单 JSON 数组格式（先迁移为
        JSONL），或文件已被外部删除（重建完整内容）。
        """
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

        if self._file_is_legacy or not os.path.isfile(self.context_file):
            await self.replace(context)
            return

        def append_line() -> None:
            line = json.dumps(new_block, ensure_ascii=False) + "\n"
            with open(self.context_file, "r+b") as f:
                # 自愈：上次追加若崩溃留下半行（文件末尾无换行），先补一个
                # 换行把半行隔离成一条会被 load 跳过的坏行，再写新行，
                # 避免新旧两行黏在一起导致新行也无法解析。
                f.seek(0, os.SEEK_END)
                if f.tell() > 0:
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        f.write(b"\n")
                f.write(line.encode("utf-8"))

        await asyncio.to_thread(append_line)

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
        2. 工具结果与 user/assistant 原文进入模型（不按字符/token 拦腰截断；
           体积由超窗后的持久化压缩管）。
        3. 用 tiktoken 精确计数后，若超过 ``max_context_tokens``，先做持久化压缩
           （保留 system / getskill 资料；默认不保留近几轮 toolcall，全部进梗概），
           仍超预算再退回 render-time 压缩。
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
        rendered = self._repair_tool_pairing(rendered)
        # Very large tool results make capping and token counting measurable
        # CPU work.  They must not run on the TUI/Agent event-loop thread.
        rendered = await asyncio.to_thread(self._cap_message_sizes, rendered)

        if max_context_tokens is None:
            return rendered

        # 压缩触发必须先拿到确切 token 计数（tiktoken；失败才回退启发式）。
        rendered_tokens = await self._measure_tokens(rendered)
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
    def _repair_tool_pairing(messages: list[dict]) -> list[dict]:
        """修复 tool_calls 与 tool 结果的配对（两个方向）。

        OpenAI 协议要求带 tool_calls 的 assistant 消息与对应 tool 结果严格
        配对，严格端点（如 DeepSeek /responses）对任一方向的失配都会以 400
        拒绝整个请求，且之后每轮请求都带着这条坏消息——会话永久变砖。

        1. 孤儿 tool 结果：tool 消息的 ``tool_call_id`` 在消息列表中任何
           assistant 的 tool_calls 里找不到（典型来源：上下文压缩把带
           tool_calls 的 assistant 梗概掉，却把它的 tool 结果留在了保留
           尾部）→ 直接丢弃该 tool 消息。
        2. 无结果的 tool_calls：assistant 发起调用与结果写回之间被打断/
           取消，或结果在压缩中丢失 → 在该 assistant 消息（及其后连续的
           tool 结果组）之后补一条占位 tool 消息（幂等：已被响应覆盖的
           id 不会重复补）。
        """
        declared: set[str] = set()
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            for call in msg.get("tool_calls") or []:
                call_id = call.get("id") if isinstance(call, dict) else None
                if call_id:
                    declared.add(call_id)

        answered = {
            msg.get("tool_call_id")
            for msg in messages
            if msg.get("role") == "tool" and msg.get("tool_call_id")
        }

        repaired: list[dict] = []
        # 缺失结果的占位 tool 消息：等当前 assistant 的 tool 结果组结束后再插入
        pending: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                call_id = msg.get("tool_call_id")
                if call_id and call_id not in declared:
                    continue  # 孤儿 tool 结果：丢弃
                repaired.append(msg)
                continue
            # tool 结果组结束：先把上一个 assistant 缺失结果的占位补上
            repaired.extend(pending)
            pending.clear()
            repaired.append(msg)
            if role != "assistant":
                continue
            for call in msg.get("tool_calls") or []:
                call_id = call.get("id") if isinstance(call, dict) else None
                if call_id and call_id not in answered:
                    pending.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": "[工具结果缺失：可能在上下文压缩中丢失]",
                    })
                    answered.add(call_id)
        repaired.extend(pending)
        return repaired

    def _cap_message_sizes(self, messages: list[dict]) -> list[dict]:
        """渲染/摘要前的消息尺寸钩子。

        拦腰截断会让模型以为没看全而反复重调；超窗由持久化压缩按 token 分块处理。
        """
        return messages

    async def _measure_tokens(self, messages: list[dict]) -> int:
        """确切 token 计数：优先 tiktoken，失败再走 LLMClient / 启发式。"""
        cfg = get_config().follower
        if cfg.model:
            TokenEstimator.configure(model=cfg.model)
        try:
            if self._llm_client is None and cfg.key and cfg.url:
                self._llm_client = LLMClient(api_key=cfg.key, base_url=cfg.url, model=cfg.model)
            if self._llm_client is not None:
                result = await self._llm_client.count_tokens(messages, model=cfg.model)
                return int(result["tokens"])
        except Exception:
            pass
        return await asyncio.to_thread(TokenEstimator.count_messages, messages)

    @staticmethod
    def _tool_call_names(messages: list[dict]) -> dict[str, str]:
        """从 assistant.tool_calls 建立 tool_call_id → function.name 映射。"""
        mapping: dict[str, str] = {}
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            for call in msg.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                call_id = call.get("id")
                name = (call.get("function") or {}).get("name") or ""
                if call_id:
                    mapping[str(call_id)] = str(name)
        return mapping

    @classmethod
    def _is_skill_tool_result(cls, msg: dict, name_by_id: dict[str, str]) -> bool:
        if msg.get("role") != "tool":
            return False
        call_id = msg.get("tool_call_id")
        if not call_id:
            return False
        return name_by_id.get(str(call_id), "") in SKILL_TOOL_NAMES

    @staticmethod
    def _skill_name_from_call(call: dict) -> str:
        """从 getskill tool_call.arguments 解析 skill_name。"""
        raw = (call.get("function") or {}).get("arguments")
        if isinstance(raw, dict):
            data = raw
        elif isinstance(raw, str) and raw.strip():
            try:
                data = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                data = {}
        else:
            data = {}
        if not isinstance(data, dict):
            return ""
        name = data.get("skill_name") or data.get("name") or ""
        return str(name).strip()

    @classmethod
    def _skill_name_by_call_id(cls, messages: list[dict]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            for call in msg.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                call_id = call.get("id")
                if not call_id:
                    continue
                skill = cls._skill_name_from_call(call)
                if skill:
                    mapping[str(call_id)] = skill
        return mapping

    @staticmethod
    def _skill_pin_key(content: str) -> str:
        """从 pin 正文取去重键：优先 ``skill=``，否则用正文前缀哈希。"""
        first = (content or "").split("\n", 1)[0]
        marker = f"{SKILL_PIN_MARKER} skill="
        if first.startswith(marker):
            return first[len(marker):].strip().split()[0]
        # 旧格式或匿名 pin：用稳定前缀区分，避免互不相同的资料被误并
        prefix = (content or "")[:240]
        return f"anon:{hash(prefix)}"

    @classmethod
    def _skill_names_from_pins(cls, pins: list[dict]) -> list[str]:
        """从 skill pin 列表提取具名 skill（跳过 anon），保序去重。"""
        names: list[str] = []
        seen: set[str] = set()
        for pin in pins:
            key = cls._skill_pin_key(str(pin.get("content") or ""))
            if not key or key.startswith("anon:"):
                continue
            if key in seen:
                continue
            seen.add(key)
            names.append(key)
        return names

    @classmethod
    def _pinned_skills_handoff_block(cls, skill_names: list[str]) -> str:
        """压缩交接末尾的确定性说明：已钉住 skill 勿再列为待办。"""
        if not skill_names:
            return (
                "\n\n**Skill 钉住**：本次交接未额外列出钉住 skill；"
                "若上下文里已有 `[Skill 资料]`，仍视为已加载——"
                "如非必要不要重复 getskill。"
            )
        joined = "、".join(skill_names)
        return (
            "\n\n**已钉住的 Skill（如非必要不要重复 getskill）**："
            f"{joined}。"
            "压缩不会丢弃这些 SOP——它们以 `[Skill 资料]` 原样留在 system 层。"
            "不要因为「压缩后想核对语义」而再 getskill 同名 skill；直接使用已有钉住内容。"
            "仅当需要 `other=` 读取 reference 附件、或上述列表里没有你真正缺少的 skill 时才调用 getskill。"
            "下一步应推进任务（建图/计算/写交接文档），不要把「加载/重读 skill」当阻塞点。"
        )

    @classmethod
    def _normalize_skill_pins(cls, pins: list[dict]) -> list[dict]:
        """同名 skill 只留最新一条；正文不截断。"""
        by_key: dict[str, dict] = {}
        order: list[str] = []
        for pin in pins:
            content = str(pin.get("content") or "")
            if not content.strip():
                continue
            key = cls._skill_pin_key(content)
            if key not in by_key:
                order.append(key)
            by_key[key] = {"role": "system", "content": content}

        return [by_key[k] for k in order]

    @classmethod
    def _split_skill_pins_from_system(
        cls, system_messages: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """把已存在的 Skill 钉住从其它 system（身份/Supervisor）中拆出。"""
        pins: list[dict] = []
        other: list[dict] = []
        for msg in system_messages:
            content = msg.get("content", "")
            if isinstance(content, str) and content.startswith(SKILL_PIN_MARKER):
                pins.append(msg)
            else:
                other.append(msg)
        return pins, other

    @staticmethod
    def _is_compact_summary_message(msg: dict) -> bool:
        content = msg.get("content", "")
        return isinstance(content, str) and content.startswith(COMPACT_SUMMARY_MARKER)

    @classmethod
    def _make_compact_summary_message(
        cls, summary: str, pinned_skill_names: list[str] | None = None
    ) -> dict:
        """生成压缩交接消息：role=user，便于模型当作当前任务接续。"""
        content = (
            f"{COMPACT_SUMMARY_MARKER}\n"
            f"{COMPACT_SUMMARY_INSTRUCTION}\n\n"
            f"{summary}"
        )
        content += cls._pinned_skills_handoff_block(pinned_skill_names or [])
        return {
            "role": "user",
            "content": content,
        }

    @classmethod
    def _extract_skill_pins(
        cls, messages: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """把 getskill 工具返回提升为 system 钉住，并从历史中剥离对应调用。

        返回 (skill_pins, remainder)。skill 内容以 ``SKILL_PIN_MARKER`` system
        消息保留，避免压缩摘要冲掉 SOP；原 tool 配对从 remainder 移除并清掉
        对应 tool_calls，以免留下孤儿结果。同名 skill 在
        ``_normalize_skill_pins`` 中去重。
        """
        name_by_id = cls._tool_call_names(messages)
        skill_name_by_id = cls._skill_name_by_call_id(messages)
        skill_ids = {
            call_id
            for call_id, name in name_by_id.items()
            if name in SKILL_TOOL_NAMES
        }
        if not skill_ids:
            return [], list(messages)

        pins: list[dict] = []
        remainder: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool" and str(msg.get("tool_call_id", "")) in skill_ids:
                text = cls._content_to_text(msg.get("content"))
                if text.strip():
                    call_id = str(msg.get("tool_call_id", ""))
                    skill = skill_name_by_id.get(call_id, "")
                    header = (
                        f"{SKILL_PIN_MARKER} skill={skill}"
                        if skill
                        else SKILL_PIN_MARKER
                    )
                    pins.append({
                        "role": "system",
                        "content": f"{header}\n{text}",
                    })
                continue
            if role == "assistant" and msg.get("tool_calls"):
                original_calls = list(msg.get("tool_calls") or [])
                kept_calls = [
                    call for call in original_calls
                    if not (
                        isinstance(call, dict)
                        and str(call.get("id", "")) in skill_ids
                    )
                ]
                if len(kept_calls) == len(original_calls):
                    remainder.append(msg)
                    continue
                new_msg = dict(msg)
                if kept_calls:
                    new_msg["tool_calls"] = kept_calls
                    remainder.append(new_msg)
                else:
                    new_msg.pop("tool_calls", None)
                    # 仅发起 getskill、无其它内容的 assistant 可丢弃
                    if (
                        new_msg.get("content")
                        or new_msg.get("reasoning_content")
                    ):
                        remainder.append(new_msg)
                continue
            remainder.append(msg)
        return pins, remainder

    async def _summarize_history(
        self,
        history: list[dict],
        pinned_skill_names: list[str] | None = None,
    ) -> str:
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

        input_limit = max(8_000, min(64_000, int(cfg.context_window or 200_000) // 2))
        pinned_names = list(pinned_skill_names or [])
        pinned_note = ""
        if pinned_names:
            pinned_note = (
                "下列 skill 本次压缩已钉住并在梗概外单独保留，必须写入「已完成」，"
                "禁止写成待办/阻塞/未落地，禁止写「压缩后需核对/重读 skill」，"
                "也禁止要求再次 getskill 同名 skill："
                f"{'、'.join(pinned_names)}。\n"
            )

        def partition(items: list[str]) -> list[list[str]]:
            expanded: list[str] = []
            for item in items:
                if TokenEstimator.count_text(item) <= input_limit:
                    expanded.append(item)
                    continue
                # 按 token 硬切，避免把 token 预算误当成字符数。
                remaining = item
                while remaining:
                    if TokenEstimator.count_text(remaining) <= input_limit:
                        expanded.append(remaining)
                        break
                    chunk = TokenEstimator.truncate_to_tokens(remaining, input_limit)
                    if not chunk:
                        chunk = remaining[: max(1, min(len(remaining), input_limit))]
                    expanded.append(chunk)
                    remaining = remaining[len(chunk):]
            chunks: list[list[str]] = []
            current: list[str] = []
            current_tokens = 0
            for item in expanded:
                item_tokens = TokenEstimator.count_text(item) + 2
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
            # 超长单条由 partition 按 token 分块，不在这里拦腰截断。
            lines: list[str] = []
            for msg in history:
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
                "你正在为科研 Agent 压缩对话历史。输出一段结构化梗概，供后续模型"
                "接续任务；不要写客套话，不要发明未出现的事实。\n\n"
                "必须保留：\n"
                "1. 用户总目标与当前子目标\n"
                "2. 已完成步骤与关键结论（含数值、判据、成功/失败）\n"
                "3. 重要文件路径——尤其是交接文档（HANDOFF.md / progress.md 等）、"
                "分子/反应标识、作业 ID\n"
                "4. 失败原因与已尝试的修复\n"
                "5. 尚未完成的待办与阻塞点\n\n"
                "可以丢弃：重复的工具日志、冗长原始输出、已过时的中间猜测、"
                "逐条 tool_call 参数原文（用路径与结论代替）。\n"
                "注意：system prompt 与 getskill 资料会在梗概之外单独保留（`[Skill 资料]` 钉住），"
                "无需在梗概中复述完整 SOP。历史里 getskill 的 tool 成功记录可能已被"
                "抽走钉住，因此不能仅因摘要输入看不到 tool 结果就断定 skill 未加载，"
                "也不要把「压缩后核对/重读 skill」写成待办。"
                "后续轮次应优先打开梗概里点名的交接文档，如非必要不要建议再次 getskill。\n"
                f"{pinned_note}\n"
                "--- 历史对话 ---\n\n"
                f"{history_text}\n\n"
                "--- 梗概（用简洁条目或短段落）---"
            )

            if self._llm_client is None:
                self._llm_client = LLMClient(
                    api_key=api_key, base_url=base_url, model=model
                )
            response = await self._llm_client.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是对话历史压缩器。只输出忠实、可执行的状态摘要，"
                            "优先保留目标、路径、结论与失败信息。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
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

    @staticmethod
    def _split_tail_keep_tool_pairs(
        compressible: list[dict], tail_count: int
    ) -> tuple[list[dict], list[dict]]:
        """按条数切出保留尾部，并把切口对齐到 tool_calls 配对边界。

        若切口恰好落在「带 tool_calls 的 assistant 消息」与其 tool 结果之间，
        尾部首条会是没有匹配 function_call 的孤儿 function_call_output，
        严格端点（如 DeepSeek /responses）会以 400 拒绝之后整个会话的所有
        请求。这里在尾部首条为 tool 消息时把切口左移一条（把它前面的消息
        拉进尾部），直到首条不再是 tool 或 history 耗尽；耗尽时（找不到
        配对的 assistant）丢弃尾部开头的孤儿 tool 消息。

        返回 (history, tail)。
        """
        if tail_count <= 0:
            return list(compressible), []
        history = list(compressible[:-tail_count])
        tail = list(compressible[-tail_count:])
        while tail and tail[0].get("role") == "tool":
            if history:
                tail.insert(0, history.pop())
            else:
                # 配对的 assistant 不在上下文里：孤儿 tool 结果直接丢弃
                tail.pop(0)
        return history, tail

    @staticmethod
    def _count_tail_keep_assistant(
        compressible: list[dict], keep_assistant: int
    ) -> int:
        """按「最近 N 个 assistant 回合」计算应保留的尾部消息条数。

        ``keep_assistant <= 0`` 表示不保留任何尾部（含 toolcall 链），全部交梗概。
        """
        if keep_assistant <= 0 or not compressible:
            return 0
        tail_count = 0
        assistant_seen = 0
        for msg in reversed(compressible):
            tail_count += 1
            if msg.get("role") == "assistant":
                assistant_seen += 1
            if assistant_seen >= keep_assistant:
                break
        return tail_count

    async def _compress_persistent(self) -> bool:
        """超预算时先做持久化压缩：把历史梗概一次性写回上下文存储。

        保留策略：
        - 全部非梗概 system（含 Supervisor）；已钉住 Skill 与新 getskill 合并去重
        - 历史折叠为一条 role=user 的交接梗概（``COMPACT_SUMMARY_INSTRUCTION``）
        - 最近 ``AUTO_COMPACT_KEEP_ASSISTANT`` 个 assistant 回合（默认 0：不留 toolcall）
        - 旧梗概（system/user 两种历史格式）会并入新梗概

        返回是否发生了持久化压缩（无可压缩历史或梗概生成失败时为 False）。
        """
        context = await self.load()

        pinned_system: list[dict] = []
        compressible: list[dict] = []
        for msg in context:
            # 梗概不论旧 system 还是新 user，都进可压缩历史以便折叠
            if msg.get("role") == "system" and not self._is_compact_summary_message(msg):
                pinned_system.append(msg)
            else:
                compressible.append(msg)

        existing_pins, pinned_system = self._split_skill_pins_from_system(
            pinned_system
        )

        tail_count = self._count_tail_keep_assistant(
            compressible, AUTO_COMPACT_KEEP_ASSISTANT
        )
        history, tail = self._split_tail_keep_tool_pairs(compressible, tail_count)
        if not history:
            return False

        # getskill 资料从待摘要历史中钉住，避免 SOP 被梗概冲淡
        skill_pins, history = self._extract_skill_pins(history)
        skill_pins = self._normalize_skill_pins(existing_pins + skill_pins)
        history = await asyncio.to_thread(self._cap_message_sizes, history)
        if not history:
            # 只有 skill 可抽、无可摘要正文：仍写回钉住 + 尾部
            await self.replace(pinned_system + skill_pins + tail)
            return bool(skill_pins)

        try:
            pinned_names = self._skill_names_from_pins(skill_pins)
            summary = await self._summarize_history(
                history, pinned_skill_names=pinned_names
            )
        except Exception as e:
            print(
                f"\033[93m[ContextManager]\033[0m 持久化压缩的梗概生成失败，"
                f"退回 render-time 压缩: {e}"
            )
            return False

        await self.replace(
            pinned_system
            + skill_pins
            + [
                self._make_compact_summary_message(
                    summary, pinned_skill_names=pinned_names
                )
            ]
            + tail
        )
        return True

    async def _compress_to_budget(
        self,
        messages: list[dict],
        max_context_tokens: int,
    ) -> list[dict]:
        """在不超过 token 预算的前提下压缩消息列表（仅当次请求副本）。

        保留：非 skill / 非梗概 system、去重后的 getskill 资料、一条 user
        交接梗概、最近 ``RENDER_COMPACT_KEEP_ASSISTANT`` 个 assistant 回合（默认 0）。
        """
        if not messages:
            return messages

        total = await self._measure_tokens(messages)
        if total <= max_context_tokens:
            return messages

        # 旧版 system 梗概与 skill 钉住都在 system 里；梗概要进 history 折叠
        system_messages: list[dict] = []
        non_system: list[dict] = []
        for msg in messages:
            if msg.get("role") == "system" and not self._is_compact_summary_message(msg):
                system_messages.append(msg)
            else:
                non_system.append(msg)
        existing_pins, system_messages = self._split_skill_pins_from_system(
            system_messages
        )

        tail_count = self._count_tail_keep_assistant(
            non_system, RENDER_COMPACT_KEEP_ASSISTANT
        )
        history, tail = self._split_tail_keep_tool_pairs(non_system, tail_count)
        if not history:
            return messages

        skill_pins, history = self._extract_skill_pins(history)
        skill_pins = self._normalize_skill_pins(existing_pins + skill_pins)
        history = await asyncio.to_thread(self._cap_message_sizes, history)
        if not history:
            return system_messages + skill_pins + tail

        # 交接梗概已是 user：若历史只剩旧/新梗概，勿再调一次摘要模型
        if all(self._is_compact_summary_message(m) for m in history):
            return messages

        try:
            pinned_names = self._skill_names_from_pins(skill_pins)
            summary = await self._summarize_history(
                history, pinned_skill_names=pinned_names
            )
        except Exception as e:
            print(
                f"\033[93m[ContextManager]\033[0m 历史消息梗概生成失败，"
                f"保留原始历史消息不压缩: {e}"
            )
            return messages

        candidate = (
            system_messages
            + skill_pins
            + [
                self._make_compact_summary_message(
                    summary, pinned_skill_names=pinned_names
                )
            ]
            + tail
        )

        candidate_tokens = await self._measure_tokens(candidate)
        if candidate_tokens <= max_context_tokens:
            return candidate

        print(
            f"\033[93m[ContextManager]\033[0m 警告：生成的历史梗概仍超过 "
            f"{max_context_tokens} token 预算，本次请求保留完整上下文。"
        )
        return messages

    async def compact(self, keep_recent: int = 5) -> dict:
        """手动压缩持久化上下文。

        保留：非梗概 system（Supervisor 等）、去重后的 getskill 钉住、
        一条 user 交接梗概、最近 ``keep_recent`` 条消息；其余生成梗概写回。

        Args:
            keep_recent: 保留的最近消息条数，必须 >= 1，默认 5。
        """
        if keep_recent < 1:
            raise ValueError("keep_recent 必须 >= 1")

        context = await self.load()
        original_count = len(context)

        pinned_system: list[dict] = []
        compressible: list[dict] = []
        for msg in context:
            if msg.get("role") == "system" and not self._is_compact_summary_message(msg):
                pinned_system.append(msg)
            else:
                compressible.append(msg)

        existing_pins, pinned_system = self._split_skill_pins_from_system(
            pinned_system
        )

        if len(compressible) <= keep_recent:
            return {
                "original_count": original_count,
                "new_count": original_count,
                "summary_length": 0,
                "compressed": False,
                "reason": (
                    f"可压缩消息仅 {len(compressible)} 条，"
                    f"未超过保留窗口 {keep_recent} 条"
                ),
            }

        history, tail = self._split_tail_keep_tool_pairs(compressible, keep_recent)
        if not history:
            return {
                "original_count": original_count,
                "new_count": original_count,
                "summary_length": 0,
                "compressed": False,
                "reason": "保留窗口向 tool_calls 配对边界对齐后没有可压缩的历史",
            }

        skill_pins, history = self._extract_skill_pins(history)
        skill_pins = self._normalize_skill_pins(existing_pins + skill_pins)
        history = await asyncio.to_thread(self._cap_message_sizes, history)
        if not history:
            new_context = pinned_system + skill_pins + list(tail)
            await self.replace(new_context)
            return {
                "original_count": original_count,
                "new_count": len(new_context),
                "summary_length": 0,
                "compressed": bool(skill_pins),
                "reason": "历史仅含 getskill 资料，已钉住并保留尾部",
            }

        pinned_names = self._skill_names_from_pins(skill_pins)
        summary = await self._summarize_history(
            history, pinned_skill_names=pinned_names
        )
        new_context = (
            pinned_system
            + skill_pins
            + [
                self._make_compact_summary_message(
                    summary, pinned_skill_names=pinned_names
                )
            ]
            + list(tail)
        )
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
        session_id: Optional[str] = None,
    ) -> None:
        """外部生产者调用，将事件写入 context_events 表。

        该方法是静态方法，因为生产者通常不持有目标 Agent 的 ContextManager 实例。
        session_id 用于区分同 conversation 下同 agent_id 的并行 session；
        为 None 时事件视为会话级广播，所有同名 session 都会收到。
        """
        path = db_path or _db_path(conversation_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        db = ConversationDB.from_path(path)

        async def insert_event() -> None:
            async with db.aconnect() as con:
                await con.execute(
                    """
                    INSERT INTO context_events (conversation_id, agent_id, session_id, event_type, content, state, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (conversation_id, agent_id, session_id, event_type, content, 'pending', time.time())
                )
                await con.commit()

        await aretry_on_locked(insert_event)
        await events.aemit(
            conversation_id,
            "external_event",
            agent_id=agent_id,
            session_id=session_id,
            event_type=event_type,
            content=content,
        )


    async def drain_pending_events(self) -> list[dict]:
        """读取并消费属于本 agent 的 pending 外部事件（用于离线恢复或启动补拉）。

        带 session 身份时只消费本 session 的事件与会话级广播（session_id 为 NULL），
        避免同 conversation 下同 agent_id 的并行 session 互相串扰。
        """
        db = ConversationDB.from_path(self.db_path)
        if self.session_id is not None:
            where = (
                "conversation_id = ? AND agent_id = ? AND state = 'pending' "
                "AND (session_id IS NULL OR session_id = ?)"
            )
            params = (self.conversation_id, self.agent_id, self.session_id)
        else:
            where = "conversation_id = ? AND agent_id = ? AND state = 'pending'"
            params = (self.conversation_id, self.agent_id)

        async def poll() -> list[dict]:
            found = []
            async with db.aconnect() as con:
                cur = await con.execute(
                    f"""
                    SELECT id, event_type, content FROM context_events
                    WHERE {where}
                    ORDER BY created_at ASC
                    """,
                    params,
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
        """检查是否有待处理的外部事件（与 drain_pending_events 同样的 session 过滤）。"""
        db = ConversationDB.from_path(self.db_path)
        if self.session_id is not None:
            where = (
                "conversation_id = ? AND agent_id = ? AND state = 'pending' "
                "AND (session_id IS NULL OR session_id = ?)"
            )
            params = (self.conversation_id, self.agent_id, self.session_id)
        else:
            where = "conversation_id = ? AND agent_id = ? AND state = 'pending'"
            params = (self.conversation_id, self.agent_id)

        async def count_pending() -> bool:
            async with db.aconnect() as con:
                cur = await con.execute(
                    f"SELECT COUNT(*) FROM context_events WHERE {where}",
                    params,
                )
                row = await cur.fetchone()
                return row[0] > 0 if row else False

        return await aretry_on_locked(count_pending)
