"""calculator 锁 wrapper：保留独占进程组，直到计算全家的锁释放。

用法：``python -m cloudra.runtime.calc_lock_wrapper <lock_path> -- <cmd> [args...]``

calculator 继承 calc 锁，wrapper 写完退出码才关闭自身原锁句柄。即使 calculator 提前
退出，wrapper 仍等继承锁的引擎子进程全部退出，保持组长身份，防止取消时
进程组 ID 被复用。计算是否存活仍只认 flock，不探测或信任存盘 PID。
显式取消时保留组长与锁，给 TERM 一秒收尾后对整个自有进程组发 KILL；
引擎关闭继承句柄或忽略 TERM 都不能让取消提前确认或永久挂起。

抢不到锁（同名作业已有计算在跑）时以退出码 3 拒绝启动，构成 OS 级防重。
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from cloudra.persistence.fs_utils import atomic_write_json

_CANCEL_GRACE_SECONDS = 1.0
_POLL_SECONDS = 0.05


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

    def finish_requested_cancel():
        if cancel_requested:
            # Keep our group ID reserved until every remaining member receives
            # KILL, even if the engine closed its inherited lock or ignored TERM.
            # This includes us: only the guard may then acknowledge cancellation.
            time.sleep(_CANCEL_GRACE_SECONDS)
            os.killpg(os.getpid(), signal.SIGKILL)

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
        exit_path = Path(lock_path).with_suffix(".exit.json")
        exit_path.unlink(missing_ok=True)
        if cancel_requested:
            return 128 + signal.SIGTERM
        os.set_inheritable(fd, True)
        calculator = subprocess.Popen(cmd, pass_fds=(fd,))
        if cancel_requested:
            # A TERM during Popen may have arrived before the engine existed.
            # Popen has now completed exec; cover that window from our own group.
            # The handler only records the flag, so this does not recurse.
            os.killpg(os.getpid(), signal.SIGTERM)
        while True:
            finish_requested_cancel()
            try:
                returncode = calculator.wait(timeout=_POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                pass
        finish_requested_cancel()
        # Persist before releasing the calc lock, so an adopt guard can recover
        # the result even when the original guard no longer owns waitpid.
        atomic_write_json(str(exit_path), {"exit_code": returncode})
        os.close(fd)
        fd = os.open(lock_path, os.O_RDWR)
        while True:
            finish_requested_cancel()
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                time.sleep(_POLL_SECONDS)
                continue
            finish_requested_cancel()
            return returncode
    finally:
        if fd is not None:
            os.close(fd)
        signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
