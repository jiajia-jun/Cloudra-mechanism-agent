"""OS 余量探针与容量取小：解析、缓存、回落、min(声明, OS)。"""

from __future__ import annotations

import pytest

from cloudra import scheduler
from cloudra.scheduler import daemon
from cloudra.services import host_capacity as hc
from cloudra.services import nodes

# 真实 `vm_stat` 输出形态（值带尾点、含引号标签、含无关行）
VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               67483.
Pages active:                           1233232.
Pages inactive:                         1221100.
Pages speculative:                         8360.
Pages throttled:                              0.
Pages wired down:                        246428.
Pages purgeable:                           7136.
"Translation faults":                6180853587.
File-backed pages:                       790264.
"""

# 期望值 = (67483 + 1221100 + 8360 + 7136) * 16384 // 1024 // 1024
VM_STAT_MB = 20376

MEMINFO = """MemTotal:       528375528 kB
MemFree:         1056640 kB
MemAvailable:    20480000 kB
Buffers:           12345 kB
"""


@pytest.fixture(autouse=True)
def _clean_cache():
    hc._reset_probe_cache_for_tests()
    yield
    hc._reset_probe_cache_for_tests()


class _FakeNode:
    def __init__(self, resources, scheduler_type="local", node_id="workstation"):
        self.node_id = node_id
        self.resources = resources
        self.scheduler = {"type": scheduler_type}


class _FakeRegistry:
    """只实现容量路径用到的表面：nodes 遍历 + default_node_id。"""

    def __init__(self, node):
        self._node = node
        self.nodes = () if node is None else (node,)
        self.default_node_id = getattr(node, "node_id", "workstation")

    def node(self, node_id=None):
        return self._node


def test_parse_vm_stat_reclaimable_memory():
    assert hc.parse_vm_stat(VM_STAT) == VM_STAT_MB


def test_parse_vm_stat_missing_counter_or_page_size_is_none():
    assert hc.parse_vm_stat(VM_STAT.replace("Pages purgeable:                           7136.\n", "")) is None
    assert hc.parse_vm_stat(VM_STAT.replace("page size of 16384 bytes", "page size unknown")) is None
    assert hc.parse_vm_stat("") is None


def test_parse_meminfo_available_only():
    assert hc.parse_meminfo(MEMINFO) == 20480000 // 1024
    assert hc.parse_meminfo("MemTotal:  528375528 kB\n") is None
    assert hc.parse_meminfo("MemAvailable: 20480000 MB\n") is None


def test_memory_probe_is_cached_and_refreshable(monkeypatch):
    calls: list = []
    monkeypatch.setattr(hc, "_probe_memory_mb", lambda: calls.append(1) or VM_STAT_MB)

    assert hc.os_available_memory_mb() == VM_STAT_MB
    assert hc.os_available_memory_mb() == VM_STAT_MB
    assert len(calls) == 1  # TTL 内不重复探测（认领每 tick 都读容量）

    hc.os_available_memory_mb(refresh=True)
    assert len(calls) == 2


def test_probe_memory_mb_dispatch(monkeypatch):
    monkeypatch.setattr(hc.sys, "platform", "darwin")
    monkeypatch.setattr(hc, "_run_text", lambda cmd: VM_STAT if cmd == ["vm_stat"] else None)
    assert hc._probe_memory_mb() == VM_STAT_MB

    monkeypatch.setattr(hc.sys, "platform", "freebsd14")
    assert hc._probe_memory_mb() is None


def test_available_cpus_from_loadavg(monkeypatch):
    monkeypatch.setattr(hc.os, "getloadavg", lambda: (11.37, 11.07, 10.40))
    monkeypatch.setattr(hc.os, "cpu_count", lambda: 18)
    assert hc.os_available_cpus() == 18 - 12

    monkeypatch.setattr(hc.os, "getloadavg", lambda: (99.0, 1.0, 1.0))
    hc._reset_probe_cache_for_tests()
    assert hc.os_available_cpus() == 0  # 饱和时报 0，放行侧由 max(1, ...) 兜底


def test_effective_resources_takes_min(monkeypatch):
    declared = {"max_concurrent": 10, "cpus": 18, "memory_mb": 40960}
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: VM_STAT_MB)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 6)

    assert hc.effective_resources(declared) == {
        "max_concurrent": 10,  # 槽位是注册声明，不参与取小
        "cpus": 6,
        "memory_mb": VM_STAT_MB,
    }


def test_effective_resources_keeps_declared_when_os_is_roomier(monkeypatch):
    declared = {"max_concurrent": 10, "cpus": 18, "memory_mb": 40960}
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: 100_000)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 64)
    assert hc.effective_resources(declared) == declared


def test_effective_resources_falls_back_to_declared_when_probe_unavailable(monkeypatch):
    declared = {"max_concurrent": 10, "cpus": 18, "memory_mb": 40960}
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: None)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: None)
    assert hc.effective_resources(declared) == declared


def test_capacity_report_exposes_all_three_layers(monkeypatch):
    declared = {"max_concurrent": 10, "cpus": 18, "memory_mb": 40960}
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: VM_STAT_MB)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 6)

    report = hc.capacity_report(declared)
    assert report["declared"] == declared
    assert report["os_available"] == {"memory_mb": VM_STAT_MB, "cpus": 6}
    assert report["effective"]["memory_mb"] == VM_STAT_MB


DECLARED = {"max_concurrent": 10, "cpus": 18, "memory_mb": 40960}


def _patch_node(monkeypatch, node, *, raises=False):
    def _from_environment(cls=None):
        if raises:
            raise RuntimeError("registry broken")
        return _FakeRegistry(node)

    monkeypatch.setattr(nodes.NodeRegistry, "from_environment", _from_environment)


def test_node_capacities_apply_host_limits(monkeypatch):
    """本机 local 节点：生效容量 = min(声明, OS 余量)，按 node_id 分池返回。"""
    _patch_node(monkeypatch, _FakeNode(dict(DECLARED)))
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: VM_STAT_MB)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 6)

    capacities, default_node_id = daemon._node_capacities()

    assert capacities == {
        "workstation": {"max_concurrent": 10, "cpus": 6, "memory_mb": VM_STAT_MB}
    }
    assert default_node_id == "workstation"


def test_node_capacities_ignore_host_limits_for_slurm(monkeypatch):
    """远端/集群节点不在这台机器上跑：OS 读数与它无关，原样用注册声明。"""
    _patch_node(monkeypatch, _FakeNode(dict(DECLARED), scheduler_type="slurm"))
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: 1)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: 1)

    capacities, _default = daemon._node_capacities()

    assert capacities == {"workstation": DECLARED}


def test_node_capacities_survive_broken_registry(monkeypatch):
    _patch_node(monkeypatch, None, raises=True)
    monkeypatch.setattr(hc, "os_available_memory_mb", lambda **_: None)
    monkeypatch.setattr(hc, "os_available_cpus", lambda **_: None)

    capacities, default_node_id = daemon._node_capacities()

    assert capacities == {default_node_id: nodes.default_resources()}


def test_scheduler_module_import_path_unchanged():
    """守护入口仍从 cloudra.scheduler 暴露（守护拉起链路依赖它）。"""
    assert scheduler.daemon is daemon
