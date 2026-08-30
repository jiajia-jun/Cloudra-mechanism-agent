"""v11 双语适配：props.label_en 进 FTS、ASCII 启发、service lang/去重、中文回归。"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

from cloudra.knowledge import fuzzy, store
from cloudra.knowledge import plugin as kg_plugin
from cloudra.knowledge.plugin import ChemKBPlugin

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_plugins(tmp_path, monkeypatch):
    from cloudra.runtime_v2.plugins import clear_plugins

    clear_plugins()
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: tmp_path / "no-cards.jsonl")
    fuzzy._reset_cache()
    yield
    fuzzy._reset_cache()
    clear_plugins()


@pytest.fixture
def bilingual_db(tmp_path: Path) -> Path:
    ents = [
        {"id": "concept:过渡态", "type": "concept", "label": "过渡态", "n_sources": "2",
         "props": '{"label_en": "transition state"}'},
        {"id": "concept:虚频", "type": "concept", "label": "虚频", "n_sources": "1",
         "props": '{"label_en": "imaginary frequency"}'},
        {"id": "software:Gaussian", "type": "software", "label": "Gaussian",
         "n_sources": "3", "props": ""},
    ]
    rels = [
        {"src_id": "concept:过渡态", "dst_id": "software:Gaussian", "rel_type": "applies_to",
         "source": "kb:1"},
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
    db = tmp_path / "kg.db"
    store.import_csv(db, e_csv, r_csv)
    return db


def _svc():
    spec = importlib.util.spec_from_file_location(
        "kg_vec_service", REPO_ROOT / "scripts" / "kg_vec_service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- store/FTS

def test_label_en_in_fts_english_query_hits_graph(bilingual_db: Path):
    """props.label_en 是 FTS 索引列 → 英文 trigram 查询直接命中图谱。"""
    rows = store.search_graph(bilingual_db, "transition state", limit=5)
    assert rows, "english FTS query must hit via props.label_en"
    hit = next(r for r in rows if r["id"] == "concept:过渡态")
    assert hit["label_en"] == "transition state"
    assert hit["label"] == "过渡态"  # 原 label 保留（唯一事实源）


def test_chinese_query_regression_unchanged(bilingual_db: Path):
    rows = store.search_graph(bilingual_db, "过渡态", limit=5)
    assert rows and rows[0]["fallback"] == "fts"
    assert rows[0]["label"] == "过渡态"


def test_label_en_none_for_missing_props(bilingual_db: Path):
    rows = store.search_graph(bilingual_db, "Gaussian", limit=5)
    g = next(r for r in rows if r["id"] == "software:Gaussian")
    assert g["label_en"] is None


def test_ego_graph_passes_label_en(bilingual_db: Path):
    """前端图谱视图的数据源：ego 节点与 focus 都要透传 label_en。"""
    eg = store.ego_graph(bilingual_db, "concept:过渡态", hops=1)
    assert eg is not None
    node = next(n for n in eg["nodes"] if n["id"] == "concept:过渡态")
    assert node["label_en"] == "transition state"
    assert node["label"] == "过渡态"
    assert eg["focus"]["label_en"] == "transition state"
    # 无 props 的实体：label_en 为 None 而非报错
    gauss = next(n for n in eg["nodes"] if n["id"] == "software:Gaussian")
    assert gauss["label_en"] is None


# ---------------------------------------------------------------- plugin

def test_ascii_dominant_graph_title_uses_label_en(bilingual_db, monkeypatch):
    monkeypatch.setattr(kg_plugin, "knowledge_graph_db_path", lambda: bilingual_db)
    entries = ChemKBPlugin().search("transition state", limit=5)
    graph = [e for e in entries if e.title.startswith("〔图谱〕")]
    assert any("transition state" in e.title for e in graph)
    # content 保留原 label 可溯源
    for e in graph:
        if "transition state" in e.title:
            assert "过渡态" in e.content


def test_chinese_query_graph_title_uses_zh_label(bilingual_db, monkeypatch):
    monkeypatch.setattr(kg_plugin, "knowledge_graph_db_path", lambda: bilingual_db)
    entries = ChemKBPlugin().search("过渡态", limit=5)
    graph = [e for e in entries if e.title.startswith("〔图谱〕")]
    assert graph
    # 中文查询：命中的中文实体用中文 label，且不得出现英文 label_en
    assert any("过渡态" in e.title for e in graph)
    assert not any("transition state" in e.title for e in graph)


def test_ascii_dominant_heuristic():
    assert kg_plugin._ascii_dominant("how to find transition state")
    assert kg_plugin._ascii_dominant("opt=TS with calcfc")
    assert not kg_plugin._ascii_dominant("怎么找过渡态")
    assert not kg_plugin._ascii_dominant("Gaussian 过渡态 优化 搜索 收敛")  # 多数中文


# ---------------------------------------------------------------- service

def test_service_lang_filter_and_card_dedup():
    svc = _svc()
    cards = [
        {"card_id": "kb:1:1", "lang": "en", "heading": "h-en", "content": "c"},
        {"card_id": "kb:1:1", "lang": "zh", "heading": "h-zh", "content": "c"},
        {"card_id": "kb:2:1", "lang": "en", "heading": "h2-en", "content": "c"},
        {"card_id": "kb:3:1", "heading": "h3-legacy", "content": "c"},  # 无 lang → zh
    ]

    class Scores:  # 简单分数字典模拟 numpy 数组
        def __init__(self, d):
            self.d = d

        def __getitem__(self, i):
            return self.d[int(i)]

    scores = Scores({0: 0.9, 1: 0.8, 2: 0.7, 3: 0.6})
    order = [0, 1, 2, 3]

    mixed = svc._select_hits(cards, scores, order, 5, None)
    assert [h["card_id"] for h in mixed] == ["kb:1:1", "kb:2:1", "kb:3:1"]  # 同卡去重
    assert mixed[0]["lang"] == "en"  # 高分行（0.9 是 en 行）
    assert mixed[0]["score"] == 0.9

    en_only = svc._select_hits(cards, scores, order, 5, "en")
    assert [h["card_id"] for h in en_only] == ["kb:1:1", "kb:2:1"]

    zh_only = svc._select_hits(cards, scores, order, 5, "zh")
    assert [h["card_id"] for h in zh_only] == ["kb:1:1", "kb:3:1"]  # 无 lang 行归 zh


def test_service_clamp_lang():
    svc = _svc()
    assert svc._clamp_lang("en") == "en"
    assert svc._clamp_lang("ZH") == "zh"
    assert svc._clamp_lang("") is None
    assert svc._clamp_lang(None) is None
    assert svc._clamp_lang("fr") is None


# ---------------------------------------------------------------- fuzzy

def test_fuzzy_bilingual_dedup_prefers_en_for_ascii_query(tmp_path, monkeypatch):
    rows = [
        {"card_id": "kb:1:1", "lang": "en", "heading": "transition state optimization",
         "content": "english body"},
        {"card_id": "kb:1:1", "lang": "zh", "heading": "过渡态优化",
         "content": "transition state 内容"},  # zh 行也含 ASCII token
    ]
    p = tmp_path / "cards.jsonl"
    import json as _json
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(_json.dumps(r, ensure_ascii=False) + "\n")
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: p)
    fuzzy._reset_cache()
    hits = fuzzy.search("transition state", 5)
    assert len(hits) == 1  # 同卡去重
    assert hits[0]["lang"] == "en"  # ASCII 查询偏 en 行


def test_fuzzy_bilingual_prefers_zh_for_chinese_query(tmp_path, monkeypatch):
    rows = [
        {"card_id": "kb:1:1", "lang": "en", "heading": "transition state",
         "content": "过渡态 english body"},  # en 行也含中文 token
        {"card_id": "kb:1:1", "lang": "zh", "heading": "过渡态优化",
         "content": "正文"},
    ]
    p = tmp_path / "cards.jsonl"
    import json as _json
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(_json.dumps(r, ensure_ascii=False) + "\n")
    monkeypatch.setattr(fuzzy, "_cards_file", lambda: p)
    fuzzy._reset_cache()
    hits = fuzzy.search("过渡态", 5)
    assert len(hits) == 1
    assert hits[0]["lang"] == "zh"
