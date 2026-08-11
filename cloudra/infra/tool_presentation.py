"""Safe, compact presentation of structured tool payloads in user interfaces."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

_UNICODE_ESCAPE_RUN = re.compile(r"(?:\\u[0-9a-fA-F]{4})+")
_SECRET_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|authorization|credential|cookie)",
    re.IGNORECASE,
)
_RESULT_KEYS = ("message", "result", "output", "content", "error", "detail")


def _decode_unicode_escapes(text: str) -> str:
    """Decode only explicit ``\\uXXXX`` runs without corrupting real UTF-8."""

    def replace(match: re.Match[str]) -> str:
        try:
            return json.loads(f'"{match.group(0)}"')
        except (json.JSONDecodeError, UnicodeDecodeError):
            return match.group(0)

    return _UNICODE_ESCAPE_RUN.sub(replace, text)


def _parse_nested(value: Any, *, depth: int = 0) -> Any:
    if depth >= 3 or not isinstance(value, str):
        return value
    text = _decode_unicode_escapes(value.strip())
    if not text or text[0] not in "[{\"'":
        return text
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text
    return _parse_nested(parsed, depth=depth + 1)


def _clean(value: Any, *, depth: int = 0) -> Any:
    value = _parse_nested(value)
    if isinstance(value, str):
        return _decode_unicode_escapes(value)
    if depth >= 4:
        return "…"
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key)
            cleaned[key_text] = "[已隐藏]" if _SECRET_KEY.search(key_text) else _clean(
                item, depth=depth + 1
            )
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_clean(item, depth=depth + 1) for item in value]
    return value


def _flatten(value: Any, *, indent: int = 0, max_items: int = 10) -> list[str]:
    prefix = "  " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        items = list(value.items())
        for key, item in items[:max_items]:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}{key}:")
                lines.extend(_flatten(item, indent=indent + 1, max_items=max_items))
            else:
                lines.append(f"{prefix}{key}: {item}")
        if len(items) > max_items:
            lines.append(f"{prefix}… 另有 {len(items) - max_items} 项")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value[:max_items]:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{prefix}-")
                lines.extend(_flatten(item, indent=indent + 1, max_items=max_items))
            else:
                lines.append(f"{prefix}- {item}")
        if len(value) > max_items:
            lines.append(f"{prefix}… 另有 {len(value) - max_items} 项")
        return lines
    return [f"{prefix}{value}"]


def format_tool_payload(value: Any, *, is_result: bool = False, max_chars: int = 2400) -> str:
    """Return a readable, redacted and bounded tool payload for UI display."""
    cleaned = _clean(value)
    if is_result and isinstance(cleaned, dict):
        primary_key = next((key for key in _RESULT_KEYS if key in cleaned), None)
        if primary_key is not None:
            primary = cleaned[primary_key]
            metadata = {key: item for key, item in cleaned.items() if key != primary_key}
            lines = _flatten(primary)
            if metadata:
                lines.extend(("——", *_flatten(metadata)))
        else:
            lines = _flatten(cleaned)
    else:
        lines = _flatten(cleaned)
    rendered = "\n".join(lines).strip()
    if len(rendered) > max_chars:
        rendered = rendered[:max_chars].rstrip() + "\n… 结果预览已截断"
    return rendered
