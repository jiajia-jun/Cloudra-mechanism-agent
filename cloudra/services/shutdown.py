"""显式全停入口（``cloudra stop``）的实现。

顺序（停止语义契约 3/5）：
1. 落持久关停 marker 并置进程内标志——此后任何 ensure_* 拒绝拉起，
   活着的 scheduler/kg_vec 守护自检 marker 后干净退出（flock 随进程释放）；
2. 通知 API 控制面关停（POST /api/v2/runtime/shutdown → 优雅 lifespan：
   停准入 → 取消并 await 推理/收尾任务 → 关流/客户端 → 回收 JS host）；
3. 有界等待 API 停止响应；**协作关停失败则升级**：对该端口的 LISTEN
   进程（健康端点已验明是 Cloudra API，双重确认归属）SIGTERM → 有界
   等待 → SIGKILL。手工/旧方式拉起的 uvicorn 缺
   ``--timeout-graceful-shutdown`` 时优雅关停会被 SPA 常驻 SSE 挂死
   （GH #38），必须有这样的兜底；
4. 复查守护 flock 与计算作业，报告终态。

归属边界：只终止有明确归属的执行（API 进程=端口 LISTEN + 健康验明、
自持 flock 的守护）。在跑的计算进程（guard/calculator/QM）按铁律不
kill——它们不受本入口影响，会跑到终态并自行写库收尾；Slurm 作业的
取消只走既有的显式 cancel_requested → scancel 路径。禁止宽泛
python/node/用户名匹配杀进程。
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
import urllib.request

from cloudra.infra.flocks import is_lock_held
from cloudra.persistence import paths
from cloudra.services.daemon_supervisor import (
    kg_vec_lock_path,
    request_daemons_shutdown,
)


def _health_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/api/v2/runtime/health"


def api_is_healthy(port: int, *, timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(_health_url(port), timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def find_api_port() -> int | None:
    """定位在跑的 API 端口：CLOUDRA_API_PORT 优先，否则从 8000 起扫。"""
    env_value = os.environ.get("CLOUDRA_API_PORT")
    candidates = [int(env_value)] if env_value else list(range(8000, 8100))
    for port in candidates:
        if api_is_healthy(port):
            return port
    return None


def request_api_shutdown(port: int, *, timeout: float = 5.0) -> bool:
    """POST 关停端点；连接被对端立刻掐断也算已送达（进程正在退出）。"""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v2/runtime/shutdown", method="POST"
    )
    from cloudra.services.api_token import resolve_api_token

    token = resolve_api_token()
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError:
        return False
    except Exception:
        # 进程可能在响应返回前已开始退出；稍后由健康探测复查定案。
        return True


def _wait_for(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.25)
    return predicate()


def _port_listener_pid(port: int) -> int | None:
    """端口 LISTEN 进程的 PID（lsof 按端口精确定位，不是进程名宽匹配）。

    归属链：返回的 PID 在该端口上 LISTEN，而调用方已用健康端点验明该端口
    是 Cloudra API——两步合一才构成「明确归属」，任何一环缺失都不动手。
    """
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    pids = [int(line) for line in out.stdout.split() if line.strip().isdigit()]
    return pids[0] if pids else None


def _pid_alive(pid: int) -> bool:
    """我们已验明归属的单个 PID 的存活探测（kill 0）。

    flock 探测铁律约束的是计算进程（guard/calculator/QM）——它们由 scheduler
    体系管理、本入口永不触碰；API 控制面进程没有 flock，其归属由
    「端口 LISTEN + 健康验明」建立，存活探测只能走信号 0。
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 存在但属他人——视作活着（且不该由我们杀）
    return True


def _signal_pid(pid: int, sig: signal.Signals) -> bool:
    """给已验明归属的 PID 发信号；进程消失/无权限返回 False。"""
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _force_stop_pid(pid: int | None) -> str | None:
    """协作关停失败后的升级：SIGTERM → 有界等待 → SIGKILL。

    ``pid`` 必须在关停动作之前由「端口 LISTEN + 健康验明」双重确认归属
    （关停后监听 socket 可能已关闭，届时再从端口反查不到挂死的进程）。
    返回实际生效的升级级别（"sigterm"/"sigkill"）；无归属 PID 或最终仍
    活着时返回 None（调用方如实报告失败，绝不声称已停）。uvicorn 收到
    第二发 SIGTERM 会跳过连接排干立即退出（force_exit），所以重复
    SIGTERM 对正在优雅关停的进程是有效推力而非误伤。
    """
    if pid is None:
        return None
    if not _signal_pid(pid, signal.SIGTERM):
        return None
    if _wait_for(lambda: not _pid_alive(pid), 10.0):
        return "sigterm"
    if not _signal_pid(pid, signal.SIGKILL):
        return "sigterm" if not _pid_alive(pid) else None
    if _wait_for(lambda: not _pid_alive(pid), 5.0):
        return "sigkill"
    return None


