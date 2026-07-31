"""Cloudra Textual 全屏 TUI 主应用。"""

from textual.app import App
from textual.theme import Theme

from cloudra.log_class import Log
from cloudra.tui.new.screens.main_screen import MainScreen

# 主题：绿色主色 + 黄色辅色
_CLOUDRA_THEME = Theme(
    name="cloudra",
    dark=True,
    primary="#4ade80",
    secondary="#facc15",
    accent="#a3e635",
    success="#22c55e",
    warning="#eab308",
)


class CloudraTextualApp(App):
    """基于 Textual 的 Cloudra 全屏终端界面。"""

    CSS_PATH = "styles.tcss"
    TITLE = "Cloudra Research System"

    def __init__(self, yolo: bool = False) -> None:
        super().__init__()
        self.yolo = yolo
        self.register_theme(_CLOUDRA_THEME)
        self.theme = "cloudra"

    def on_mount(self) -> None:
        # reAct 的 Log 会绕过 Textual 直接 print 到终端，毁掉全屏渲染；
        # 与 legacy TUI 一样关掉终端输出（日志文件写入不受影响）。
        Log.terminal_output = False
        self.push_screen(MainScreen(yolo=self.yolo))

    def on_unmount(self) -> None:
        Log.terminal_output = True


def run_tui(yolo: bool = False) -> None:
    CloudraTextualApp(yolo=yolo).run()
