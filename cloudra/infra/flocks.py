"""fcntl.flock 原语：执行面唯一的进程存活/互斥判定手段（POSIX only）。

设计约定（AGENTS.md 铁律）：执行面判断"进程是否还活着"一律用锁探测，
外部对账不依赖存盘 PID 或 ps//proc 文本。持锁的原执行 owner 可核对自己新建
session 的成员，用于取消和确认其计算家族已退出；不能据此猜杀其它进程。
进程死亡（含 kill -9）时内核自动放锁，因此锁探测不存在 PID 复用误判。
guard/calculator/调度器单实例共用本模块。
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager


def try_acquire_lock(path: str) -> int | None:
    """非阻塞抢排他 flock。

    成功返回持有锁的 fd——调用方必须保持该 fd 打开以持锁（进程退出即释放）；
    锁被其他进程持有时返回 None。
    """
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def is_lock_held(path: str) -> bool:
    """探测锁是否正被其他进程持有（抢到立即释放，只读不写语义）。"""
    fd = try_acquire_lock(path)
    if fd is None:
        return True
    os.close(fd)
    return False


@contextmanager
def locked(path: str) -> Iterator[int]:
    """阻塞式排他 flock 上下文：跨进程/线程串行化临界区（如配置的读-改-写）。

    与 try_acquire_lock 的非阻塞探测不同，本原语用于必须等到锁的写路径。
    进程死亡（含 kill -9）时内核自动放锁，不会死锁后继等锁者。
    """
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
