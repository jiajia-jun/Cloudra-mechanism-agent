"""DeviceBroker 进程级缓存测试：同一数据目录只初始化一次（DDL 幂等）。"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from cloudra.device_broker import DeviceBroker, get_device_broker


def test_get_device_broker_caches_per_data_dir(tmp_path):
    first = get_device_broker(tmp_path)
    second = get_device_broker(tmp_path)
    assert first is second

    other = get_device_broker(tmp_path / "other")
    assert other is not first


def test_get_device_broker_runs_init_once(tmp_path, monkeypatch):
    calls = 0
    original_init = DeviceBroker._init

    def counting_init(self):
        nonlocal calls
        calls += 1
        original_init(self)

    monkeypatch.setattr(DeviceBroker, "_init", counting_init)

    for _ in range(5):
        get_device_broker(tmp_path)
    assert calls == 1


def test_get_device_broker_single_init_under_thread_race(tmp_path, monkeypatch):
    calls = 0
    calls_lock = threading.Lock()
    original_init = DeviceBroker._init

    def counting_init(self):
        nonlocal calls
        with calls_lock:
            calls += 1
        original_init(self)

    monkeypatch.setattr(DeviceBroker, "_init", counting_init)

    with ThreadPoolExecutor(max_workers=8) as pool:
        brokers = list(pool.map(lambda _i: get_device_broker(tmp_path), range(32)))

    assert len({id(broker) for broker in brokers}) == 1
    assert calls == 1


def test_get_device_broker_query_semantics_unchanged(tmp_path):
    """缓存实例的查询结果与新建实例一致（实时读，不缓存查询结果）。"""
    cached = get_device_broker(tmp_path)
    fresh = DeviceBroker(tmp_path)
    assert cached.list_devices() == fresh.list_devices() == []
    assert cached.available_tool_names() == fresh.available_tool_names() == set()
