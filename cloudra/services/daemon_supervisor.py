"""守护进程拉起判定链的唯一事实源：compute scheduler 与 kg_vec 向量微服务。

两个消费入口：``web_launcher.launch_browser`` 启动时 ensure 一次；api_v2
lifespan 的 watchdog 循环周期 ensure（守护崩溃退出后自动重拉起）。存活判定
只信 flock 探测（kg_vec 另有 /health 探测），任何路径都不 kill 进程。

崩溃循环防护：每次真实 ``spawn_detached`` 前查 ``<lock_path>.last_spawn``
持久时间戳（原子写、进程重启不丢），距上次拉起不足 ``MIN_RESPAWN_SECONDS``
则本轮跳过并记 warning——防止配置错误导致的每秒 fork 轰炸。节流只作用于
"锁空闲、要拉起"路径：锁被持有（活实例）时不读时间戳直接返回。
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

# 距上次真实拉起不足该秒数时跳过本轮 spawn（崩溃循环节流）
MIN_RESPAWN_SECONDS = 60.0


def ensure_daemons() -> None:
    """无活实例则拉起 scheduler 与 kg_vec；单个失败只记警告，互不影响。"""
    ensure_scheduler()
    ensure_kg_vec()


def last_spawn_path(lock_path: str) -> str:
    """拉起节流时间戳文件：``<lock_path>.last_spawn``，内容 epoch 秒。"""
    return lock_path + ".last_spawn"


def _respawn_throttled(lock_path: str) -> bool:
    """距上次真实拉起 < MIN_RESPAWN_SECONDS。时间戳缺失/损坏一律视为可拉起。"""
    try:
        last = float(Path(last_spawn_path(lock_path)).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return time.time() - last < MIN_RESPAWN_SECONDS


def _record_spawn(lock_path: str) -> None:
    from cloudra.persistence.fs_utils import atomic_write_text

    atomic_write_text(last_spawn_path(lock_path), f"{time.time():.3f}")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]  # cloudra/services/daemon_supervisor.py -> 仓库根


def ensure_scheduler() -> None:
    """无活调度器则 detach 拉起一个（flock 单实例；CLOUDRA_SCHEDULER=off 关闭）。

    调度守护进程与 Web 服务彻底分家：本进程崩溃/退出不影响它，它崩溃
    也不影响在跑的计算（guard/calculator 本就 detach 且终态直接写库）。
    """
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
            return  # 已有活实例
        os.close(fd)  # 只探测；守护进程启动后自己持锁
        if _respawn_throttled(lock_path):
            logger.warning(
                "compute scheduler respawn throttled (last spawn < %ss ago)", MIN_RESPAWN_SECONDS
            )
            return
        log_dir = paths.logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        spawn_detached(
            [sys.executable, "-m", "cloudra.scheduler"],
            str(log_dir / "scheduler.log"),
        )
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
        if kg_vec_is_healthy(url):
            return  # 已有健康服务
        vec_python = resolve_vec_python(cfg.knowledge_vec_python)
        if vec_python is None:
            logger.warning(
                "kg_vec: vector venv python not found — semantic channel stays down; "
                "set knowledge_vec_python in config.yaml or CLOUDRA_KNOWLEDGE_VEC_PYTHON"
            )
            return
        lock_path = kg_vec_lock_path()
        fd = try_acquire_lock(lock_path)
        if fd is None:
            return  # 已有活实例持锁
        os.close(fd)  # 只探测；服务启动后自己持锁
        if _respawn_throttled(lock_path):
            logger.warning("kg_vec respawn throttled (last spawn < %ss ago)", MIN_RESPAWN_SECONDS)
            return
        log_dir = paths.logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        script = _repo_root() / "scripts" / "kg_vec_service.py"
        port = urlparse(url).port or 8765
        spawn_detached(
            [vec_python, str(script), "--port", str(port), "--lock-file", lock_path],
            str(log_dir / "kg_vec.log"),
        )
        _record_spawn(lock_path)
        logger.info("kg_vec service started (detached, port %s)", port)
    except Exception as exc:
        logger.warning("could not start kg_vec service: %s", exc)
