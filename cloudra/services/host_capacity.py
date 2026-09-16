"""OS 实时余量探针：调度容量记账的"机器侧"输入。

调度容量 = min(注册节点声明 resources, OS 实时余量)，作业成本仍按 agent 声明的
``req_memory_mb`` / ``req_cpus`` 记账（声明口径）。OS 读数回答的是"这台机器现在
还剩多少"，因此天然涵盖**账本看不见的占用**：agent 绕过 ``submit_compute_job``
直调引擎起的作业、浏览器/IDE 等无关进程。

读数只用于**放行判定与展示**：不参与进程存活、终态判定，绝不 kill 任何进程
（存活一律 flock，见 AGENTS.md 执行面铁律）。探针读不到时返回 None，调用方
回落注册声明容量（不停摆），并在状态翻转时记一条 WARNING。

两个口径的定义：

- 剩余内存 = free + inactive + speculative + purgeable（macOS `vm_stat`）。
  只算 ``free`` 会得出"机器永远只剩 1 GB"的假象——macOS 把内存当文件缓存用；
  ``wired`` 与 compressor 占用的部分不可回收，本就不该算进余量。
- 可用核数 = ``cpu_count - ceil(loadavg 1min)``。1 分钟均值、零成本、不做进程名
  匹配；它偏向保守——我们自己起的作业也计入 load，形成自限。
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 探针 TTL：调度认领每 tick（1s）读一次容量，vm_stat 是子进程，缓存避免每 tick fork。
_PROBE_TTL_SECONDS = 5.0
_PROBE_TIMEOUT_SECONDS = 5

# macOS 可回收页类型：缺任一标签即判定读数不可用（不猜、不静默降级）
_VM_STAT_COUNTERS = (
    "Pages free",
    "Pages inactive",
    "Pages speculative",
    "Pages purgeable",
)

_cache: dict = {"at": 0.0, "memory_mb": None, "cpus": None, "warned": False}


def _reset_probe_cache_for_tests() -> None:
    _cache.update({"at": 0.0, "memory_mb": None, "cpus": None, "warned": False})


def _to_int(text: str) -> int | None:
    cleaned = text.strip().rstrip(".").strip()
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_vm_stat(text: str) -> int | None:
    """``vm_stat`` 文本 → 可回收内存 MB；页大小或任一计数缺失时返回 None。"""
    page_size: int | None = None
    counters: dict[str, int] = {}
    for line in text.splitlines():
        stripped = line.strip()
        tokens = stripped.split()
        if not tokens:
            continue
        if stripped.startswith("Mach Virtual Memory Statistics"):
            if "of" in tokens:
                idx = tokens.index("of")
                if idx + 1 < len(tokens):
                    page_size = _to_int(tokens[idx + 1])
            continue
        label, sep, value = stripped.partition(":")
        if not sep:
            continue
        parsed = _to_int(value)
        if parsed is not None:
            counters[label] = parsed
    if not page_size:
        return None
    pages = 0
    for label in _VM_STAT_COUNTERS:
        if label not in counters:
            return None
        pages += counters[label]
    return pages * page_size // (1024 * 1024)


def parse_meminfo(text: str) -> int | None:
    """``/proc/meminfo`` 文本 → ``MemAvailable`` MB；缺该行或单位不是 kB 时返回 None。"""
    for line in text.splitlines():
        label, sep, value = line.partition(":")
        if not sep or label.strip() != "MemAvailable":
            continue
        tokens = value.split()
        if not tokens:
            return None
        if len(tokens) > 1 and tokens[1] != "kB":
            return None
        kb = _to_int(tokens[0])
        return None if kb is None else kb // 1024
    return None


def _run_text(cmd: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _probe_memory_mb() -> int | None:
    if sys.platform == "darwin":
        text = _run_text(["vm_stat"])
        return parse_vm_stat(text) if text else None
    if sys.platform.startswith("linux"):
        try:
            text = Path("/proc/meminfo").read_text(encoding="utf-8")
        except OSError:
            return None
        return parse_meminfo(text)
    return None


def _probe_cpus() -> int | None:
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        return None
    return max(0, (os.cpu_count() or 1) - int(math.ceil(load1)))


def _refresh_cache(now: float) -> None:
    memory_mb = _probe_memory_mb()
    cpus = _probe_cpus()
    missing = memory_mb is None or cpus is None
    if missing and not _cache["warned"]:
        logger.warning(
            "host capacity probe unavailable (memory_mb=%s cpus=%s); "
            "falling back to the declared node resources",
            memory_mb,
            cpus,
        )
    _cache.update(
        {"at": now, "memory_mb": memory_mb, "cpus": cpus, "warned": bool(missing)}
    )


def _cached(*, refresh: bool) -> None:
    now = time.monotonic()
    if refresh or now - float(_cache["at"]) >= _PROBE_TTL_SECONDS:
        _refresh_cache(now)


def os_available_memory_mb(*, refresh: bool = False) -> int | None:
    """OS 报告的可回收内存 MB；本平台读不到返回 None。"""
    _cached(refresh=refresh)
    return _cache["memory_mb"]


def os_available_cpus(*, refresh: bool = False) -> int | None:
    """OS 报告的可用核数（cpu_count 减 1 分钟负载）；读不到返回 None。"""
    _cached(refresh=refresh)
    return _cache["cpus"]


def effective_resources(declared: dict) -> dict:
    """``min(注册声明, OS 实时余量)``；OS 侧读不到的项保持声明值。

    槽位 ``max_concurrent`` 不参与取小：它是注册声明里的调度上限，OS 侧没有
    对应读数，并发数由 CPU/内存记账间接约束。
    """
    effective = dict(declared)
    memory_mb = os_available_memory_mb()
    if memory_mb is not None:
        effective["memory_mb"] = min(int(declared.get("memory_mb", memory_mb)), memory_mb)
    cpus = os_available_cpus()
    if cpus is not None:
        effective["cpus"] = min(int(declared.get("cpus", cpus)), cpus)
    return effective


def capacity_report(declared: dict) -> dict:
    """容量视图（展示用）：注册声明 / OS 实时余量 / 生效值。"""
    return {
        "declared": dict(declared),
        "os_available": {
            "memory_mb": os_available_memory_mb(),
            "cpus": os_available_cpus(),
        },
        "effective": effective_resources(declared),
    }
