"""Standalone POSIX calculator owner: hold the lock until its session exits.

用法：``python -m cloudra.runtime.calc_lock_wrapper <lock_path> -- <cmd> [args...]``

The fresh session is the ownership boundary, including MPI children that create
another process group in that session. Only this live owner resolves and signals
its current members. No persisted PID is used. External liveness still uses flock.
An explicit lock-derived .cancel request works even after its guard was replaced.
This file also runs directly with Python and the standard library on SSH nodes.

抢不到锁（同名作业已有计算在跑）时以退出码 3 拒绝启动，构成 OS 级防重。
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

_CANCEL_GRACE_SECONDS = 1.0
_POLL_SECONDS = 0.05


def cancellation_path(lock_path: str | Path) -> Path:
    return Path(lock_path).with_suffix(".cancel")


def _owned_session_members() -> list[int]:
    """Native PID discovery is restricted to this still-live owner's session."""
    owner = os.getpid()
    rows = subprocess.run(
        ["ps", "-A", "-o", "pid=,stat="], check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    members = []
    for row in rows:
        fields = row.split()
        if len(fields) != 2:
            raise RuntimeError("native process list did not provide PID/state pairs")
        pid, state = int(fields[0]), fields[1]
        if pid == owner or state.startswith("Z"):
            continue
        try:
            if os.getsid(pid) == owner:
                members.append(pid)
        except ProcessLookupError:
            continue
    return members


def _signal_owned_session(sig: int) -> None:
    for pid in _owned_session_members():
        try:
            # Recheck current native ownership immediately before signalling.
            if os.getsid(pid) == os.getpid():
                os.kill(pid, sig)
        except ProcessLookupError:
            continue


def _write_exit(path: Path, returncode: int) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({"exit_code": returncode}) + "\n")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[1] != "--":
        print(
            "usage: python -m cloudra.runtime.calc_lock_wrapper <lock_path> -- <cmd> [args...]",
            file=sys.stderr,
        )
        return 2
    lock_path, cmd = args[0], args[2:]
    cancel_path = cancellation_path(lock_path)
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
        # Fail before launching an engine if native ownership cannot be read.
        _owned_session_members()
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(f"calc lock held by another process: {lock_path}", file=sys.stderr)
            return 3
        exit_path = Path(lock_path).with_suffix(".exit.json")
        exit_path.unlink(missing_ok=True)
        if cancel_requested or cancel_path.exists():
            return 128 + signal.SIGTERM
        os.set_inheritable(fd, True)
        calculator = subprocess.Popen(cmd, pass_fds=(fd,))
        cancel_started = None
        while True:
            cancel_requested = cancel_requested or cancel_path.exists()
            try:
                if cancel_requested:
                    if cancel_started is None:
                        cancel_started = time.monotonic()
                        _signal_owned_session(signal.SIGTERM)
                    elif time.monotonic() - cancel_started >= _CANCEL_GRACE_SECONDS:
                        _signal_owned_session(signal.SIGKILL)
                returncode = calculator.wait(timeout=_POLL_SECONDS)
                if not _owned_session_members():
                    break
                time.sleep(_POLL_SECONDS)
            except subprocess.TimeoutExpired:
                continue
            except (OSError, subprocess.CalledProcessError, ValueError, RuntimeError) as exc:
                # Losing visibility is not exit proof. Keep the owner and its
                # flock alive rather than acknowledge an unverified cancellation.
                print(f"cannot inspect owned calculation session: {exc}", file=sys.stderr)
                time.sleep(_POLL_SECONDS)
        if cancel_requested:
            returncode = 128 + signal.SIGTERM
        _write_exit(exit_path, returncode)
        os.close(fd)
        fd = os.open(lock_path, os.O_RDWR)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                time.sleep(_POLL_SECONDS)
                continue
            return returncode
    finally:
        if fd is not None:
            os.close(fd)
        signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
