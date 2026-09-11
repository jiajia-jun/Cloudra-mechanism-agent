"""chem-kb 混合 provider：配额、缝合、降级矩阵与故障隔离。

v10 起语义通道有模糊兜底层（``cloudra/knowledge/fuzzy.py``）。本文件默认
把 ``fuzzy._cards_file`` 指向不存在的路径（隔离出 v9.1 行为域）；涉及新
退化矩阵（3 模糊 + 2 图谱）的用例在 ``test_knowledge_fuzzy.py``，或在此
显式覆盖 cards 路径。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cloudra.knowledge import fuzzy
from cloudra.knowledge import plugin as kg_plugin
from cloudra.knowledge.plugin import ChemKBPlugin


@pytest.fixture(autouse=True)
def _clear_plugins(tmp_path, monkeypatch):
    from cloudra.runtime_v2.plugins import clear_plugins

    clear_plugins()
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: tmp_path / "no-cards-in-these-tests.jsonl")
    fuzzy._reset_cache()
    yield
    fuzzy._reset_cache()
    clear_plugins()


class _VecHandler(BaseHTTPRequestHandler):
    hits = []  # class 级注入，测试可改
    requests: list[dict] = []  # 记录每个 POST /search 的请求体（v13 路由断言用）
    respond = None  # 可选 callable(body)->hits：按请求体动态应答，优先于静态 hits

    def do_POST(self) -> None:  # noqa: N802  # 插件走 POST /search
        if self.path.startswith("/search"):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:  # noqa: BLE001 — 畸形体不阻断假服务
                body = {}
            _VecHandler.requests.append(body)
            hits = _VecHandler.respond(body) if _VecHandler.respond else _VecHandler.hits
            payload = json.dumps({"hits": hits}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
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
    _VecHandler.requests = []
    _VecHandler.hits = []
    _VecHandler.respond = None
    yield server
    server.shutdown()
    _VecHandler.requests = []
    _VecHandler.hits = []
    _VecHandler.respond = None


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


def test_degradation_service_dead_no_cards_still_kg_only(kg_db, monkeypatch, tmp_path):
    # v10 回归：cards.jsonl 缺失（fuzzy._cards_file 已被 autouse 指向不存在路径）
    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", "http://127.0.0.1:1")
    entries = ChemKBPlugin().search("过渡态", limit=5)
    assert len(entries) == 3
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


# ---------------------------------------------------------------------------
# v13：报错签名路由 / lang 传递 / 回退 / 旧库降级
# ---------------------------------------------------------------------------

def test_error_query_routes_tags_to_both_channels(vec_server, kg_db):
    """查询含报错签名（L502）→ 语义请求带 tags 过滤，不抛、照常返回。"""
    _VecHandler.hits = [
        {"card_id": "kb:164:1", "blog_id": "164", "heading": "SCF不收敛解决",
         "content": "c", "score": 0.9, "tags": {"error": ["err_l502"]}},
    ]
    entries = ChemKBPlugin().search("opt 失败 Convergence failure -- L502", limit=5)
    assert entries, "报错路由下仍必须有结果"
    sem_reqs = [r for r in _VecHandler.requests if r.get("query")]
    assert sem_reqs and sem_reqs[0].get("tags") == {"error": ["err_l502"]}


def test_error_filtered_semantic_empty_retries_once_without_tags(vec_server, kg_db):
    """报错过滤命中为空（服务忽略 tags 返回 []）→ 每个"带 tags 且空"的语义
    请求后必须紧跟一个同 k 的无 tags 内部回退（放大重取会再次带 tags，
    同样适用该契约）。"""
    _VecHandler.hits = []
    ChemKBPlugin().search("SCF has not converged during opt", limit=5)
    reqs = [r for r in _VecHandler.requests if r.get("query")]
    assert len(reqs) >= 2, "过滤空必须触发无 tags 回退重试"
    assert reqs[0].get("tags") == {"error": ["err_scf_not_converged"]}
    for i, req in enumerate(reqs):
        if req.get("tags"):
            assert i + 1 < len(reqs), "带 tags 请求返回空后必须有回退请求"
            nxt = reqs[i + 1]
            assert not nxt.get("tags") and nxt.get("k") == req.get("k"), \
                "回退请求不得带 tags 且 k 必须一致"


def test_ascii_query_passes_lang_and_zh_query_does_not(vec_server, kg_db):
    _VecHandler.hits = []
    ChemKBPlugin().search("SCF convergence failure troubleshooting", limit=5)
    en_reqs = [r for r in _VecHandler.requests if r.get("query")]
    assert en_reqs and en_reqs[0].get("lang") == "en"

    _VecHandler.requests = []
    ChemKBPlugin().search("过渡态搜索", limit=5)
    zh_reqs = [r for r in _VecHandler.requests if r.get("query")]
    assert zh_reqs and not zh_reqs[0].get("lang")


def test_vocab_missing_disables_routing_gracefully(vec_server, kg_db, monkeypatch):
    """词表损坏/缺失 → 路由静默禁用：请求不带 tags，不抛异常。"""
    import cloudra.knowledge.tagging as tagging_mod

    def _boom(_path=None):
        raise OSError("vocab gone")

    monkeypatch.setattr(tagging_mod.TagVocab, "load", staticmethod(_boom))
    p = ChemKBPlugin()
    entries = p.search("L502 convergence failure", limit=5)
    assert isinstance(entries, list)  # 不抛即通过
    reqs = [r for r in _VecHandler.requests if r.get("query")]
    assert reqs and not reqs[0].get("tags"), "词表缺失时不得带 tags 过滤"


def test_old_schema_db_with_facets_degrades_to_unfiltered(kg_db, monkeypatch):
    """P0 回归：v12 旧库（无 kg_entity_tags 表）+ 报错签名查询 → 不抛，
    降级为无过滤图谱检索（与 v12 行为一致）。"""
    from cloudra.knowledge import store

    con = store._open_rw(kg_db)
    con.execute("DROP TABLE kg_entity_tags")
    con.commit()
    con.close()

    rows = store.search_graph(kg_db, "过渡态", limit=5,
                              facets={"error": ["err_l502"]})
    assert rows, "旧库 facet 查询必须降级为无过滤并正常返回"

    monkeypatch.setenv("CLOUDRA_KG_VEC_URL", "http://127.0.0.1:1")  # 语义通道死
    p = ChemKBPlugin()
    p._vocab = False  # 跳过词表加载，单测图谱路径
    entries = p._graph_channel(kg_db, "过渡态", 2, error_tags=["err_l502"])
    assert entries, "plugin 图谱通道在旧库 + error_tags 下不得抛错"


def test_error_filtered_hits_survive_graph_empty_enlarged_refetch(vec_server, kg_db):
    """P1 回归（轮 2）：图谱通道空 → 放大重取语义时必须保留报错过滤——
    带 tags 请求返回 1 条高相关卡（0.95），无 tags 请求返回 5 条泛化卡（0.3）。
    修复前：无 tags 放大重取整体覆盖 sem，高相关卡被泛化卡顶掉。"""
    def _respond(body: dict) -> list:
        if body.get("tags"):
            return [{"card_id": "kb:164:1", "blog_id": "164", "heading": "SCF不收敛高相关",
                     "content": "c", "score": 0.95, "tags": {"error": ["err_scf_not_converged"]}}]
        return [{"card_id": f"kb:9:{i}", "blog_id": "9", "heading": f"泛化卡{i}",
                 "content": "c", "score": 0.3, "tags": {}} for i in range(5)]

    _VecHandler.respond = _respond
    # 英文报错查询：kg_db 的中文实体对它 0 命中 → 走"图谱死"补位路径
    entries = ChemKBPlugin().search("SCF has not converged during opt", limit=5)
    assert any("SCF不收敛高相关" in e.title for e in entries), \
        "报错过滤命中的高相关卡不得被无 tags 放大重取覆盖"
