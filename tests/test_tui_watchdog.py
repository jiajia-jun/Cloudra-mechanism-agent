"""TUI watchdog：UI 心跳过期判定与路径约定。"""

from __future__ import annotations

import time
from pathlib import Path

from cloudra.tui.new.watchdog import (
    read_heartbeat_age,
    should_restart_for_ui_stall,
    touch_heartbeat,
    ui_path,
)

# 假死重启只针对 TUI 子进程；runtime 由 runtime_proc 单独管理（见 test_tui_isolation）。


def test_should_restart_only_after_grace_and_stall():
    assert not should_restart_for_ui_stall(
        ui_age=100, child_running=True, past_boot_grace=False, stale_s=30
    )
    assert not should_restart_for_ui_stall(
        ui_age=10, child_running=True, past_boot_grace=True, stale_s=30
    )
    assert should_restart_for_ui_stall(
        ui_age=31, child_running=True, past_boot_grace=True, stale_s=30
    )
    assert should_restart_for_ui_stall(
        ui_age=None, child_running=True, past_boot_grace=True, stale_s=30
    )
    assert not should_restart_for_ui_stall(
        ui_age=100, child_running=False, past_boot_grace=True, stale_s=30
    )


def test_heartbeat_age_roundtrip(tmp_path: Path):
    path = ui_path(tmp_path)
    now = time.time()
    touch_heartbeat(path)
    # 写入的是当前时间；年龄应接近 0
    age = read_heartbeat_age(path, now=now + 0.01)
    assert age is not None
    assert 0 <= age < 2.0
    assert read_heartbeat_age(tmp_path / "missing") is None
