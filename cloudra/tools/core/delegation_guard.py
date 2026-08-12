"""Coordinator 自行下场计算的轻量提示（软警告，不硬拦）。

背景：Coordinator 故意持有工具全集，方便简单任务自己做；但长上下文下
容易把「自己做」放大成默认路径，本该派给 dft / small_mol / md 的正式计算
也自己 submit_compute_job。这里只在成功提交时附一句提醒，放行执行。
"""

from __future__ import annotations

from typing import Any

_GUIDANCE = (
    "你是 Coordinator，正在自行 submit_compute_job。"
    "简单确认（秒级）可以自己做；正式或耗时的量化计算请优先派给 "
    "dft / small_mol / md 等子 Agent，并在派工时注明文件路径、目标与验收标准。"
    "本次提交已照常执行。"
)


def coordinator_self_compute_warning(agent: Any) -> str | None:
    """Coordinator 自行提交计算时返回提示文案；其它角色返回 None。"""
    if getattr(agent, "type", None) != "coordinator":
        return None
    return f"【提示：Coordinator 自行提交计算】{_GUIDANCE}"
