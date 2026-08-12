"""Cloudra Textual 全屏 TUI 主应用。"""

from textual.app import App
from textual.binding import Binding
from textual.theme import Theme

from cloudra.base.log_class import Log
from cloudra.tui.new.hard_escape import install_hard_escape
from cloudra.tui.new.screens.main_screen import MainScreen
from cloudra.tui.new.watchdog import touch_heartbeat, ui_path

# 主题：绿色主色 + 黄色辅色
_CLOUDRA_THEME = Theme(
    name="cloudra",
    dark=True,
    primary="#4ade80",
    secondary="#facc15",
    accent="#a3e635",
    success="#22c55e",
    warning="#eab308",
    variables={
        # 缺省时 Textual 会把前景/背景都回退成 primary，选中的文本直接隐形。
        # 白底黑字，对比最直白。
        "screen-selection-background": "#ffffff",
        "screen-selection-foreground": "#000000",
    },
)


class CloudraTextualApp(App):
    """基于 Textual 的 Cloudra 全屏终端界面。"""

    CSS_PATH = "styles.tcss"
    TITLE = "Cloudra Research System"
    # priority=True：即使焦点在 TextArea 也能触发，避免 q 被吞成输入字符。
    BINDINGS = [
        Binding("ctrl+q", "soft_quit", "退出", show=True, priority=True),
    ]

    def __init__(self, yolo: bool = False) -> None:
        super().__init__()
        self.yolo = yolo
        self.register_theme(_CLOUDRA_THEME)
        self.theme = "cloudra"
        self._ui_heartbeat_path = ui_path()

    def on_mount(self) -> None:
        # reAct 的 Log 会绕过 Textual 直接 print 到终端，毁掉全屏渲染；
        # 与 legacy TUI 一样关掉终端输出（日志文件写入不受影响）。
        Log.terminal_output = False
        install_hard_escape()
        # UI 心跳：只有事件循环还能调度时才会刷新；父 watchdog 据此判断假死。
        try:
            touch_heartbeat(self._ui_heartbeat_path)
        except Exception:
            pass
        self.set_interval(1.0, self._beat_ui_heartbeat)
        self.push_screen(MainScreen(yolo=self.yolo))

    def _beat_ui_heartbeat(self) -> None:
        try:
            touch_heartbeat(self._ui_heartbeat_path)
        except Exception:
            pass

    def on_unmount(self) -> None:
        Log.terminal_output = True

    def action_soft_quit(self) -> None:
        """事件循环仍活着时的正常退出；卡死时请用 Ctrl+\\ 或 touch tui.force_exit。"""
        self.exit()


def run_tui(yolo: bool = False) -> None:
    """启动 TUI；默认由外层 watchdog 监督，UI 假死自动重启并保留对话。"""
    from cloudra.tui.new.watchdog import run_tui_supervised

    raise SystemExit(run_tui_supervised(yolo=yolo))
