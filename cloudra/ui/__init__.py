"""Cloudra 原生 GUI（Flet）入口。"""

from __future__ import annotations

__all__ = ["run_gui"]


def run_gui() -> None:
    """启动 Flet GUI；若未安装 flet 则给出友好提示。"""
    try:
        import flet as ft
    except ImportError as exc:
        raise SystemExit(
            "未安装 GUI 依赖。请运行：\n"
            "  pip install cloudra[gui]\n"
            "或：\n"
            "  pip install flet"
        ) from exc

    from cloudra.ui.app import main

    ft.app(target=main)
