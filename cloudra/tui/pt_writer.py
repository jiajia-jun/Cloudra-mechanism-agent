"""TUI 的 rich Console 输出通道。

prompt_toolkit 的 patch_stdout/Vt100_Output.write 会把 ESC 转义成 '?'，
直接把 rich 的 ANSI 输出写进 patch_stdout 会丢失全部颜色。
这里把 rich 渲染好的 ANSI 文本交给 prompt_toolkit 的 print_formatted_text
（经 ANSI formatted text 走正常渲染管线），颜色完整且不会冲掉底部输入框。

注意：print_formatted_text 只能在 prompt 应用存活期间调用；应用退出后
（例如 TUI 收尾阶段仍有事件到达）必须回退到裸 stdout，否则会走上
prompt_toolkit 内部的"等待回车"异常处理路径，在管道输入下永久阻塞。
"""

from __future__ import annotations

import sys

from prompt_toolkit.application.current import get_app_or_none
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text


def _app_running() -> bool:
    app = get_app_or_none()
    return bool(app is not None and getattr(app, "is_running", False))


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
        if _app_running():
            if data.endswith("\n"):
                # 完整行：去掉末尾换行，由 print_formatted_text 自己补
                print_formatted_text(ANSI(data[:-1]))
            else:
                print_formatted_text(ANSI(data), end="", flush=True)
        else:
            # 应用未运行（启动前/退出后）：绕过 patch_stdout 代理直写真实终端，
            # 此时没有输入框需要保护，颜色也能保留。
            target = sys.__stdout__ or sys.stdout
            target.write(data)
            target.flush()
        return len(data)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return True
