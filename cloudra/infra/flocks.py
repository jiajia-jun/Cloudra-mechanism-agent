"""fcntl.flock 原语：执行面唯一的进程存活/互斥判定手段（POSIX only）。

设计约定（AGENTS.md 铁律）：执行面判断"进程是否还活着"一律用锁探测，
不读 PID、不解析 ps//proc 文本。进程死亡（含 kill -9）时内核自动放锁，
因此锁探测不存在 PID 复用误判。guard/calculator/调度器单实例共用本模块。

Windows 兜底：fcntl 不存在时用 msvcrt.locking 模拟同一组原语（锁文件
offset 0 的 1 字节；进程死亡同样由内核释放锁），保证配置读-改-写等
共享写路径在非 POSIX 平台不因 import 失败而 500。
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

try:
    import fcntl  # POSIX
except ImportError:  # Windows
    fcntl = None
    import msvcrt

_LOCK_NBYTES = 1


def _try_lock_fd(fd: int) -> bool:
    """非阻塞抢排他锁；抢到 True，被占 False。"""
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, _LOCK_NBYTES)
        return True
    except OSError:
        return False


def _unlock_fd(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return
    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_NBYTES)


def try_acquire_lock(path: str) -> int | None:
    """非阻塞抢排他 flock。

    成功返回持有锁的 fd——调用方必须保持该 fd 打开以持锁（进程退出即释放）；
    锁被其他进程持有时返回 None。
    """
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    if not _try_lock_fd(fd):
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
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        else:
            # msvcrt 无阻塞档：短轮询等待，直至抢到锁。
            while not _try_lock_fd(fd):
                time.sleep(0.05)
        yield fd
    finally:
        _unlock_fd(fd)
        os.close(fd)
