"""TUI 的 rich Console 输出通道。

prompt_toolkit 的 patch_stdout/Vt100_Output.write 会把 ESC 转义成 '?'，
直接把 rich 的 ANSI 输出写进 patch_stdout 会丢失全部颜色。
这里把 rich 渲染好的 ANSI 文本交给 prompt_toolkit 的 print_formatted_text
（经 ANSI formatted text 走正常渲染管线），颜色完整且不会冲掉底部输入框。
"""

from __future__ import annotations

from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text


class PromptToolkitWriter:
    """作为 rich ``Console(file=...)`` 的文件对象，按行转发到 prompt_toolkit。

    - 带换行的完整行立即渲染；
    - 无换行的流式片段（console.print(..., end="")）直接以 end="" 渲染，
      保证 token 流式观感；
    - 仅供事件循环内的渲染器/TUI 主类使用（线程 prints 仍走 patch_stdout）。
    """

    def write(self, data: str) -> int:
        if not data:
            return 0
        if data.endswith("\n"):
            # 完整行：去掉末尾换行，由 print_formatted_text 自己补
            print_formatted_text(ANSI(data[:-1]))
        else:
            print_formatted_text(ANSI(data), end="", flush=True)
        return len(data)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return True
