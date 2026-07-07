"""Coordinator 长期记忆管理（MEMORY.md）。

本模块为 Cloudra 提供自学习记忆能力：
1. Coordinator 在任务执行过程中调用 `update_memory` 工具，把获得的经验/技能提醒写入 MEMORY.md。
2. MEMORY.md 在 Coordinator 启动时自动加载为 system prompt 的一部分。
3. 当记忆字数超过阈值时，自动调用 LLM 压缩为更精简的“核心原则”，旧条目归档。

文件位置：
- 全局记忆：`<data_dir>/memory/MEMORY.md`
- conversation 级记忆（预留）：`<data_dir>/conversations/<conv_id>/memory/MEMORY.md`

当前默认使用全局记忆，使 Coordinator 能跨任务积累经验。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI

from cloudra.config import get_config


# 默认记忆字数上限（中文字符按 1 个计，英文单词按 1 个计）。
# 超过此阈值时触发自动压缩。
DEFAULT_MEMORY_WORD_LIMIT = 4000

# 压缩后保留的最大字数
DEFAULT_COMPRESSED_WORD_LIMIT = 2000


class MemoryManager:
    """管理 Coordinator 的长期记忆文件（MEMORY.md）。"""

    def __init__(
        self,
        conversation_id: Optional[str] = None,
        word_limit: int = DEFAULT_MEMORY_WORD_LIMIT,
        compressed_word_limit: int = DEFAULT_COMPRESSED_WORD_LIMIT,
    ):
        self.conversation_id = conversation_id or "default"
        self.word_limit = max(100, word_limit)
        self.compressed_word_limit = max(100, compressed_word_limit)
        self.memory_path = self._resolve_path()

    def _resolve_path(self) -> Path:
        """解析记忆文件路径。当前默认使用全局记忆。"""
        data_dir = get_config().data_dir
        # 如需按 conversation 隔离，可改为 conversations/{conv_id}/memory/MEMORY.md
        path = Path(data_dir) / "memory" / "MEMORY.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def exists(self) -> bool:
        """记忆文件是否存在。"""
        return self.memory_path.exists()

    def load(self) -> str:
        """加载记忆文件内容；不存在时返回空字符串。"""
        if not self.exists():
            return ""
        try:
            return self.memory_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[MemoryManager] 读取 MEMORY.md 失败: {e}")
            return ""

    def _count_words(self, text: str) -> int:
        """估算字数：中文字符 + 英文单词分别计数。"""
        if not text:
            return 0
        # 中文字符
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        # 英文单词：连续字母/数字序列
        en_words = len(re.findall(r"[a-zA-Z0-9]+", text))
        return cn_chars + en_words

    def append_lesson(
        self,
        lesson: str,
        source: str = "",
        skill_name: str = "",
    ) -> str:
        """追加一条经验到 MEMORY.md，并在超限时自动压缩。

        Args:
            lesson: 经验/技能提醒的具体内容。
            source: 来源，例如子 Agent 名称、session_id、任务描述。
            skill_name: 可选的技能分类标签。

        Returns:
            操作结果描述。
        """
        if not lesson or not lesson.strip():
            return "没有可记录的内容。"

        current_text = self.load()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        skill_tag = f" [{skill_name}]" if skill_name else ""

        entry = (
            f"\n## Lesson{skill_tag} ({timestamp})\n\n"
            f"- **Source**: {source or 'Coordinator'}\n"
            f"- **Lesson**: {lesson.strip()}\n"
        )

        if not current_text.strip():
            current_text = "# Cloudra Coordinator Memory\n\n" + entry
        else:
            current_text = current_text.rstrip() + "\n" + entry

        self.memory_path.write_text(current_text, encoding="utf-8")

        word_count = self._count_words(current_text)
        if word_count > self.word_limit:
            self._compress_memory()
            return f"已记录经验并触发记忆压缩（原字数 {word_count}）。"

        return f"已记录经验（当前记忆字数 {word_count}）。"

    def _compress_memory(self) -> None:
        """当记忆超过字数上限时，调用 LLM 压缩为核心原则。"""
        current_text = self.load()
        if not current_text.strip():
            return

        compressed = self._llm_compress(current_text)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        new_content = (
            "# Cloudra Coordinator Memory\n\n"
            f"_（以下内容由历史经验自动压缩生成，更新时间：{timestamp}）_\n\n"
            f"{compressed.strip()}\n"
        )

        # 保留原始记忆的归档副本
        archive_path = self.memory_path.with_suffix(".archive.md")
        archive_entry = (
            f"\n\n# Archived memory before {timestamp}\n\n{current_text}"
        )
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(archive_entry)

        self.memory_path.write_text(new_content, encoding="utf-8")
        print(
            f"[MemoryManager] MEMORY.md 已自动压缩并归档到 {archive_path}"
        )

    def _llm_compress(self, text: str) -> str:
        """调用 FOLLOWER 配置的大模型把记忆压缩成核心原则。"""
        cfg = get_config().follower
        model = cfg.model
        base_url = cfg.url
        api_key = cfg.key

        if not all([model, base_url, api_key]):
            # 未配置 LLM 时做简单的启发式截断
            return self._fallback_compress(text)

        prompt = (
            "你正在维护一个 AI 科研助手的长期记忆库。以下内容是 Coordinator 在多次任务中"
            "积累的经验、技能提醒和失败教训。请把它们压缩成一份精简的“核心原则”列表，"
            "保留最重要的判断标准、常用工具组合、常见陷阱和最佳实践。"
            "去掉具体的时间戳和重复内容，用条目式输出。总字数控制在 {limit} 字以内。\n\n"
            "--- 原始记忆 ---\n\n{text}\n\n"
            "--- 核心原则 ---"
        ).format(limit=self.compressed_word_limit, text=text[:12000])

        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个专门整理科研助手长期记忆的助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            result = response.choices[0].message.content
            return result.strip() if result else self._fallback_compress(text)
        except Exception as e:
            print(f"[MemoryManager] LLM 压缩失败: {e}，使用启发式压缩。")
            return self._fallback_compress(text)

    def _fallback_compress(self, text: str) -> str:
        """未配置 LLM 时的启发式压缩：只保留最近的条目。"""
        lines = text.splitlines()
        # 保留标题和最近约 compressed_word_limit 字的内容
        kept = []
        total = 0
        for line in reversed(lines):
            w = self._count_words(line)
            if total + w > self.compressed_word_limit:
                break
            kept.append(line)
            total += w
        kept.reverse()
        return "\n".join(kept) if kept else "（记忆内容已压缩）"


def get_memory_manager(conversation_id: Optional[str] = None) -> MemoryManager:
    """工厂函数，获取 MemoryManager 实例。"""
    return MemoryManager(conversation_id=conversation_id)
