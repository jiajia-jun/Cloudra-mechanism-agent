"""calculator 锁 wrapper：持有 calc 锁后 exec 真正的 calculator 命令。

用法：``python -m cloudra.runtime.calc_lock_wrapper <lock_path> -- <cmd> [args...]``

锁 fd 标记为 inheritable 后跨 exec 继承，calculator（g16/orca/…）及其全部
子进程存续期间锁保持有效；全家退出后内核自动放锁。因此"calc 锁能否抢到"
就是"这次计算是否还在跑"的权威答案，全程不需要任何 PID 探测。

抢不到锁（同名作业已有计算在跑）时以退出码 3 拒绝启动，构成 OS 级防重。
"""

from __future__ import annotations

import fcntl
import os
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
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"calc lock held by another process: {lock_path}", file=sys.stderr)
        return 3
    os.set_inheritable(fd, True)  # PEP 446：默认不可继承，必须显式放行给 exec 后的进程
    os.execvp(cmd[0], cmd)
    return 127  # unreachable：execvp 成功不返回，失败则抛 OSError


if __name__ == "__main__":
    raise SystemExit(main())
