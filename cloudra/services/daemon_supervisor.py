"""守护进程拉起判定链的唯一事实源：compute scheduler 与 kg_vec 向量微服务。

两个消费入口：``web_launcher.launch_browser`` 启动时 ensure 一次；api_v2
lifespan 的 watchdog 循环周期 ensure（守护崩溃退出后自动重拉起）。存活判定
只信 flock 探测（kg_vec 另有 /health 探测），任何路径都不 kill 进程。

崩溃循环防护：每次真实 ``spawn_detached`` 尝试（含 Popen 抛异常的失败路径）
前查 ``<lock_path>.last_spawn`` 持久时间戳（原子写、进程重启不丢），距上次拉起
不足当前退避间隔则本轮跳过并记 warning——防止配置错误导致的 fork 轰炸。退避
为指数：连续失败次数 n 持久化在 ``<lock_path>.spawn_fail_count``，间隔 =
``min(MIN_RESPAWN_SECONDS * 2**n, MAX_RESPAWN_SECONDS)``；健康观测（kg_vec
/health 200、scheduler 锁被活实例持有）把 n 归零。节流只作用于"锁空闲、要拉起"
路径：锁被持有（活实例）时不读时间戳直接返回。
"""

from __future__ import annotations

import logging
import os
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 距上次真实拉起不足当前退避间隔时跳过本轮 spawn（崩溃循环节流）：
# 连续失败 n 次后间隔 = min(MIN_RESPAWN_SECONDS * 2**n, MAX_RESPAWN_SECONDS)。
MIN_RESPAWN_SECONDS = 60.0
MAX_RESPAWN_SECONDS = 1800.0

# 进程内关停标志（停止语义契约 5）：置位后 ensure_* 拒绝拉起，
# api_v2 watchdog 的自愈同步失效。普通 agent.cancel 不触此。
_SHUTDOWN_REQUESTED = False


def daemons_stop_marker_path() -> str:
    """持久关停 marker（`cloudra stop` 写入）：跨进程生效，scheduler/kg_vec
    守护自检退出、ensure_* 拒绝拉起；显式启动（web_launcher）清除它。"""
    from cloudra.persistence import paths

    return str(paths.data_dir() / "daemons.stop")


def request_daemons_shutdown(*, persist: bool = False) -> None:
    """置全局关停标志：ensure_* 自此拒绝拉起（watchdog 自愈同步失效）。

    persist=True 时落持久 marker 文件（显式"停止全部 Cloudra"入口用，
    跨进程生效）；API lifespan 的正常关停用 persist=False——守护进程
    刻意长存，不随 API 退出。
    """
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    if persist:
        from cloudra.persistence.fs_utils import atomic_write_text

        try:
            marker = Path(daemons_stop_marker_path())
            marker.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(str(marker), str(time.time()))
        except OSError:
            logger.warning("could not write daemons stop marker", exc_info=True)


def daemons_shutdown_requested() -> bool:
    """关停判定：进程内标志或持久 marker 文件（后者跨进程）。"""
    if _SHUTDOWN_REQUESTED:
        return True
    try:
        return Path(daemons_stop_marker_path()).is_file()
    except OSError:
        return False


def clear_daemons_shutdown() -> None:
    """显式启动（`cloudra`/`cloudra web`）时清除关停标志与持久 marker。"""
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = False
    try:
        Path(daemons_stop_marker_path()).unlink(missing_ok=True)
    except OSError:
        logger.warning("could not clear daemons stop marker", exc_info=True)


def _reset_shutdown_for_tests() -> None:
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = False


def ensure_daemons() -> None:
    """无活实例则拉起 scheduler 与 kg_vec；单个失败只记警告，互不影响。"""
    ensure_scheduler()
    ensure_kg_vec()


def last_spawn_path(lock_path: str) -> str:
    """拉起节流时间戳文件：``<lock_path>.last_spawn``，内容 epoch 秒。"""
    return lock_path + ".last_spawn"


