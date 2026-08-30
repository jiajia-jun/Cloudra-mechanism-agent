"""零部署兜底层：模糊匹配器单测 + provider 装配集成。"""

from __future__ import annotations

import csv
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cloudra.knowledge import fuzzy
from cloudra.knowledge import plugin as kg_plugin
from cloudra.knowledge.fuzzy import search as fuzzy_search
from cloudra.knowledge.plugin import ChemKBPlugin


@pytest.fixture(autouse=True)
def _clear_plugins():
    from cloudra.runtime_v2.plugins import clear_plugins

    clear_plugins()
    fuzzy._reset_cache()
    yield
    fuzzy._reset_cache()
    clear_plugins()


def write_cards(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({**r, "domain": r.get("domain", "d")}, ensure_ascii=False) + "\n")
    return path


@pytest.fixture
def cards_file(tmp_path: Path) -> Path:
    return write_cards(tmp_path / "cards.jsonl", [
        {"card_id": "kb:1:1", "blog_id": "1", "heading": "过渡态的定义",
         "content": "过渡态是势能面上的一阶鞍点。"},
        {"card_id": "kb:2:1", "blog_id": "2", "heading": "几何优化笔记",
         "content": "优化收敛技巧：先用小基组。过渡态搜索同理。"},
        {"card_id": "kb:3:1", "blog_id": "3", "heading": "Gaussian 赝势",
         "content": "GAUSSIAN 里赝势写法示例。"},
        {"card_id": "kb:4:1", "blog_id": "4", "heading": "光谱计算",
         "content": "拉曼光谱需要足够频率精度。"},
        {"card_id": "kb:5:1", "blog_id": "5", "heading": "过渡态搜索进阶",
         "content": "QST2 与 QST3 的初猜策略，结合 Gaussian 使用。"},
    ])


@pytest.fixture(autouse=True)
def _cards_default(cards_file, monkeypatch):
    # 默认指向 tmp cards；缺卡场景的用例自行覆盖指向不存在路径。
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: cards_file)


# ---------------------------------------------------------------- 匹配器

def test_chinese_substring_hit(cards_file):
    rows = fuzzy_search("过渡态", 10)
    assert {r["card_id"] for r in rows} == {"kb:1:1", "kb:2:1", "kb:5:1"}


def test_multi_token_and_semantics(cards_file):
    # 缺一不命中：kb:1 有"过渡态"无 Gaussian；kb:5 两者都有。
    rows = fuzzy_search("过渡态 Gaussian", 10)
    assert [r["card_id"] for r in rows] == ["kb:5:1"]


def test_ascii_case_insensitive(cards_file):
    assert {r["card_id"] for r in fuzzy_search("gaussian", 10)} == {"kb:3:1", "kb:5:1"}
    assert {r["card_id"] for r in fuzzy_search("GAUSSIAN", 10)} == {"kb:3:1", "kb:5:1"}


def test_deterministic_order_and_scores(cards_file):
    a = fuzzy_search("过渡态", 10)
    b = fuzzy_search("过渡态", 10)
    assert [(r["card_id"], r["score"]) for r in a] == [(r["card_id"], r["score"]) for r in b]


def test_heading_bonus_ranks_first(cards_file):
    rows = fuzzy_search("过渡态", 10)
    # kb:1/kb:5 heading 命中（0.6 加成）必须排在只有正文命中的 kb:2 前面。
    assert rows[-1]["card_id"] == "kb:2:1"
    assert {r["card_id"] for r in rows[:2]} == {"kb:1:1", "kb:5:1"}


def test_zero_hit_empty_query_and_limit(cards_file):
    assert fuzzy_search("不存在的词组xyz", 5) == []
    assert fuzzy_search("   ", 5) == []
    assert len(fuzzy_search("过渡态", 2)) == 2


def test_missing_cards_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: tmp_path / "absent.jsonl")
    assert fuzzy_search("过渡态", 5) == []


def test_query_truncated_to_200_cps(cards_file):
    # 200 码点之后的 token 被丢弃：zzz 不参与 AND，仍可命中。
    q = "过渡态" + " " * 197 + "zzz"
    assert len(q) > 200
    rows = fuzzy_search(q, 10)
    assert {r["card_id"] for r in rows} == {"kb:1:1", "kb:2:1", "kb:5:1"}


