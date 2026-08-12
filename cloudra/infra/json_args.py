"""LLM 工具参数 JSON 的宽松解析与有限修复。"""

from __future__ import annotations

import json
import re
from typing import Any


def _snippet(raw: str, pos: int, radius: int = 60) -> str:
    start = max(0, pos - radius)
    end = min(len(raw), pos + radius)
    fragment = raw[start:end].replace("\n", "\\n")
    return f"...{fragment}..." if start > 0 or end < len(raw) else fragment


def try_repair_tool_arguments_json(raw: str) -> str | None:
    """尝试修复常见的工具参数 JSON 破损；失败返回 None。

    当前覆盖：嵌套对象少写 ``}``，表现为在 ``}, {`` 处报
    ``Expecting property name enclosed in double quotes``，且 ``{`` 比 ``}`` 多。
    Supervisor 大批量 mutate（payload 里再套 spec）极易踩中。
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        json.loads(raw, strict=False)
        return raw
    except json.JSONDecodeError:
        pass

    balance = raw.count("{") - raw.count("}")
    if balance <= 0:
        return None

    candidate = raw
    for _ in range(min(balance, 32)):
        try:
            json.loads(candidate, strict=False)
            return candidate
        except json.JSONDecodeError as exc:
            pos = exc.pos or 0
            # `, {` / `,{` 且期望属性名 → 前一个对象少了一个 `}`
            j = pos - 1
            while j >= 0 and candidate[j].isspace():
                j -= 1
            if j >= 0 and candidate[j] == "," and pos < len(candidate) and candidate[pos] == "{":
                candidate = candidate[:j] + "}" + candidate[j:]
                continue
            # 数组收尾 `}]}` 少一层
            m = re.search(r"\}\}\]\}?\s*$", candidate)
            if m and balance > 0:
                candidate = candidate[: m.start()] + "}" + candidate[m.start() :]
                continue
            break
    try:
        json.loads(candidate, strict=False)
        return candidate
    except json.JSONDecodeError:
        return None


def loads_tool_arguments(raw: Any) -> dict[str, Any]:
    """解析工具 ``function.arguments``；必要时做有限修复。

    返回 dict。非法时抛出 ``json.JSONDecodeError``，``msg`` 带片段提示。
    """
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    text = raw if isinstance(raw, str) else str(raw)
    if not text.strip():
        return {}
    try:
        data = json.loads(text, strict=False)
    except json.JSONDecodeError as exc:
        repaired = try_repair_tool_arguments_json(text)
        if repaired is None:
            hint = (
                f"{exc.msg} (at char {exc.pos}): {_snippet(text, exc.pos or 0)}。"
                "常见原因：嵌套 payload 少写了闭合 `}`，或单次 mutate 过大。"
                "请把 operations 拆成每批 1–3 个 add_node，payload 尽量扁平后重试。"
            )
            raise json.JSONDecodeError(hint, text, exc.pos or 0) from exc
        data = json.loads(repaired, strict=False)
    if not isinstance(data, dict):
        raise json.JSONDecodeError(
            "工具参数必须是 JSON object",
            text,
            0,
        )
    return data
