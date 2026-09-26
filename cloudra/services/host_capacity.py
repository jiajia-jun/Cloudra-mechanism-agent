"""OS 实时余量观测：与节点调度总额度分开。

调度容量固定采用注册声明，作业成本按 req_memory_mb / req_cpus 记账。
OS 余量包含正在运行的作业消耗，不能作为总额度再扣账本，否则重复扣减。
探针只用于展示，不参与放行、存活或终态判定，绝不 kill 任何进程。
读不到时返回 None，并在状态翻转时记录 WARNING。

- 剩余内存 = free + inactive + speculative + purgeable（macOS vm_stat）。
- 空闲核数估计 = cpu_count - ceil(loadavg 1min)，仅作观测。
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

# 探针 TTL：vm_stat 是子进程，缓存避免容量视图频繁刷新时重复 fork。
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
            "OS availability will be omitted; scheduling quotas are unchanged",
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
    """调度总额度采用注册声明，不随 OS 实时余量缩减。"""
    return dict(declared)


def effective_node_resources(node) -> dict:
    """单个节点的固定调度额度；本机、SSH 与 Slurm 使用相同口径。"""
    return effective_resources(node.resources)


def node_capacities(registry) -> dict[str, dict]:
    """注册表全部节点的生效容量：``{node_id: {max_concurrent, cpus, memory_mb}}``。

    调度认领、队列视图、控制面 API 共用这一份口径——每个节点在自己额度内认领，
    互不占用（容量池解耦）。
    """
    return {node.node_id: effective_node_resources(node) for node in registry.nodes}


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
