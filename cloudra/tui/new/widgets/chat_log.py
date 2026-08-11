"""Backward-compatible import surface for the chat transcript widget.

The legacy Widget-tree implementation has been replaced by the virtualized
``ChatLog`` in ``virtual_chat_log``.  Importing from this module keeps existing
screens and tests working without changes.
"""

from __future__ import annotations

from cloudra.infra.tool_presentation import format_tool_payload
from cloudra.tui.new.widgets.virtual_chat_log import ChatLog

_format_tool_payload = format_tool_payload
__all__ = ["ChatLog", "_format_tool_payload"]
