"""轻量级 Token 估算器。

不依赖 tiktoken / transformers 等外部库，基于启发式规则对文本和
OpenAI 风格的多模态消息进行快速 Token 估算，用于上下文压缩决策。
"""

import re
from typing import Any


class TokenEstimator:
    """基于字符分布的快速 token 估算器。

    估算规则（综合常见 BPE tokenizer 的统计特征）：
    - 英文/ASCII 单词：约 1 token / 4 个字符
    - 中文/CJK 统一表意文字：约 1 token / 1.5 个字符
    - 韩文/日文假名等：约 1 token / 2 个字符
    - 数字、标点和空格：约 1 token / 4 个字符
    - base64 图片：图片在消息中通常以 data URL 形式出现，估算为
      ``len(base64_string) * 0.75 * 0.25``，即原始字节数约 1/3 的 token
      （视觉模型对图片的 token 计算大致在此范围）。

    该估算器仅用于上下文长度管理，不替代模型计费 Token。
    """

    # CJK 统一表意文字范围
    _CJK_RE = re.compile(r"[\u4e00-\u9fff]")
    # 韩文、日文假名、片假名等
    _CJK_EXT_RE = re.compile(
        r"[\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af\u3100-\u312f]"
    )
    # ASCII 字母数字
    _ASCII_RE = re.compile(r"[a-zA-Z0-9]")

    @classmethod
    def estimate_text(cls, text: Any) -> int:
        """估算任意文本字符串的 token 数。"""
        if text is None:
            return 0
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return 0

        cjk_count = len(cls._CJK_RE.findall(text))
        cjk_ext_count = len(cls._CJK_EXT_RE.findall(text))
        ascii_count = len(cls._ASCII_RE.findall(text))
        other_count = max(0, len(text) - cjk_count - cjk_ext_count - ascii_count)

        # 其他字符里大部分是标点和空格，粗略按 1 token / 4 字符
        other_tokens = other_count / 4.0

        total = (
            cjk_count / 1.5
            + cjk_ext_count / 2.0
            + ascii_count / 4.0
            + other_tokens
        )
        return max(1, int(total))

    @classmethod
    def estimate_image_url(cls, url: str) -> int:
        """估算一张图片（data URL 或 http URL）的 token 数。"""
        if not url:
            return 0
        # http 图片不会被 LLM 实际消费，token 很低
        if not url.startswith("data:"):
            return cls.estimate_text(url)

        # data:image/xxx;base64,xxxx
        try:
            _, b64_part = url.split(",", 1)
        except ValueError:
            return cls.estimate_text(url)

        # base64 字符串长度 * 0.75 为原始字节数，视觉模型 token 约为原始字节的 1/3
        return max(1, int(len(b64_part) * 0.75 * 0.25))

    @classmethod
    def estimate_content_part(cls, part: dict) -> int:
        """估算消息 content 列表中单个 part 的 token 数。"""
        part_type = part.get("type")
        if part_type == "text":
            return cls.estimate_text(part.get("text", ""))
        if part_type == "image_url":
            image_url = part.get("image_url", {})
            url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
            return cls.estimate_image_url(url)
        # tool/function 等其他类型 fallback
        return cls.estimate_text(str(part))

    @classmethod
    def estimate_message(cls, message: dict) -> int:
        """估算单条 OpenAI 风格消息的 token 数（含格式开销）。"""
        content = message.get("content")
        tokens = 0

        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    tokens += cls.estimate_content_part(part)
                else:
                    tokens += cls.estimate_text(part)
        elif isinstance(content, dict):
            tokens += cls.estimate_content_part(content)
        else:
            tokens += cls.estimate_text(content)

        # role / name / tool_call_id 等字段的格式开销
        for key in ("role", "name", "tool_call_id"):
            if key in message:
                tokens += cls.estimate_text(message[key])

        # tool_calls 结构
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                tokens += cls.estimate_text(str(tc))

        # 每条消息预留 4 token 的格式开销（role 分隔等）
        return max(1, tokens + 4)

    @classmethod
    def estimate_messages(cls, messages: list[dict]) -> int:
        """估算消息列表的总 token 数。"""
        if not messages:
            return 0
        total = sum(cls.estimate_message(m) for m in messages)
        # 整个消息列表预留 2 token 开销
        return total + 2
