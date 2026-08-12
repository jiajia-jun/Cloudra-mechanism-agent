"""TUI 外层监督：进程隔离 runtime + UI 假死时只重启界面。

架构（默认）::

    父进程（watchdog）
      ├─ Process A: 本机 FastAPI runtime（SessionRunner / Coordinator）← 持久
      └─ Process B: Textual TUI（只渲染 + HTTP/IPC 控制）← 可杀

假死时只对 B 发 SIGQUIT 并重启；A 继续跑计算。``last_conversation_id``
由 B 落盘，重启后自动回到同一对话。

回退：
- ``CLOUDRA_TUI_INLINE=1``：Agent 与 TUI 同进程（旧行为）。
- ``CLOUDRA_TUI_NO_WATCHDOG=1``：不重启界面；仍默认拉起隔离 runtime。
- ``CLOUDRA_TUI_RUNTIME_URL``：复用已有健康 runtime，不另起进程。

心跳：
- ``tui.alive``：子进程守护线程（进程还活着）
- ``tui.ui``：Textual ``set_interval``（事件循环还能调度）

调参：``CLOUDRA_TUI_UI_STALE_S``（30）、``CLOUDRA_TUI_BOOT_GRACE_S``（45）、
``CLOUDRA_TUI_MAX_RESTARTS``（5）、``CLOUDRA_TUI_RUNTIME_BOOT_S``（30）。
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

_heartbeat_stop = threading.Event()


def _data_dir() -> Path:
    from cloudra.infra.config import get_config

    return Path(get_config().data_dir)


def alive_path(data_dir: Optional[Path] = None) -> Path:
    return (data_dir or _data_dir()) / "tui.alive"


def ui_path(data_dir: Optional[Path] = None) -> Path:
    return (data_dir or _data_dir()) / "tui.ui"


def touch_heartbeat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{time.time():.3f}\n", encoding="utf-8")


def read_heartbeat_age(path: Path, *, now: Optional[float] = None) -> Optional[float]:
    """返回心跳文件年龄（秒）；不存在或无法解析则 None。"""
    try:
        text = path.read_text(encoding="utf-8").strip()
        stamped = float(text.split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return (now if now is not None else time.time()) - stamped


def should_restart_for_ui_stall(
    *,
    ui_age: Optional[float],
    child_running: bool,
    past_boot_grace: bool,
    stale_s: float,
) -> bool:
    """纯函数：是否因 UI 心跳过期而重启子进程。"""
    if not child_running or not past_boot_grace:
        return False
    if ui_age is None:
        return True
    return ui_age > stale_s


def _process_heartbeat_loop(path: Path, interval: float = 1.0) -> None:
    while not _heartbeat_stop.is_set():
        try:
            touch_heartbeat(path)
        except Exception:
            pass
        time.sleep(interval)


def start_process_heartbeat(data_dir: Optional[Path] = None) -> Path:
    """子进程：启动与 asyncio 无关的进程心跳线程。"""
    global _heartbeat_stop
    _heartbeat_stop = threading.Event()
    path = alive_path(data_dir)
    touch_heartbeat(path)
    threading.Thread(
        target=_process_heartbeat_loop,
        args=(path,),
        name="cloudra-tui-alive",
        daemon=True,
    ).start()
    return path


def stop_process_heartbeat() -> None:
    _heartbeat_stop.set()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _watchdog_disabled() -> bool:
    return os.environ.get("CLOUDRA_TUI_NO_WATCHDOG", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def run_tui_child(yolo: bool | None = None) -> None:
    """子进程入口：真正的 Textual TUI（不跑 Agent，除非 INLINE）。"""
    if yolo is None:
        yolo = os.environ.get("CLOUDRA_TUI_YOLO", "").lower() in {"1", "true", "yes", "on"}
    from cloudra.tui.new.app import CloudraTextualApp
    from cloudra.tui.new.hard_escape import install_hard_escape

    data = _data_dir()
    start_process_heartbeat(data)
    install_hard_escape(data_dir=data)
    # 清掉上一轮残留的 UI 心跳，避免父进程用旧时间戳误判。
    try:
        ui_path(data).unlink(missing_ok=True)
    except Exception:
        pass
    CloudraTextualApp(yolo=yolo).run()


def _spawn_child(yolo: bool, *, runtime_url: Optional[str]) -> subprocess.Popen:
    env = os.environ.copy()
    env["CLOUDRA_TUI_CHILD"] = "1"
    env["CLOUDRA_TUI_YOLO"] = "1" if yolo else "0"
    # 子进程不再套一层 watchdog
    env["CLOUDRA_TUI_NO_WATCHDOG"] = "1"
    if runtime_url:
        env["CLOUDRA_TUI_RUNTIME_URL"] = runtime_url
    else:
        env.pop("CLOUDRA_TUI_RUNTIME_URL", None)
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from cloudra.tui.new.watchdog import run_tui_child; run_tui_child()",
        ],
        env=env,
        # 继承终端：Textual 需要真实 tty
        stdin=None,
        stdout=None,
        stderr=None,
        start_new_session=False,
    )


def _terminate_child(proc: subprocess.Popen, *, grace_s: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGQUIT)
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=grace_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
        proc.wait(timeout=3)
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
        pass


def _stderr_write(msg: str) -> None:
    stream = getattr(sys, "__stderr__", None) or sys.stderr
    try:
        stream.write(msg)
        stream.flush()
    except Exception:
        pass


def _is_sigquit_exit(returncode: int | None) -> bool:
    """子进程因 SIGQUIT（硬逃生 / 假死杀进程）退出。"""
    if returncode is None:
        return False
    if returncode == -signal.SIGQUIT:
        return True
    return returncode == 128 + int(signal.SIGQUIT)


def run_tui_supervised(yolo: bool = False) -> int:
    """父进程：可选拉起 runtime，监督 TUI；UI 假死只重启界面。"""
    if os.environ.get("CLOUDRA_TUI_CHILD") == "1":
        run_tui_child(yolo=yolo)
        return 0

    from cloudra.tui.new.runtime_proc import (
        ensure_local_runtime,
        inline_mode,
        stop_runtime,
    )

    data = _data_dir()
    runtime_proc = None
    runtime_url: Optional[str] = None
    # Ctrl+Q 正常退出时关掉 runtime；硬逃生 / 假死杀进程则保留计算进程。
    stop_runtime_on_exit = True
    if not inline_mode():
        try:
            runtime_proc, runtime_url = ensure_local_runtime(data)
            os.environ["CLOUDRA_TUI_RUNTIME_URL"] = runtime_url
            _stderr_write(f"[cloudra] Agent runtime: {runtime_url}\r\n")
        except Exception as exc:
            _stderr_write(
                f"[cloudra] 无法启动隔离 runtime（{exc}）。"
                "可设 CLOUDRA_TUI_INLINE=1 回退同进程。\r\n"
            )
            return 1

    try:
        if _watchdog_disabled():
            run_tui_child(yolo=yolo)
            return 0

        stale_s = _env_float("CLOUDRA_TUI_UI_STALE_S", 30.0)
        boot_grace_s = _env_float("CLOUDRA_TUI_BOOT_GRACE_S", 45.0)
        max_restarts = _env_int("CLOUDRA_TUI_MAX_RESTARTS", 5)
        ui = ui_path(data)
        restarts = 0

        while True:
            started = time.time()
            try:
                ui.unlink(missing_ok=True)
            except Exception:
                pass
            proc = _spawn_child(yolo, runtime_url=runtime_url)
            restarted = False
            while proc.poll() is None:
                time.sleep(1.0)
                age = read_heartbeat_age(ui)
                if should_restart_for_ui_stall(
                    ui_age=age,
                    child_running=True,
                    past_boot_grace=(time.time() - started) >= boot_grace_s,
                    stale_s=stale_s,
                ):
                    _stderr_write(
                        "\r\n[cloudra] TUI 事件循环无响应，正在保留对话与 Agent runtime "
                        "并重启界面…\r\n"
                    )
                    _terminate_child(proc)
                    restarts += 1
                    restarted = True
                    break
            if not restarted:
                code = int(proc.returncode or 0)
                if runtime_url and _is_sigquit_exit(proc.returncode):
                    stop_runtime_on_exit = False
                    _stderr_write(
                        f"[cloudra] TUI 已退出；Agent runtime 仍在运行：{runtime_url}\r\n"
                        "重新 cloudra 会自动复用（或 CLOUDRA_TUI_RUNTIME_URL）。"
                        "结束计算：kill $(cat data_dir/runtime.pid)\r\n"
                    )
                return code
            if restarts >= max_restarts:
                _stderr_write(
                    f"[cloudra] TUI 连续假死重启 {restarts} 次，放弃。"
                    "可 CLOUDRA_TUI_NO_WATCHDOG=1 禁用监督，"
                    "CLOUDRA_TUI_INLINE=1 回退同进程，"
                    "或 touch data_dir/tui.force_exit 强制退出子进程。\r\n"
                )
                return 1
            time.sleep(1.0)
    finally:
        if stop_runtime_on_exit:
            stop_runtime(runtime_proc, data)
