"""Plantool 的 per-agent 状态存储：按 conversation + agent 隔离的 JSON 文件。

工具实例在每次派发时重新构造（act_result 里 instantiate），所以状态不能挂在
实例上；落盘到 data_dir 下，既跨调用持久，也方便 TUI 后续读取展示。
"""

import json
import os
from typing import Any

from cloudra.config import get_config
from cloudra.fs_utils import atomic_write_json


def agent_store_path(subagent, filename: str) -> str:
    """返回当前 agent 的专属存储文件路径（自动建目录）。

    键控规则：conversation_id + agent_id；若 agent 带 session_id（子 Agent
    派发时由 launcher/executor 注入），并入键中——同角色并行实例（swarm）
    各自持有独立的 todos/goal 文件，互不覆盖。无 session_id（Coordinator
    主 agent、旧行为）路径与旧版完全一致。
    """
    conv_id = getattr(subagent, "conversation_id", "default") or "default"
    agent_id = getattr(subagent, "id", "a-unknown") or "a-unknown"
    session_id = getattr(subagent, "session_id", None)
    key = agent_id
    if session_id:
        # session_id 内部生成（"{agent_id}_task{N}"），仍兜底去掉路径分隔符。
        safe_session = str(session_id).replace("/", "_").replace("\\", "_")
        key = f"{agent_id}_{safe_session}"
    base = get_config().data_dir / "conversations" / conv_id / "plan"
    os.makedirs(base, exist_ok=True)
    return str(base / f"{key}_{filename}")


def load_json(path: str, default: Any) -> Any:
    """读取 JSON 存储；文件不存在或损坏时返回 default（状态可丢，不能崩）。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: str, data: Any) -> None:
    """原子写入 JSON 存储（临时文件 + rename，避免并发截断）。"""
    atomic_write_json(path, data, indent=2)
