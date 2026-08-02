"""Synchronous clipboard helpers for the TUI.

Copying is invoked from async event handlers via ``asyncio.to_thread`` so the
Textual event loop is not blocked by subprocess startup.
"""

from __future__ import annotations

import shutil
import subprocess


_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("xclip", "-selection", "clipboard"),
    ("xsel", "--clipboard", "--input"),
    ("pbcopy",),
    ("clip",),
)


def copy_to_clipboard(text: str) -> None:
    """Copy ``text`` to the system clipboard using the first available tool."""
    for command in _COMMANDS:
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=text, text=True, check=True)
            return
        except (FileNotFoundError, subprocess.CalledProcessError, OSError):
            continue
    raise RuntimeError("未找到可用的剪贴板工具（xclip/xsel/pbcopy/clip）")
