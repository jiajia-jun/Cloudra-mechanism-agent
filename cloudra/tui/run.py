"""Cloudra TUI 统一入口。

默认启动基于 Textual 的全屏 TUI；设置环境变量 ``CLOUDRA_LEGACY_TUI=1``
或传入 ``legacy=True`` 可回退到旧版 prompt_toolkit TUI。
"""

from __future__ import annotations

import os


def run_tui(yolo: bool = False, legacy: bool = False) -> None:
    """启动 Cloudra 交互式 TUI。"""
    if legacy or os.getenv("CLOUDRA_LEGACY_TUI") == "1":
        from cloudra.tui.legacy_app import CloudraTUI

        CloudraTUI(yolo=yolo).run()
        return

    try:
        from cloudra.tui.new.app import run_tui as _run_textual
    except ImportError as exc:
        raise RuntimeError(
            "无法启动新 TUI，请确保已安装 textual：pip install textual"
        ) from exc

    _run_textual(yolo=yolo)
