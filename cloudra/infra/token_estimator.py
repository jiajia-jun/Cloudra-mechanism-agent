"""Token 计数器：压缩触发与截断的统一入口。

使用随包提供的 OpenAI o200k_base 词表离线计数，不依赖临时缓存或下载。
它是跨供应商的本地估计；实际请求用量仍应以供应商返回值为准。

压缩决策统一调用 ``count_text`` / ``count_messages``。
"""

from __future__ import annotations

import base64
import gzip
import hashlib
from functools import lru_cache
from importlib.resources import files
from typing import Any, Optional

# OpenAI chat 消息格式开销（cl100k / o200k 通用近似）
_TOKENS_PER_MESSAGE = 4
_TOKENS_PER_NAME = 1
_REPLY_PRIMING_TOKENS = 2

_O200K_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
# The tokenizer pattern and special tokens match openai/tiktoken's
# tiktoken_ext/openai_public.py. This pattern tokenizes text; it does not
# validate Agent responses or tool inputs.
_O200K_PATTERN = "|".join(
    [
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"\p{N}{1,3}",
        r" ?[^\s\p{L}\p{N}]+[\r\n/]*",
        r"\s*[\r\n]+",
        r"\s+(?!\S)",
        r"\s+",
    ]
)


@lru_cache(maxsize=8)
def _encoding_for(name: str):
    if name != "o200k_base":
        raise KeyError(name)
    import tiktoken

    resource = files("cloudra.infra").joinpath("token_data", "o200k_base.tiktoken.gz")
    contents = gzip.decompress(resource.read_bytes())
    if hashlib.sha256(contents).hexdigest() != _O200K_SHA256:
        raise ValueError("bundled o200k_base tokenizer has an invalid SHA-256")
    ranks = {
        base64.b64decode(token): int(rank)
        for token, rank in (line.split() for line in contents.splitlines() if line)
    }
    return tiktoken.Encoding(
        name=name,
        pat_str=_O200K_PATTERN,
        mergeable_ranks=ranks,
        special_tokens={"<|endoftext|>": 199999, "<|endofprompt|>": 200018},
    )


@lru_cache(maxsize=32)
def _encoding_for_model(model: str):
    from tiktoken.model import encoding_name_for_model

    return _encoding_for(encoding_name_for_model(model))


class TokenEstimator:
    """使用随包词表的离线 token 计数器。"""

    _model: Optional[str] = None
    _encoding_name: str = "o200k_base"

    @classmethod
    def configure(
        cls,
        model: Optional[str] = None,
        encoding: Optional[str] = None,
    ) -> None:
        """配置默认模型 / encoding；压缩前可由 Agent 按当前 endpoint 设置。"""
        if model is not None:
            cls._model = model or None
            _encoding_for_model.cache_clear()
        if encoding is not None:
            cls._encoding_name = encoding
            _encoding_for.cache_clear()

    @classmethod
    def _get_encoding(cls):
        if cls._model:
            try:
                return _encoding_for_model(cls._model)
            except KeyError:
                pass
        return _encoding_for(cls._encoding_name)

    # ------------------------------------------------------------------
    # 精确计数 API
    # ------------------------------------------------------------------

    @classmethod
    def count_text(cls, text: Any) -> int:
        """按随包词表计数；词表缺失或损坏时明确报错。"""
        if text is None:
            return 0
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return 0
        return len(cls._get_encoding().encode(text, disallowed_special=()))

    @classmethod
    def truncate_to_tokens(cls, text: str, max_tokens: int) -> str:
        """把文本按词表边界截到不超过 ``max_tokens``。"""
        if max_tokens <= 0 or not text:
            return ""
        enc = cls._get_encoding()
        tokens = enc.encode(text, disallowed_special=())
        if len(tokens) <= max_tokens:
            return text
        return enc.decode(tokens[:max_tokens])

    @classmethod
    def count_content_part(cls, part: dict) -> int:
        part_type = part.get("type")
        if part_type == "text":
            return cls.count_text(part.get("text", ""))
        if part_type == "image_url":
            image_url = part.get("image_url", {})
            url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
            return cls.count_image_url(url)
        return cls.count_text(str(part))

    @classmethod
    def count_image_url(cls, url: str) -> int:
        if not url:
            return 0
        if not url.startswith("data:"):
            return cls.count_text(url)
        try:
            _, b64_part = url.split(",", 1)
        except ValueError:
            return cls.count_text(url)
        # 视觉模型对图片的 token 计算大致：原始字节约 1/3
        return max(1, int(len(b64_part) * 0.75 * 0.25))

    @classmethod
    def count_message(cls, message: dict) -> int:
        """精确计数单条 OpenAI 风格消息（含格式开销）。"""
        tokens = _TOKENS_PER_MESSAGE
        content = message.get("content")

        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    tokens += cls.count_content_part(part)
                else:
                    tokens += cls.count_text(part)
        elif isinstance(content, dict):
            tokens += cls.count_content_part(content)
        elif content is not None:
            tokens += cls.count_text(content)

        for key in ("role", "name", "tool_call_id"):
            if key in message and message[key] is not None:
                tokens += cls.count_text(message[key])
                if key == "name":
                    tokens += _TOKENS_PER_NAME

        if "tool_calls" in message and message["tool_calls"]:
            for tc in message["tool_calls"]:
                tokens += cls.count_text(
                    tc if isinstance(tc, str) else _stable_json(tc)
                )

        if "reasoning_content" in message and message["reasoning_content"]:
            tokens += cls.count_text(message["reasoning_content"])

        return max(1, tokens)

    @classmethod
    def count_messages(cls, messages: list[dict]) -> int:
        """精确计数消息列表总 token。"""
        if not messages:
            return 0
        return sum(cls.count_message(m) for m in messages) + _REPLY_PRIMING_TOKENS

    # ------------------------------------------------------------------
    # 兼容旧调用名（内部改为精确计数）
    # ------------------------------------------------------------------

    @classmethod
    def estimate_text(cls, text: Any) -> int:
        return cls.count_text(text)

    @classmethod
    def estimate_image_url(cls, url: str) -> int:
        return cls.count_image_url(url)

    @classmethod
    def estimate_content_part(cls, part: dict) -> int:
        return cls.count_content_part(part)

    @classmethod
    def estimate_message(cls, message: dict) -> int:
        return cls.count_message(message)

    @classmethod
    def estimate_messages(cls, messages: list[dict]) -> int:
        return cls.count_messages(messages)


def _stable_json(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(obj)
