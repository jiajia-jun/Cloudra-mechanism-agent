"""Full-history exports stream records to disk without duplicating the history."""

import asyncio
import json
import threading
import time
import tracemalloc
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cloudra.runtime_v2.persistence import RuntimeStore
from cloudra.services import telemetry
from cloudra.services.api_v2 import create_v2_app
from tests.test_telemetry import _envelope


def test_session_export_memory_does_not_retain_all_raw_events(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    for index in range(120):
        store.append_event(_envelope(index + 1, "tool.result_recorded", {"raw": "x" * 32768}))
    tracemalloc.start()
    try:
        count = telemetry.write_session_jsonl(store.path, "s1", tmp_path / "s1.jsonl")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert count == 122  # meta + 120 events + final context
    assert peak < 2 * 1024 * 1024


def test_project_zip_reuses_streaming_session_records(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path / "runtime.db")
    store.append_event(_envelope(1, "llm.completed", {"model": "m", "usage": {"prompt_tokens": 2}}))

    def reject(*args, **kwargs):
        raise AssertionError("export must not materialize an events list")

    monkeypatch.setattr(telemetry, "load_events", reject)
    output = tmp_path / "p1.zip"
    assert telemetry.write_project_zip(store.path, "p1", output) == {"sessions": 1}
    with zipfile.ZipFile(output) as archive:
        records = [json.loads(line) for line in archive.read("s1.jsonl").decode().splitlines()]
    assert [record["type"] for record in records] == ["meta", "event", "context", "usage"]
    assert records[-1]["prompt_tokens"] == 2


def test_session_export_keeps_one_fixed_history_prefix(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    store.append_event(_envelope(1, "llm.completed", {"usage": {"prompt_tokens": 2}}))
    records = telemetry.build_session_export(store.path, "s1")
    store.append_event(_envelope(2, "llm.completed", {"usage": {"prompt_tokens": 9}}))
    exported = list(records)
    assert exported[0]["event_count"] == 1
    assert exported[0]["llm_calls"] == 1
    assert len([record for record in exported if record["type"] == "event"]) == 1
    assert [record["prompt_tokens"] for record in exported if record["type"] == "usage"] == [2]


@pytest.mark.asyncio
async def test_export_download_builds_are_serialized_and_files_are_removed(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path / "runtime.db")
    active, peak = 0, 0
    outputs = []
    lock = threading.Lock()

    def write(db_path, project_id, out_path):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            outputs.append(Path(out_path))
            time.sleep(0.04)
            Path(out_path).write_bytes(b"small export")
            return {"sessions": 1}
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(telemetry, "write_project_zip", write)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(store_path=store.path)),
                           base_url="http://testserver") as client:
        responses = await asyncio.gather(*[
            client.get("/api/v2/telemetry/export/project/p1") for _ in range(3)
        ])
    assert all(response.status_code == 200 for response in responses)
    assert all(response.content == b"small export" for response in responses)
    assert peak == 1
    assert outputs and not any(path.exists() for path in outputs)


@pytest.mark.asyncio
async def test_session_download_reuses_disk_writer(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path / "runtime.db")
    store.append_event(_envelope(1, "llm.completed", {"usage": {}}))
    written = []
    original = telemetry.write_session_jsonl

    def write(db_path, session_id, out_path):
        written.append(Path(out_path))
        return original(db_path, session_id, out_path)

    monkeypatch.setattr(telemetry, "write_session_jsonl", write)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(store_path=store.path)),
                           base_url="http://testserver") as client:
        response = await client.get("/api/v2/telemetry/export/session/s1")
    assert response.status_code == 200
    assert written and not written[0].exists()
    assert json.loads(response.text.splitlines()[0])["type"] == "meta"


@pytest.mark.asyncio
async def test_export_failure_removes_partial_file(tmp_path, monkeypatch):
    from cloudra.services.api_v2.routers import telemetry as routes

    store = RuntimeStore(tmp_path / "runtime.db")
    outputs = []
    mkstemp = routes.tempfile.mkstemp

    def temporary(**kwargs):
        fd, path = mkstemp(**kwargs)
        outputs.append(Path(path))
        return fd, path

    def fail(*args):
        Path(args[-1]).write_text("partial output")
        raise RuntimeError("export failed")

    monkeypatch.setattr(routes.tempfile, "mkstemp", temporary)
    monkeypatch.setattr(telemetry, "write_project_zip", fail)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(store_path=store.path),
                                                 raise_app_exceptions=False),
                           base_url="http://testserver") as client:
        response = await client.get("/api/v2/telemetry/export/project/p1")
    assert response.status_code == 500
    assert outputs and not any(path.exists() for path in outputs)


@pytest.mark.asyncio
async def test_cancelled_export_keeps_shared_slot_until_worker_exits(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path / "runtime.db")
    entered, release = threading.Event(), threading.Event()
    outputs = []

    def write(db_path, ident, out_path):
        outputs.append(Path(out_path))
        if ident == "first":
            entered.set()
            assert release.wait(2)
        Path(out_path).write_bytes(b"export")
        return {"sessions": 1}

    monkeypatch.setattr(telemetry, "write_session_jsonl", write)
    monkeypatch.setattr(telemetry, "write_project_zip", write)
    async with AsyncClient(transport=ASGITransport(app=create_v2_app(store_path=store.path)),
                           base_url="http://testserver") as client:
        first = asyncio.create_task(client.get("/api/v2/telemetry/export/session/first"))
        second = None
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            first.cancel()
            second = asyncio.create_task(client.get("/api/v2/telemetry/export/project/second"))
            await asyncio.sleep(0.03)
            assert len(outputs) == 1
        finally:
            release.set()
            await asyncio.gather(first, return_exceptions=True)
        assert (await second).status_code == 200
    assert len(outputs) == 2
    assert not any(path.exists() for path in outputs)
