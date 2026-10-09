"""calculator 锁 wrapper：保留独占进程组，直到计算全家的锁释放。

用法：``python -m cloudra.runtime.calc_lock_wrapper <lock_path> -- <cmd> [args...]``

calculator 继承 calc 锁，wrapper 关闭自身原锁句柄。即使 calculator 提前
退出，wrapper 仍等继承锁的引擎子进程全部退出，保持组长身份，防止取消时
进程组 ID 被复用。计算是否存活仍只认 flock，不探测或信任存盘 PID。

抢不到锁（同名作业已有计算在跑）时以退出码 3 拒绝启动，构成 OS 级防重。
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[1] != "--":
        print(
            "usage: python -m cloudra.runtime.calc_lock_wrapper <lock_path> -- <cmd> [args...]",
            file=sys.stderr,
        )
        return 2
    lock_path, cmd = args[0], args[2:]
    cancel_requested = False

    def request_cancel(_signal, _frame):
        nonlocal cancel_requested
        cancel_requested = True

    # A caught handler resets to the default in the exec child. SIG_IGN would
    # survive exec and make Gaussian ignore the group's cancellation signal.
    previous_handler = signal.signal(signal.SIGTERM, request_cancel)
    fd = None
    try:
        # monitor already starts a new session. Direct CLI callers must isolate
        # themselves before any group signal can be sent during the spawn race.
        if os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid():
            try:
                os.setsid()
            except OSError as exc:
                print(f"cannot isolate calculator session: {exc}", file=sys.stderr)
                return 1
        if os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid():
            print("calculator wrapper does not own its session", file=sys.stderr)
            return 1
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(f"calc lock held by another process: {lock_path}", file=sys.stderr)
            return 3
        if cancel_requested:
            return 128 + signal.SIGTERM
        os.set_inheritable(fd, True)
        calculator = subprocess.Popen(cmd, pass_fds=(fd,))
        os.close(fd)
        fd = None
        if cancel_requested:
            # A TERM during Popen may have arrived before the engine existed.
            # Popen has now completed exec; cover that window from our own group.
            # The handler only records the flag, so this does not recurse.
            os.killpg(os.getpid(), signal.SIGTERM)
        returncode = calculator.wait()
        fd = os.open(lock_path, os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return returncode
    finally:
        if fd is not None:
            os.close(fd)
        signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
