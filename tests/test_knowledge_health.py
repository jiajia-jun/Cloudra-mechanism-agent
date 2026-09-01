"""chem-kb 三通道健康聚合（knowledge/health.py）、plugin 语义通道健康记录、
knowledge health API 与 `cloudra knowledge status` CLI 冒烟。

语义通道异常路径在旧实现上必须红：裸 except 静默吞掉、没有 last_health。
"""

from __future__ import annotations

import csv
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cloudra.knowledge import fuzzy, store
from cloudra.knowledge import plugin as kg_plugin
from cloudra.knowledge.plugin import ChemKBPlugin


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """默认全缺省：语义指死端口、模糊层指不存在文件、图谱库缺席（conftest 隔离 data_dir）。
    需要活服务/真文件的用例在测试内后覆盖（后应用的 monkeypatch 生效）。"""
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: tmp_path / "no-cards.jsonl")
    fuzzy._reset_cache()
    yield
    fuzzy._reset_cache()


class _VecHandler(BaseHTTPRequestHandler):
    hits: list = []

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            self._json({"ok": True, "model": "bge-m3", "library_model": "bge-m3", "count": 4})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/search"):
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self._json({"hits": _VecHandler.hits})
        else:
            self._json({"error": "not found"}, 404)

    def _json(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def vec_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _VecHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", f"http://127.0.0.1:{server.server_address[1]}")
    yield server
    server.shutdown()
    _VecHandler.hits = []


# ---------------------------------------------------------------- plugin 语义通道留痕


def test_semantic_channel_error_is_recorded(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated transport failure")

    monkeypatch.setattr(kg_plugin.httpx, "post", _boom)
    plugin = ChemKBPlugin()
    assert plugin._semantic_channel("过渡态", 3) == []  # 仍然绝不抛、通道为空
    assert plugin.last_health is not None
    assert plugin.last_health["ok"] is False
    assert "simulated transport failure" in plugin.last_health["error"]
    assert plugin.last_health["at"]


def test_semantic_channel_success_is_recorded(vec_server):
    _VecHandler.hits = [
        {"card_id": "kb:1:0", "blog_id": "1", "heading": "h", "content": "c", "score": 0.9}
    ]
    plugin = ChemKBPlugin()
    entries = plugin._semantic_channel("anything", 2)
    assert entries
    assert plugin.last_health is not None
    assert plugin.last_health["ok"] is True
    assert "error" not in plugin.last_health


def test_plugin_health_live_ok(vec_server):
    h = ChemKBPlugin().health()
    assert h["ok"] is True
    assert h["model"] == "bge-m3"
    assert h["count"] == 4
    assert h["url"].startswith("http://127.0.0.1:")


def test_plugin_health_dead_has_error():
    h = ChemKBPlugin().health()
    assert h["ok"] is False
    assert h["error"]
    assert h["url"] == "http://127.0.0.1:1"


def test_plugin_health_surfaces_last_search_error():
    plugin = ChemKBPlugin()
    plugin._semantic_channel("q", 1)  # 死端口 → last_health 记录失败
    h = plugin.health()
    assert h["ok"] is False
    assert h.get("last_error")


# ---------------------------------------------------------------- 三通道聚合


def _build_db(tmp_path: Path) -> Path:
    e_csv = tmp_path / "e.csv"
    with e_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "type", "label", "smiles", "props", "n_sources"])
        w.writeheader()
        w.writerow({"id": "concept:过渡态", "type": "concept", "label": "过渡态", "n_sources": "1"})
    r_csv = tmp_path / "r.csv"
    r_csv.write_text("src_id,dst_id,rel_type,evidence_level,source,falsified,note\n",
                     encoding="utf-8-sig")
    db = tmp_path / "knowledge" / "chem_kg.db"
    store.import_csv(db, e_csv, r_csv)
    return db


def test_knowledge_health_all_channels_down():
    from cloudra.knowledge.health import knowledge_health

    health = knowledge_health()
    assert set(health) == {"semantic", "graph", "fuzzy"}
    for channel in health.values():
        assert channel["ok"] is False
        assert channel["error"]


def test_graph_channel_ok_with_real_db(tmp_path):
    from cloudra.knowledge.health import graph_health

    h = graph_health(_build_db(tmp_path))
    assert h == {"ok": True, "entities": 1, "relations": 0}


def test_fuzzy_channel_ok_with_cards(tmp_path, monkeypatch):
    from cloudra.knowledge.health import fuzzy_health

    cards = tmp_path / "cards.jsonl"
    cards.write_text(
        "\n".join(
            json.dumps({"card_id": f"kb:1:{i}", "heading": f"h{i}", "content": "c"})
            for i in range(3)
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: cards)
    fuzzy._reset_cache()
    assert fuzzy_health() == {"ok": True, "cards": 3}


def test_semantic_channel_ok_with_live_service(vec_server):
    from cloudra.knowledge.health import semantic_health

    h = semantic_health()
    assert h["ok"] is True
    assert h["count"] == 4


# ---------------------------------------------------------------- API 与 CLI


def test_knowledge_health_api_route():
    from fastapi.testclient import TestClient

    from cloudra.services.api_v2 import create_v2_app

    client = TestClient(create_v2_app())
    resp = client.get("/api/v2/knowledge/health")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"semantic", "graph", "fuzzy"}
    assert all("ok" in channel for channel in body.values())


def test_knowledge_status_cli_smoke():
    from click.testing import CliRunner

    from cloudra.cli import cli

    result = CliRunner().invoke(cli, ["knowledge", "status"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "chem-kb" in result.output
    # 本文件 fixture 下三通道全缺：三个失败标记
    assert result.output.count("✗") == 3
