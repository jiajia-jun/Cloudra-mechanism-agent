"""daemon_supervisor：守护进程拉起崩溃循环节流 + api_v2 lifespan watchdog。

spawn_detached 一律 monkeypatch 拦截，绝不真起子进程；节流时间戳落在隔离
data_dir 的 ``<lock>.last_spawn``（conftest 已把 data_dir 重定向到 tmp）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

import pytest

from cloudra.infra.config import get_config
from cloudra.knowledge.plugin import PLUGIN_SPEC
from cloudra.services import daemon_supervisor


@pytest.fixture(autouse=True)
def _data_dir_exists():
    """锁文件/节流时间戳的 O_CREAT 不建父目录，这里补齐（同 test_kg_vec_launcher）。"""
    Path(get_config().data_dir).mkdir(parents=True, exist_ok=True)


@pytest.fixture
def spawn_calls(monkeypatch):
    """拦截 compute_utils.spawn_detached（ensure_* 惰性导入源模块属性）。"""
    calls: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        "cloudra.infra.compute_utils.spawn_detached",
        lambda cmd, log_path: calls.append((list(cmd), str(log_path))),
    )
    return calls


def _scheduler_last_spawn() -> Path:
    from cloudra.scheduler.daemon import scheduler_lock_path

    return Path(daemon_supervisor.last_spawn_path(scheduler_lock_path()))


# ---------------------------------------------------------------- 崩溃循环节流


def test_ensure_daemons_runs_both(monkeypatch):
    ran: list[str] = []
    monkeypatch.setattr(daemon_supervisor, "ensure_scheduler", lambda: ran.append("scheduler"))
    monkeypatch.setattr(daemon_supervisor, "ensure_kg_vec", lambda: ran.append("kg_vec"))
    daemon_supervisor.ensure_daemons()
    assert ran == ["scheduler", "kg_vec"]


def test_spawn_writes_timestamp_then_throttles(spawn_calls, caplog):
    daemon_supervisor.ensure_scheduler()
    assert len(spawn_calls) == 1
    assert _scheduler_last_spawn().is_file()  # 拉起时间戳已持久化落盘
    # 立刻再次 ensure：锁空闲（mock spawn 不持锁）但距上次拉起 < MIN_RESPAWN_SECONDS
    with caplog.at_level(logging.WARNING, logger="cloudra.services.daemon_supervisor"):
        daemon_supervisor.ensure_scheduler()
    assert len(spawn_calls) == 1
    assert "throttled" in caplog.text


def test_throttle_expires_after_min_respawn(spawn_calls):
    daemon_supervisor.ensure_scheduler()
    assert len(spawn_calls) == 1
    past = time.time() - (daemon_supervisor.MIN_RESPAWN_SECONDS + 1)
    _scheduler_last_spawn().write_text(f"{past:.3f}", encoding="utf-8")
    daemon_supervisor.ensure_scheduler()
    assert len(spawn_calls) == 2


@pytest.mark.parametrize("content", ["not-a-number", "", "  \n"])
def test_corrupt_last_spawn_allows_spawn(spawn_calls, content):
    _scheduler_last_spawn().write_text(content, encoding="utf-8")
    daemon_supervisor.ensure_scheduler()
    assert len(spawn_calls) == 1


def test_live_instance_never_touches_throttle(spawn_calls, monkeypatch):
    """flock 被持有（活实例）：直接返回，不读时间戳、不告警、不 spawn。"""
    from cloudra.infra.flocks import try_acquire_lock
    from cloudra.scheduler.daemon import scheduler_lock_path

    fd = try_acquire_lock(scheduler_lock_path())
    assert fd is not None
    warnings: list[str] = []
    monkeypatch.setattr(
        daemon_supervisor.logger,
        "warning",
        lambda msg, *args, **kwargs: warnings.append(msg % args if args else str(msg)),
    )
    try:
        # 时间戳写成"刚刚拉起"也不影响活实例路径
        _scheduler_last_spawn().write_text(f"{time.time():.3f}", encoding="utf-8")
        daemon_supervisor.ensure_scheduler()
        assert spawn_calls == []
        assert warnings == []
    finally:
        os.close(fd)


def test_kg_vec_spawn_throttled_too(spawn_calls, monkeypatch, tmp_path):
    """节流对 ensure_kg_vec 同样生效（共用同一持久时间戳机制）。"""
    fake_py = tmp_path / ".venv-trans" / "bin" / "python"
    fake_py.parent.mkdir(parents=True)
    fake_py.touch()
    monkeypatch.setattr(get_config(), "plugins", [PLUGIN_SPEC])
    monkeypatch.setattr(daemon_supervisor, "resolve_vec_python", lambda _c="": str(fake_py))
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", "http://127.0.0.1:1")  # 死端口立即拒连

    daemon_supervisor.ensure_kg_vec()
    assert len(spawn_calls) == 1
    last_spawn = Path(daemon_supervisor.last_spawn_path(daemon_supervisor.kg_vec_lock_path()))
    assert last_spawn.is_file()
    daemon_supervisor.ensure_kg_vec()
    assert len(spawn_calls) == 1  # 节流跳过
    last_spawn.write_text(f"{time.time() - (daemon_supervisor.MIN_RESPAWN_SECONDS + 1):.3f}")
    daemon_supervisor.ensure_kg_vec()
    assert len(spawn_calls) == 2


# ------------------------------------------------------------- lifespan watchdog


def _make_app():
    from cloudra.runtime_v2.core import RuntimeCore
    from cloudra.services.api_v2 import create_v2_app

    return create_v2_app(RuntimeCore(strict_events=True))


@pytest.mark.asyncio
async def test_watchdog_ticks_until_shutdown(monkeypatch):
    monkeypatch.setenv("CLOUDRA_DAEMON_WATCHDOG", "on")  # 覆盖 conftest 的 off
    monkeypatch.setenv("CLOUDRA_DAEMON_WATCHDOG_SECONDS", "0.05")
    ticks: list[int] = []
    monkeypatch.setattr(daemon_supervisor, "ensure_daemons", lambda: ticks.append(1))

    app = _make_app()
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.3)
        assert len(ticks) >= 2
        count_at_shutdown = len(ticks)
    await asyncio.sleep(0.15)
    assert len(ticks) == count_at_shutdown  # lifespan 收尾后 task 已取消，不再增长


@pytest.mark.asyncio
async def test_watchdog_survives_ensure_exception(monkeypatch):
    monkeypatch.setenv("CLOUDRA_DAEMON_WATCHDOG", "on")
    monkeypatch.setenv("CLOUDRA_DAEMON_WATCHDOG_SECONDS", "0.05")
    ticks: list[int] = []

    def _boom() -> None:
        ticks.append(1)
        raise RuntimeError("boom")

    monkeypatch.setattr(daemon_supervisor, "ensure_daemons", _boom)

    app = _make_app()
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.3)
        assert len(ticks) >= 2  # 异常只记日志，loop 继续 tick


@pytest.mark.asyncio
async def test_watchdog_off_by_default_in_tests():
    # conftest autouse 已设 CLOUDRA_DAEMON_WATCHDOG=off：普通建 app 不启动巡检
    app = _make_app()
    async with app.router.lifespan_context(app):
        names = {task.get_name() for task in asyncio.all_tasks()}
        assert "daemon-watchdog" not in names


# ------------------------------------------------------------- 指数退避（崩溃循环熔断）


def _scheduler_fail_count() -> Path:
    from cloudra.scheduler.daemon import scheduler_lock_path

    return Path(daemon_supervisor.spawn_fail_count_path(scheduler_lock_path()))


def _backoff_spawn_to_past(seconds: float) -> None:
    _scheduler_last_spawn().write_text(f"{time.time() - seconds:.3f}", encoding="utf-8")


def test_spawn_exception_is_throttled_and_backoff_grows(monkeypatch):
    """Popen 抛异常原先完全不限速（崩溃配置下 30s 无限重试）；
    现在失败也落时间戳并计入退避，间隔按 2^n 翻倍。"""
    attempts: list[tuple[list[str], str]] = []

    def boom(cmd, log_path):
        attempts.append((list(cmd), str(log_path)))
        raise OSError("spawn failed")

    monkeypatch.setattr("cloudra.infra.compute_utils.spawn_detached", boom)

    daemon_supervisor.ensure_scheduler()  # 第一次失败：n=1 → 退避 120s
    assert len(attempts) == 1
    assert _scheduler_last_spawn().is_file()  # 失败路径也落了时间戳
    assert _scheduler_fail_count().read_text(encoding="utf-8") == "1"

    daemon_supervisor.ensure_scheduler()  # 节流跳过，不再尝试
    assert len(attempts) == 1

    _backoff_spawn_to_past(61)  # n=1 → 间隔 120s，61s 前仍节流
    daemon_supervisor.ensure_scheduler()
    assert len(attempts) == 1

    _backoff_spawn_to_past(121)  # 超过 120s：重试 → 再失败 n=2 → 间隔 240s
    daemon_supervisor.ensure_scheduler()
    assert len(attempts) == 2
    assert _scheduler_fail_count().read_text(encoding="utf-8") == "2"

    _backoff_spawn_to_past(121)  # n=2 → 间隔 240s，121s 前仍节流
    daemon_supervisor.ensure_scheduler()
    assert len(attempts) == 2


def test_backoff_capped_at_max(spawn_calls):
    """退避封顶 MAX_RESPAWN_SECONDS：n 再大也不超过 1800s。"""
    _scheduler_fail_count().write_text("10", encoding="utf-8")
    _backoff_spawn_to_past(daemon_supervisor.MAX_RESPAWN_SECONDS - 1)
    daemon_supervisor.ensure_scheduler()
    assert spawn_calls == []  # 差 1s 仍节流

    _backoff_spawn_to_past(daemon_supervisor.MAX_RESPAWN_SECONDS + 1)
    daemon_supervisor.ensure_scheduler()
    assert len(spawn_calls) == 1


def test_successful_spawn_does_not_increment_fail_count(spawn_calls):
    """spawn 成功只刷新时间戳，不计失败（计数只由健康观测归零）。"""
    daemon_supervisor.ensure_scheduler()
    assert len(spawn_calls) == 1
    assert not _scheduler_fail_count().exists()


def test_kg_vec_health_success_resets_backoff(spawn_calls, monkeypatch, tmp_path):
    """健康探测成功 = 崩溃循环结束：残留失败计数归零，且不拉起。"""
    monkeypatch.setattr(get_config(), "plugins", [PLUGIN_SPEC])
    monkeypatch.setattr(daemon_supervisor, "kg_vec_is_healthy", lambda url: True)
    fail_count = Path(daemon_supervisor.spawn_fail_count_path(daemon_supervisor.kg_vec_lock_path()))
    fail_count.write_text("5", encoding="utf-8")

    daemon_supervisor.ensure_kg_vec()
    assert spawn_calls == []
    assert not fail_count.exists()


def test_live_scheduler_instance_resets_backoff(spawn_calls):
    """scheduler 没有 /health：锁被活实例持有就是它的健康观测，归零退避。"""
    from cloudra.infra.flocks import try_acquire_lock
    from cloudra.scheduler.daemon import scheduler_lock_path

    fd = try_acquire_lock(scheduler_lock_path())
    assert fd is not None
    try:
        fail_count = _scheduler_fail_count()
        fail_count.write_text("3", encoding="utf-8")
        daemon_supervisor.ensure_scheduler()
        assert spawn_calls == []
        assert not fail_count.exists()
    finally:
        os.close(fd)
