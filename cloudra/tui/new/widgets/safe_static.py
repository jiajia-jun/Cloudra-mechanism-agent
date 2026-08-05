"""防御性 Static：内容含未转义 console markup 时自动降级为纯文本。

背景
----
Textual 的 ``Static`` 默认按 Rich console markup 解析内容。当内容是来源不可信、
可能含 ``[``、``"`` 等字符的文本（工具参数、命令输出、对话消息）时，未转义的
方括号会触发 ``MarkupError``，并且发生在布局/更新阶段——直接把整个 TUI 打崩。

本模块提供 :class:`SafeStatic`：即使某个调用点忘记设置 ``markup=False``，
渲染失败也会自动降级为纯文本，而不是让应用崩溃（defense-in-depth）。
``visual`` 属性与 ``update()``/``content`` 赋值两条路径都覆盖。
"""

from __future__ import annotations

from typing import Any

from rich.errors import MarkupError
from textual.visual import Visual, VisualType
from textual.widgets import Static


class SafeStatic(Static):
    """Static 的安全版：markup 解析失败时回退为纯文本渲染。

    用法与 :class:`textual.widgets.Static` 完全一致；对不可信内容仍建议显式
    传 ``markup=False``（快路径，不尝试解析），本类的回退用于兜底。
    """

    @property
    def visual(self) -> Visual:
        try:
            return super().visual
        except MarkupError:
            self._degrade()
            return super().visual

    @property
    def content(self) -> VisualType:
        return super().content

    @content.setter
    def content(self, content: VisualType) -> None:
        try:
            super().content = content
        except MarkupError:
            self._degrade()
            super().content = content

    def _degrade(self) -> None:
        """永久降级为纯文本渲染，避免后续每次渲染都重复解析失败。"""
        self._render_markup = False
