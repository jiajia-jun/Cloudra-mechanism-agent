"""TUI 硬逃生：事件循环被同步代码卡死时仍能退回 shell。

背景：Textual TUI 与 Coordinator 共用同一 asyncio 循环。CREST/xTB/PySCF 等
若在 loop 里同步跑，界面假死；Esc / q / Ctrl+C（复制）全部失效，因为键事件
进不了 loop。

本模块提供两类**不依赖 asyncio**的逃生通道：

1. ``SIGQUIT``（终端 Ctrl+\\，或另一终端 ``kill -QUIT <pid>``）——OS 信号在
   可中断的 syscall 返回后会进入 Python handler，即使 UI loop 已停。
2. 守护线程轮询 ``data_dir/tui.force_exit``——在另一终端 ``touch`` 该文件即可，
   覆盖 WSL/远程下 Ctrl+\\ 被吞的情况。

两者都 ``os._exit``：不跑 atexit/finally（可能同样卡住），但会尽力写回
``last_conversation_id`` 并退出备用屏，以便下次 ``cloudra`` 回到同一对话。
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

_installed = False
_watcher_stop = threading.Event()
_force_exit_path: Optional[Path] = None


def force_exit_path(data_dir: Optional[Path] = None) -> Path:
    """返回硬逃生触发文件路径。"""
    if data_dir is None:
        from cloudra.infra.config import get_config

        data_dir = Path(get_config().data_dir)
    return Path(data_dir) / "tui.force_exit"


def _restore_terminal() -> None:
    stream = getattr(sys, "__stdout__", None) or sys.stdout
    try:
        # 退出备用屏、显示光标、复位 SGR；Textual 卡死时自己来不及清理。
        stream.write("\033[?1049l\033[?25h\033[0m\r\n")
        stream.write(
            "Cloudra TUI 已强制退出（对话已保留；隔离模式下 Agent runtime 继续运行）。"
            "重新运行 cloudra 会回到同一对话；若由 watchdog 拉起则会自动重启界面。\r\n"
            "若仍异常：另一终端可 touch data_dir/tui.force_exit"
            " 或 kill -QUIT <pid>。\r\n"
        )
        stream.flush()
    except Exception:
        pass


def _persist_conversation() -> None:
    try:
        from cloudra.infra.config import get_config

        get_config().save()
    except Exception:
        pass


def emergency_exit(signum: Optional[int] = None, _frame=None) -> None:
    """尽力落盘后立刻结束进程。可从信号或守护线程调用。"""
    _watcher_stop.set()
    try:
        if _force_exit_path is not None:
            _force_exit_path.unlink(missing_ok=True)
    except Exception:
        pass
    _persist_conversation()
    _restore_terminal()
    code = 128 + int(signum) if signum else 130
    os._exit(code)


def _watch_force_exit_file(path: Path, poll_s: float = 0.5) -> None:
    while not _watcher_stop.is_set():
        try:
            if path.exists():
                emergency_exit()
        except Exception:
            pass
        time.sleep(poll_s)


def install_hard_escape(*, data_dir: Optional[Path] = None) -> Path:
    """安装 SIGQUIT + 文件触发守护线程。幂等；返回 force_exit 文件路径。"""
    global _installed, _force_exit_path
    path = force_exit_path(data_dir)
    _force_exit_path = path
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass

    if _installed:
        return path
    _installed = True

    try:
        signal.signal(signal.SIGQUIT, emergency_exit)
    except (ValueError, OSError, AttributeError):
        # 非主线程或平台无 SIGQUIT 时跳过；文件通道仍可用。
        pass

    watcher = threading.Thread(
        target=_watch_force_exit_file,
        args=(path,),
        name="cloudra-tui-hard-escape",
        daemon=True,
    )
    watcher.start()
    return path


def uninstall_hard_escape_for_tests() -> None:
    """仅测试用：停止轮询并复位安装标记。"""
    global _installed, _force_exit_path
    _watcher_stop.set()
    _installed = False
    _force_exit_path = None
    _watcher_stop.clear()
