"""Plantool 的 per-agent 状态存储：按 conversation + agent 隔离的 JSON 文件。

工具实例在每次派发时重新构造（act_result 里 instantiate），所以状态不能挂在
实例上；落盘到 data_dir 下，既跨调用持久，也方便 TUI 后续读取展示。
"""

import json
import os
from typing import Any

from cloudra.config import get_config


def agent_store_path(subagent, filename: str) -> str:
    """返回当前 agent 的专属存储文件路径（自动建目录）。"""
    conv_id = getattr(subagent, "conversation_id", "default") or "default"
    agent_id = getattr(subagent, "id", "a-unknown") or "a-unknown"
    base = get_config().data_dir / "conversations" / conv_id / "plan"
    os.makedirs(base, exist_ok=True)
    return str(base / f"{agent_id}_{filename}")


def load_json(path: str, default: Any) -> Any:
    """读取 JSON 存储；文件不存在或损坏时返回 default（状态可丢，不能崩）。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data: Any) -> None:
    """原子写入 JSON 存储（临时文件 + rename，避免并发截断）。"""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