def test_cache_parsed_once_and_thread_safe(cards_file, monkeypatch):
    calls = {"n": 0}
    real_parse = fuzzy._parse

    def counting_parse(path):
        calls["n"] += 1
        return real_parse(path)

    monkeypatch.setattr(fuzzy, "_parse", counting_parse)
    fuzzy._reset_cache()
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        fuzzy_search("过渡态", 3)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls["n"] == 1  # 并发首查只解析一次


# ---------------------------------------------------------------- 集成（装配）

class _VecHandler(BaseHTTPRequestHandler):
    hits = []
    alive = True

    def do_POST(self) -> None:  # noqa: N802
        if not _VecHandler.alive:
            self.send_response(503)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        body = json.dumps({"hits": _VecHandler.hits}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def vec_server(monkeypatch):
    _VecHandler.hits = []
    _VecHandler.alive = True
    server = ThreadingHTTPServer(("127.0.0.1", 0), _VecHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
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
    with e_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "type", "label", "smiles", "props", "n_sources"])
        w.writeheader()
        w.writerows(ents)
    with r_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["src_id", "dst_id", "rel_type", "evidence_level",
                                           "source", "falsified", "note"])
        w.writeheader()
        w.writerows(rels)
    db = tmp_path / "knowledge" / "chem_kg.db"
    store.import_csv(db, e_csv, r_csv)
    monkeypatch.setattr(kg_plugin, "knowledge_graph_db_path", lambda: db)
    return db


def _card(card_id, blog_id, heading, score, content="卡片正文。"):
    return {"card_id": card_id, "blog_id": blog_id, "domain": "d",
            "heading": heading, "content": content, "score": score}


def test_service_dead_fuzzy_plus_graph(vec_server, kg_db, cards_file):
    _VecHandler.alive = False
    entries = ChemKBPlugin().search("过渡态", limit=5)
    cards = [e for e in entries if e.title.startswith("〔卡片·模糊〕")]
    graph = [e for e in entries if e.title.startswith("〔图谱〕")]
    assert len(entries) == 5
    assert len(cards) == 3  # 3 模糊 + 2 图谱：降级模式双通道叙事成立
    assert len(graph) == 2
    assert all(e.source.startswith("kb:") for e in entries)


def test_partial_semantic_dedup_topup(vec_server, kg_db, cards_file):
    # 服务活着但只回 1 条，且模糊层同卡命中 → card_id 去重不重复。
    _VecHandler.hits = [_card("kb:1:1", "1", "过渡态的定义", 0.9)]
    entries = ChemKBPlugin().search("过渡态", limit=5)
    sources = [e.source for e in entries]
    assert len(entries) == 5
    # 去重承诺作用于卡片通道（语义+模糊按 card_id）；图谱 source 是关系指针，
    # 不同实体可能合法地指向同一 kb: 卡。
    card_sources = [e.source for e in entries if not e.title.startswith("〔图谱〕")]
    assert len(set(card_sources)) == len(card_sources)
    assert sources.count("kb:1:1") == 1
    real = [e for e in entries if e.title.startswith("〔卡片〕")]
    fuzzy_hits = [e for e in entries if e.title.startswith("〔卡片·模糊〕")]
    assert len(real) == 1 and len(fuzzy_hits) == 2  # 补足语义槽
    assert len([e for e in entries if e.title.startswith("〔图谱〕")]) == 2


def test_full_semantic_fuzzy_lazy(vec_server, kg_db, cards_file):
    _VecHandler.hits = [
        _card(f"kb:9:{i}", "9", f"语义命中{i}", 0.8) for i in range(3)
    ]
    entries = ChemKBPlugin().search("过渡态", limit=5)
    assert len(entries) == 5
    assert len([e for e in entries if e.title.startswith("〔卡片〕")]) == 3
    assert not [e for e in entries if e.title.startswith("〔卡片·模糊〕")]  # 模糊层零参与


def test_all_missing_returns_empty(vec_server, tmp_path, monkeypatch, kg_db):
    _VecHandler.alive = False
    monkeypatch.setattr(kg_plugin, "knowledge_graph_db_path", lambda: tmp_path / "absent.db")
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: tmp_path / "absent.jsonl")
    assert ChemKBPlugin().search("过渡态", limit=5) == []