def _api_gone(port: int, pid: int | None) -> bool:
    """「API 真的停了」的判定：端口不再应答，且归属进程已死（归属不明时
    退化为端口判定——旧行为）。"""
    if api_is_healthy(port):
        return False
    return pid is None or not _pid_alive(pid)


def _is_owned_runtime_process(pid: int, lock_path) -> bool:
    """Recognize our exact uvicorn entry point, user, and held runtime lock."""
    from cloudra.services.runtime_ownership import _lsof

    if not is_lock_held(str(lock_path)):
        return False
    fields = _lsof(["-nP", "-a", "-p", str(pid), "-Fln", str(lock_path)]).splitlines()
    locked = any(
        fields[index] in {"lW", "lw"} and fields[index + 1] == f"n{lock_path}"
        for index in range(len(fields) - 1)
    )
    if not locked:
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "uid=", "-o", "args="],
            capture_output=True, text=True, timeout=5, check=True,
        )
        uid, command = result.stdout.strip().split(maxsplit=1)
        args = shlex.split(command)
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return (
        uid == str(os.getuid())
        and len(args) >= 4
        and args[1:4] == ["-m", "uvicorn", "cloudra.services.api_v2:create_default_v2_app"]
    )


def stop_owned_api(owner, lock_path, *, timeout: float = 20.0) -> bool:
    """Stop a verified store owner and wait for its lock to be released.

    Healthy APIs require matching listener and lock owner. Unresponsive ones
    require the same user, exact launcher command, and the runtime lock.
    """
    if owner.port is None:
        if not _is_owned_runtime_process(owner.pid, lock_path):
            return False
    else:
        if _port_listener_pid(owner.port) != owner.pid or not api_is_healthy(owner.port):
            return False
        request_api_shutdown(owner.port)
        if _wait_for(lambda: not is_lock_held(str(lock_path)), timeout):
            return True
    _force_stop_pid(owner.pid)
    return _wait_for(lambda: not is_lock_held(str(lock_path)), timeout)


def stop_all(*, timeout: float = 20.0) -> dict:
    """执行显式全停，返回复查报告（各部件最终状态）。"""
    request_daemons_shutdown(persist=True)
    report: dict = {"stop_marker": True}

    port = find_api_port()
    report["api_port"] = port
    report["api_escalated"] = None
    if port is not None:
        # 关停动作之前锁定进程归属：优雅关停会先行关闭监听 socket（健康
        # 探测转失败），之后端口反查不到可能挂死的进程本体。
        pid = _port_listener_pid(port)
        request_api_shutdown(port)
        if not _wait_for(lambda: not api_is_healthy(port), timeout):
            # 协作端点无响应（事件循环卡死/鉴权失败/信号丢失）：直接信号升级。
            report["api_escalated"] = _force_stop_pid(pid)
        elif pid is not None and _pid_alive(pid):
            # 端口已不答但进程未死：优雅关停被常驻 SSE 连接排干挂死
            # （缺 --timeout-graceful-shutdown 的实例，GH #38）。先给足优雅
            # 排空窗口（对齐该上界的 20s），再信号升级。
            if not _wait_for(lambda: not _pid_alive(pid), timeout + 5.0):
                report["api_escalated"] = _force_stop_pid(pid)
        report["api_stopped"] = _api_gone(port, pid)
    else:
        store = os.environ.get("CLOUDRA_RUNTIME_STORE") or paths.runtime_db_path()
        lock_path = paths.runtime_api_lock_path(store)
        # 没有健康 API 不代表旧进程已经退出：它可能仍持有 runtime 锁。
        if is_lock_held(str(lock_path)):
            from cloudra.services.runtime_ownership import find_store_owner

            owner = find_store_owner(store)
            report["api_stopped"] = bool(owner and stop_owned_api(owner, lock_path, timeout=timeout))
        else:
            report["api_stopped"] = None

    from cloudra.scheduler.daemon import scheduler_lock_path

    locks = {"scheduler": scheduler_lock_path(), "kg_vec": kg_vec_lock_path()}
    held = {name: path for name, path in locks.items() if is_lock_held(path)}
    if held:
        _wait_for(
            lambda: not any(is_lock_held(path) for path in held.values()), timeout
        )
    report["daemons"] = {
        name: ("running" if is_lock_held(path) else "stopped")
        for name, path in locks.items()
    }

    # 复查：仍在跑的计算作业只报告、绝不 kill（执行面铁律）。
    report["compute_jobs_running"] = _count_running_compute_jobs()
    return report


def _count_running_compute_jobs() -> int | None:
    """running 状态的本地/Slurm 作业数；库不存在返回 None。"""
    db_path = paths.compute_db_path()
    if not db_path.is_file():
        return None
    try:
        import sqlite3

        con = sqlite3.connect(str(db_path))
        try:
            (count,) = con.execute(
                "SELECT COUNT(*) FROM compute_jobs WHERE state = 'running'"
            ).fetchone()
            return int(count)
        finally:
            con.close()
    except Exception:
        return None