def spawn_fail_count_path(lock_path: str) -> str:
    """连续拉起失败计数文件：``<lock_path>.spawn_fail_count``，内容十进制整数。"""
    return lock_path + ".spawn_fail_count"


def _read_spawn_fail_count(lock_path: str) -> int:
    """计数缺失/损坏一律视为 0（基础间隔）。"""
    try:
        return int(Path(spawn_fail_count_path(lock_path)).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def reset_spawn_fail_count(lock_path: str) -> None:
    """健康观测成功后归零退避计数（守护已恢复，回到基础间隔）。"""
    try:
        Path(spawn_fail_count_path(lock_path)).unlink(missing_ok=True)
    except OSError:
        logger.warning("could not reset spawn fail count for %s", lock_path, exc_info=True)


def _respawn_interval_seconds(lock_path: str) -> float:
    """当前退避间隔：min(MIN_RESPAWN_SECONDS * 2**n, MAX_RESPAWN_SECONDS)。"""
    return min(MIN_RESPAWN_SECONDS * (2 ** _read_spawn_fail_count(lock_path)), MAX_RESPAWN_SECONDS)


def _respawn_throttled(lock_path: str) -> bool:
    """距上次真实拉起不足当前退避间隔。时间戳缺失/损坏一律视为可拉起。"""
    try:
        last = float(Path(last_spawn_path(lock_path)).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return time.time() - last < _respawn_interval_seconds(lock_path)


def _record_spawn(lock_path: str, *, failed: bool = False) -> None:
    """每次真实 spawn 尝试都落时间戳——含 Popen 抛异常的失败路径（原先失败
    完全不限速，崩溃配置下会无限重试）；failed=True 递增连续失败计数，
    成功只刷新时间戳（计数由健康观测归零）。"""
    from cloudra.persistence.fs_utils import atomic_write_text

    atomic_write_text(last_spawn_path(lock_path), f"{time.time():.3f}")
    if failed:
        atomic_write_text(spawn_fail_count_path(lock_path), str(_read_spawn_fail_count(lock_path) + 1))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]  # cloudra/services/daemon_supervisor.py -> 仓库根


def ensure_scheduler() -> None:
    """无活调度器则 detach 拉起一个（flock 单实例；CLOUDRA_SCHEDULER=off 关闭）。

    调度守护进程与 Web 服务彻底分家：本进程崩溃/退出不影响它，它崩溃
    也不影响在跑的计算（guard/calculator 本就 detach 且终态直接写库）。
    """
    if daemons_shutdown_requested():
        return
    if os.environ.get("CLOUDRA_SCHEDULER", "").strip().lower() in {"off", "0", "false"}:
        return
    try:
        from cloudra.infra.compute_utils import spawn_detached
        from cloudra.infra.flocks import try_acquire_lock
        from cloudra.persistence import paths
        from cloudra.scheduler.daemon import scheduler_lock_path

        lock_path = scheduler_lock_path()
        fd = try_acquire_lock(lock_path)
        if fd is None:
            reset_spawn_fail_count(lock_path)  # 活实例持锁 = 健康观测，退避归零
            return  # 已有活实例
        os.close(fd)  # 只探测；守护进程启动后自己持锁
        if _respawn_throttled(lock_path):
            logger.warning(
                "compute scheduler respawn throttled (backoff %.0fs not elapsed)",
                _respawn_interval_seconds(lock_path),
            )
            return
        log_dir = paths.logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            spawn_detached(
                [sys.executable, "-m", "cloudra.scheduler"],
                str(log_dir / "scheduler.log"),
            )
        except Exception:
            _record_spawn(lock_path, failed=True)  # Popen 失败同样限速并计入退避
            raise
        _record_spawn(lock_path)
        logger.info("compute scheduler daemon started (detached)")
    except Exception as exc:
        logger.warning("could not start compute scheduler: %s", exc)


def kg_vec_lock_path() -> str:
    """kg_vec 微服务单实例锁（scheduler.lock 同款范式：服务进程自持到退出）。"""
    from cloudra.persistence import paths

    return str(paths.data_dir() / "kg_vec.lock")


def kg_vec_is_healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=1.0) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def resolve_vec_python(configured: str = "") -> str | None:
    """kg_vec 解释器解析：显式配置（knowledge_vec_python / CLOUDRA_KNOWLEDGE_VEC_PYTHON）
    优先且必须真实存在（配置写错要暴露，不静默回落）；空串时按仓库根 .venv-trans
    自动探测。找不到返回 None（调用方打警告跳过，不炸启动）。
    """
    configured = (configured or "").strip()
    if configured:
        path = Path(configured).expanduser()
        return str(path) if path.is_file() else None
    repo_root = _repo_root()
    for candidate in (
        repo_root / ".venv-trans" / "bin" / "python",
        repo_root / ".venv-trans" / "Scripts" / "python.exe",  # Windows venv 布局
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def ensure_kg_vec() -> None:
    """chem-kb 插件激活且无活 kg_vec 服务时，detach 拉起向量检索微服务。

    判定链（任一命中即返回，不拉起）：``CLOUDRA_KG_VEC=off/0/false`` → 插件未装
    （plugins 不含 ``cloudra.knowledge.plugin:plugin``，没有消费者）→ 服务已健康
    （GET ``CLOUDRA_KG_VEC_URL``/health 200，手动起的也算）→ flock 已被持有
    （另一实例在跑/在启动）→ vec 解释器探测不到（打警告跳过，不炸启动）。
    服务进程经 ``--lock-file`` 自持 flock 至退出（scheduler.lock 同款范式）；
    端口从 ``CLOUDRA_KG_VEC_URL`` 解析，缺省 8765。
    """
    if daemons_shutdown_requested():
        return
    if os.environ.get("CLOUDRA_KG_VEC", "").strip().lower() in {"off", "0", "false"}:
        return
    try:
        from cloudra.infra.compute_utils import spawn_detached
        from cloudra.infra.config import get_config
        from cloudra.infra.flocks import try_acquire_lock
        from cloudra.knowledge.plugin import PLUGIN_SPEC, VEC_URL_DEFAULT, VEC_URL_ENV
        from cloudra.persistence import paths

        cfg = get_config()
        if PLUGIN_SPEC not in cfg.plugins:
            return
        url = (os.environ.get(VEC_URL_ENV) or VEC_URL_DEFAULT).rstrip("/")
        lock_path = kg_vec_lock_path()
        if kg_vec_is_healthy(url):
            reset_spawn_fail_count(lock_path)  # 健康探测成功，退避归零
            return  # 已有健康服务
        vec_python = resolve_vec_python(cfg.knowledge_vec_python)
        if vec_python is None:
            logger.warning(
                "kg_vec: vector venv python not found — semantic channel stays down; "
                "set knowledge_vec_python in config.yaml or CLOUDRA_KNOWLEDGE_VEC_PYTHON"
            )
            return
        fd = try_acquire_lock(lock_path)
        if fd is None:
            return  # 已有活实例持锁
        os.close(fd)  # 只探测；服务启动后自己持锁
        if _respawn_throttled(lock_path):
            logger.warning(
                "kg_vec respawn throttled (backoff %.0fs not elapsed)",
                _respawn_interval_seconds(lock_path),
            )
            return
        log_dir = paths.logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        script = _repo_root() / "scripts" / "kg_vec_service.py"
        port = urlparse(url).port or 8765
        try:
            spawn_detached(
                [vec_python, str(script), "--port", str(port), "--lock-file", lock_path],
                str(log_dir / "kg_vec.log"),
            )
        except Exception:
            _record_spawn(lock_path, failed=True)  # Popen 失败同样限速并计入退避
            raise
        _record_spawn(lock_path)
        logger.info("kg_vec service started (detached, port %s)", port)
    except Exception as exc:
        logger.warning("could not start kg_vec service: %s", exc)
