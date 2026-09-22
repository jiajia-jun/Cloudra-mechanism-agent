"""Token 计数器：压缩触发与截断的统一入口。

优先使用 ``tiktoken`` 做本地精确计数（不依赖 provider tokenize 端点）；
tiktoken 不可用时回退到字符启发式（偏保守，略高估，避免迟迟不压缩）。

压缩决策应调用 ``count_text`` / ``count_messages``，不要直接依赖启发式。
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

# OpenAI chat 消息格式开销（cl100k / o200k 通用近似）
_TOKENS_PER_MESSAGE = 4
_TOKENS_PER_NAME = 1
_REPLY_PRIMING_TOKENS = 2

_ENCODING_ASSETS = {
    "o200k_base": (
        "fb374d419588a4632f3f557e76b4b70aebbca790",
        "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
    ),
    "cl100k_base": (
        "9b5ad71b2ce5302211f9c61530b329a4922fc6a4",
        "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    ),
}


def _encoding_cache_dir() -> Path:
    configured = os.getenv("TIKTOKEN_CACHE_DIR")
    if configured is None:
        configured = os.getenv("DATA_GYM_CACHE_DIR")
    if configured is None:
        configured = os.path.join(tempfile.gettempdir(), "data-gym-cache")
    return Path(configured) if configured else Path("/__tiktoken_cache_disabled__")


def _require_cached_encoding_asset(name: str) -> None:
    """Keep token counting offline; tiktoken's downloader has no timeout."""
    asset = _ENCODING_ASSETS.get(name)
    if asset is None:
        raise FileNotFoundError(f"tiktoken encoding {name!r} is not cached")
    cache_key, expected_hash = asset
    path = _encoding_cache_dir() / cache_key
    if not path.is_file():
        raise FileNotFoundError(f"tiktoken encoding {name!r} is not cached at {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise FileNotFoundError(f"tiktoken encoding {name!r} cache is invalid at {path}")


@lru_cache(maxsize=8)
def _encoding_for(name: str):
    _require_cached_encoding_asset(name)
    import tiktoken

    return tiktoken.get_encoding(name)


@lru_cache(maxsize=32)
def _encoding_for_model(model: str):
    from tiktoken.model import encoding_name_for_model

    return _encoding_for(encoding_name_for_model(model))


class TokenEstimator:
    """精确优先的 token 计数器（tiktoken），附带启发式回退。"""

    _model: Optional[str] = None
    _encoding_name: str = "o200k_base"

    # ---- 启发式回退（仅 tiktoken 不可用时）----
    _CJK_RE = re.compile(r"[\u4e00-\u9fff]")
    _CJK_EXT_RE = re.compile(
        r"[\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af\u3100-\u312f]"
    )
    _ASCII_RE = re.compile(r"[a-zA-Z0-9]")

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
            except Exception:
                pass
        try:
            return _encoding_for(cls._encoding_name)
        except Exception:
            return _encoding_for("cl100k_base")

    # ------------------------------------------------------------------
    # 精确计数 API
    # ------------------------------------------------------------------

    @classmethod
    def count_text(cls, text: Any) -> int:
        """精确计数单段文本 token（tiktoken）；失败则启发式。"""
        if text is None:
            return 0
        if not isinstance(text, str):
            text = str(text)
        if not text:
            return 0
        try:
            return len(cls._get_encoding().encode(text, disallowed_special=()))
        except Exception:
            return cls._estimate_text_heuristic(text)

    @classmethod
    def truncate_to_tokens(cls, text: str, max_tokens: int) -> str:
        """把文本截到不超过 ``max_tokens``（优先按 tiktoken token 边界）。"""
        if max_tokens <= 0 or not text:
            return ""
        try:
            enc = cls._get_encoding()
            tokens = enc.encode(text, disallowed_special=())
            if len(tokens) <= max_tokens:
                return text
            return enc.decode(tokens[:max_tokens])
        except Exception:
            return cls._truncate_heuristic(text, max_tokens)

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

    # ------------------------------------------------------------------
    # 启发式回退
    # ------------------------------------------------------------------

    @classmethod
    def _estimate_text_heuristic(cls, text: str) -> int:
        cjk_count = len(cls._CJK_RE.findall(text))
        cjk_ext_count = len(cls._CJK_EXT_RE.findall(text))
        ascii_count = len(cls._ASCII_RE.findall(text))
        other_count = max(0, len(text) - cjk_count - cjk_ext_count - ascii_count)
        total = (
            cjk_count / 1.0
            + cjk_ext_count / 1.5
            + ascii_count / 4.0
            + other_count / 4.0
        )
        return max(1, int(total))

    @classmethod
    def _truncate_heuristic(cls, text: str, max_tokens: int) -> str:
        if cls._estimate_text_heuristic(text) <= max_tokens:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if cls._estimate_text_heuristic(text[:mid]) <= max_tokens:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo]


def _stable_json(obj: Any) -> str:
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(obj)
