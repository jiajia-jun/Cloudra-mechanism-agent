"""图谱中英文索引与独立向量脚本的语言/标签筛选。"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

from cloudra.knowledge import store

REPO_ROOT = Path(__file__).resolve().parents[1]


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


# ---------------------------------------------------------------- v13 filters

def test_service_norm_tag_filter_accepts_string_values():
    """P2 回归：dict 值传单字符串（调试端点自然写法）不得逐字符迭代。"""
    svc = _svc()
    assert svc._norm_tag_filter({"error": "err_l502"}) == {"error": {"err_l502"}}
    assert svc._norm_tag_filter(["err_l502", "err_l9999"]) == \
        {"_any": {"err_l502", "err_l9999"}}
    assert svc._norm_tag_filter("err_l502") == {"_any": {"err_l502"}}
    assert svc._norm_tag_filter({"error": []}) is None
    assert svc._norm_tag_filter(None) is None
    # 值两端空白要 strip（GET 逗号分隔的常见残留）
    assert svc._norm_tag_filter([" err_l502 "]) == {"_any": {"err_l502"}}


def test_service_norm_domain_filter():
    svc = _svc()
    assert svc._norm_domain_filter("Gaussian使用") == {"Gaussian使用"}
    assert svc._norm_domain_filter(["a", " b ", ""]) == {"a", "b"}
    assert svc._norm_domain_filter(None) is None


def test_service_select_hits_applies_domain_and_tag_filters():
    svc = _svc()

    class Scores:
        def __init__(self, d):
            self.d = d

        def __getitem__(self, i):
            return self.d[int(i)]

    cards = [
        {"card_id": "kb:1:1", "lang": "zh", "domain": "Gaussian使用",
         "tags": {"error": ["err_l502"], "problem": ["scf_not_converged"]}},
        {"card_id": "kb:2:1", "lang": "zh", "domain": "量子化学方法", "tags": {}},
        {"card_id": "kb:3:1", "lang": "zh", "domain": "Gaussian使用",
         "tags": {"error": ["err_l9999"]}},
    ]
    scores = Scores({0: 0.9, 1: 0.8, 2: 0.7})
    order = [0, 1, 2]

    # error facet 过滤：只留带 err_l502/err_l9999 的卡（任一命中）
    hits = svc._select_hits(cards, scores, order, 5, None, None, {"error": {"err_l502"}})
    assert [h["card_id"] for h in hits] == ["kb:1:1"]
    # 扁平 _any：跨 facet 任一命中
    hits_any = svc._select_hits(cards, scores, order, 5, None, None,
                                {"_any": {"err_l9999", "nonexistent"}})
    assert [h["card_id"] for h in hits_any] == ["kb:3:1"]
    # domain 过滤 + 不足 k 宁缺勿滥
    hits_dom = svc._select_hits(cards, scores, order, 5, None, {"Gaussian使用"}, None)
    assert [h["card_id"] for h in hits_dom] == ["kb:1:1", "kb:3:1"]
    # 无 tags 字段的旧库行：过滤为 None 时照常返回
    assert svc._select_hits(cards, scores, order, 5, None, None, None)
