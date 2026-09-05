"""显式全停入口（``cloudra stop``）的实现。

顺序（停止语义契约 3/5）：
1. 落持久关停 marker 并置进程内标志——此后任何 ensure_* 拒绝拉起，
   活着的 scheduler/kg_vec 守护自检 marker 后干净退出（flock 随进程释放）；
2. 通知 API 控制面关停（POST /api/v2/runtime/shutdown → 优雅 lifespan：
   停准入 → 取消并 await 推理/收尾任务 → 关流/客户端 → 回收 JS host）；
3. 有界等待 API 停止响应、守护 flock 释放，然后复查报告。

归属边界：只终止有明确归属的执行（API 进程自己、自持 flock 的守护）。
在跑的计算进程（guard/calculator/QM）按铁律不 kill——它们不受本入口
影响，会跑到终态并自行写库收尾；Slurm 作业的取消只走既有的显式
cancel_requested → scancel 路径。禁止宽泛 python/node/用户名匹配杀进程。
"""

from __future__ import annotations

import os
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
    token = os.environ.get("CLOUDRA_API_TOKEN", "").strip()
    if token:
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


def stop_all(*, timeout: float = 20.0) -> dict:
    """执行显式全停，返回复查报告（各部件最终状态）。"""
    request_daemons_shutdown(persist=True)
    report: dict = {"stop_marker": True}

    port = find_api_port()
    report["api_port"] = port
    if port is not None:
        request_api_shutdown(port)
        report["api_stopped"] = _wait_for(
            lambda: not api_is_healthy(port), timeout
        )
    else:
        report["api_stopped"] = None  # 没有在跑的 API

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
