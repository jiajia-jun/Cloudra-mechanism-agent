"""chem-kb 混合 provider：配额、缝合、降级矩阵与故障隔离。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cloudra.knowledge import plugin as kg_plugin
from cloudra.knowledge.plugin import ChemKBPlugin


@pytest.fixture(autouse=True)
def _clear_plugins():
    from cloudra.runtime_v2.plugins import clear_plugins

    clear_plugins()
    yield
    clear_plugins()


class _VecHandler(BaseHTTPRequestHandler):
    hits = []  # class 级注入，测试可改

    def do_POST(self) -> None:  # noqa: N802  # 插件走 POST /search
        if self.path.startswith("/search"):
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            body = json.dumps({"hits": _VecHandler.hits}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def vec_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _VecHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", f"http://127.0.0.1:{server.server_address[1]}")
    yield server
    server.shutdown()


@pytest.fixture
def kg_db(tmp_path: Path, monkeypatch) -> Path:
    from cloudra.knowledge import store

    ents = [
        {"id": "concept:过渡态", "type": "concept", "label": "过渡态", "n_sources": "1"},
        {"id": "method:过渡态搜索", "type": "method", "label": "过渡态搜索", "n_sources": "1"},
        {"id": "software:Gaussian", "type": "software", "label": "Gaussian", "n_sources": "1"},
    ]
    rels = [
        {"src_id": "method:过渡态搜索", "dst_id": "concept:过渡态", "rel_type": "applies_to",
         "source": "kb:10", "evidence_level": "L0"},
        {"src_id": "software:Gaussian", "dst_id": "method:过渡态搜索", "rel_type": "part_of",
         "source": "kb:77", "evidence_level": "L0"},
    ]
    e_csv, r_csv = tmp_path / "e.csv", tmp_path / "r.csv"
    import csv as _csv

    with e_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=["id", "type", "label", "smiles", "props", "n_sources"])
        w.writeheader()
        w.writerows(ents)
    with r_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=["src_id", "dst_id", "rel_type", "evidence_level",
                                           "source", "falsified", "note"])
        w.writeheader()
        w.writerows(rels)
    db = tmp_path / "knowledge" / "chem_kg.db"
    store.import_csv(db, e_csv, r_csv)
    monkeypatch.setattr(kg_plugin, "knowledge_graph_db_path", lambda: db)
    return db


def _hits(card_id, blog_id, heading, score, content="卡片正文内容。"):
    _VecHandler.hits = [
        {"card_id": card_id, "blog_id": blog_id, "domain": "d", "heading": heading,
         "content": content, "score": score},
    ]


def test_quota_3_plus_2_structural(vec_server, kg_db):
    # 构造语义高分场景：图谱通道必须不被挤掉（配额是结构性的）。
    _VecHandler.hits = [
        {"card_id": f"kb:1:{i}", "blog_id": "1", "heading": f"语义命中{i}",
         "content": "c", "score": 0.99} for i in range(3)
    ]
    entries = ChemKBPlugin().search("过渡态", limit=5)
    assert len(entries) == 5
    cards = [e for e in entries if e.title.startswith("〔卡片〕")]
    graph = [e for e in entries if e.title.startswith("〔图谱〕")]
    assert len(cards) == 3
    assert len(graph) == 2  # 高分语义命中也挤不掉图谱配额


def test_title_prefixes_and_sources(vec_server, kg_db):
    _hits("kb:10:1", "10", "弥散函数", 0.5)
    entries = ChemKBPlugin().search("过渡态", limit=5)
    assert any(e.title.startswith("〔卡片〕") for e in entries)
    assert any(e.title.startswith("〔图谱〕") for e in entries)
    for e in entries:
        assert e.source  # 每条带出处（card_id 或 kb: 指针）
        assert e.evidence_level == "L0"


def test_stitch_only_when_card_has_relations(vec_server, kg_db):
    _hits("kb:10:1", "10", "有关系的卡", 0.9)
    _VecHandler.hits.append({"card_id": "kb:999:1", "blog_id": "999",
                             "heading": "没关系的卡", "content": "无关系正文。", "score": 0.8})
    entries = ChemKBPlugin().search("过渡态", limit=5)
    by_title = {e.title: e for e in entries}
    stitched = by_title.get("〔卡片〕有关系的卡")
    lonely = by_title.get("〔卡片〕没关系的卡")
    assert stitched and "‖图:" in stitched.content
    assert lonely and "‖图:" not in lonely.content


def test_degradation_service_dead_kg_only(kg_db, monkeypatch):
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", "http://127.0.0.1:1")  # 无人监听
    entries = ChemKBPlugin().search("过渡态", limit=5)
    assert entries and len(entries) == 3  # KG-only 补满配额（库内可命中实体共 3 个）
    assert all(e.title.startswith("〔图谱〕") for e in entries)


def test_degradation_no_db_semantic_only(vec_server, tmp_path, monkeypatch):
    monkeypatch.setattr(kg_plugin, "knowledge_graph_db_path", lambda: tmp_path / "absent.db")
    _VecHandler.hits = [
        {"card_id": f"kb:1:{i}", "blog_id": "1", "heading": f"语义命中{i}",
         "content": "c", "score": 0.9} for i in range(5)
    ]
    entries = ChemKBPlugin().search("过渡态", limit=5)
    assert entries and len(entries) == 5
    assert all(e.title.startswith("〔卡片〕") for e in entries)
    assert not (tmp_path / "absent.db").exists()  # 缺库不建库不抛


def test_degradation_both_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(kg_plugin, "knowledge_graph_db_path", lambda: tmp_path / "absent.db")
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", "http://127.0.0.1:1")
    assert ChemKBPlugin().search("过渡态", limit=5) == []


def test_limit_lt_2_keeps_one_each(vec_server, kg_db):
    entries = ChemKBPlugin().search("过渡态", limit=1)
    assert 1 <= len(entries) <= 2  # 各保 1，最终按 limit 截


def test_malicious_provider_does_not_break_hub_search(vec_server, kg_db):
    # 两个维度的故障隔离：
    # ① 恶意 provider 的 search() 抛异常 → 被 search_library 的异常隔离跳过；
    # ② 本插件只返回 KnowledgeEntry 实例（dict 路径的 float() 会穿透异常
    #    隔离炸掉 hub search，这是 runtime_v2 的已知脆弱面，绝不走）。
    import asyncio

    from cloudra.runtime_v2.knowledge import KnowledgeEntry, search_library
    from cloudra.runtime_v2.plugins import register_plugin

    class Malicious:
        name = "malicious"

        def search(self, query, *, limit=5):
            raise RuntimeError("boom")

    register_plugin(Malicious())
    register_plugin(ChemKBPlugin())
    for e in ChemKBPlugin().search("过渡态", limit=5):
        assert isinstance(e, KnowledgeEntry)
    hits = asyncio.run(search_library("过渡态", limit=5))
    assert hits  # hub search 未失败
    assert {h["provider"] for h in hits} == {"chem-kb"}


def test_activated_plugin_search_library_hits(vec_server, kg_db):
    import asyncio

    from cloudra.runtime_v2.knowledge import search_library
    from cloudra.runtime_v2.plugins import register_plugin

    _hits("kb:10:1", "10", "弥散函数", 0.5)
    register_plugin(kg_plugin.plugin)
    hits = asyncio.run(search_library("过渡态", limit=5))
    providers = {h["provider"] for h in hits}
    assert providers == {"chem-kb"}
    assert hits, "激活后 search_library 必须命中"
    assert all(h["source"] for h in hits)
