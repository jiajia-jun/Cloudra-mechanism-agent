"""chem-kb SQLite store：建库/导入/检索/邻域。"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from cloudra.knowledge import store


@pytest.fixture(autouse=True)
def _clear_plugins():
    from cloudra.runtime_v2.plugins import clear_plugins

    clear_plugins()
    yield
    clear_plugins()


ENT_HEADERS = ["id", "type", "label", "smiles", "props", "n_sources"]
REL_HEADERS = ["src_id", "dst_id", "rel_type", "evidence_level", "source", "falsified", "note"]


def write_entities(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ENT_HEADERS)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in ENT_HEADERS} for r in rows])
    return path


def write_relations(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REL_HEADERS)
        w.writeheader()
        w.writerows([{k: r.get(k, "") for k in REL_HEADERS} for r in rows])
    return path


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    ents = [
        {"id": "concept:过渡态", "type": "concept", "label": "过渡态", "n_sources": "2"},
        {"id": "method:过渡态搜索", "type": "method", "label": "过渡态搜索", "n_sources": "1"},
        {"id": "software:Gaussian", "type": "software", "label": "Gaussian", "n_sources": "3"},
        {"id": "parameter:TS", "type": "parameter", "label": "TS", "n_sources": "1"},
        {"id": "basis:def2-TZVP", "type": "parameter", "label": "def2-TZVP", "n_sources": "1"},
    ]
    rels = [
        {"src_id": "method:过渡态搜索", "dst_id": "concept:过渡态", "rel_type": "applies_to",
         "source": "kb:1", "evidence_level": "L0"},
        {"src_id": "method:过渡态搜索", "dst_id": "concept:过渡态", "rel_type": "applies_to",
         "source": "kb:2", "evidence_level": "L0"},  # 双 source → corroborated
        {"src_id": "basis:def2-TZVP", "dst_id": "software:Gaussian", "rel_type": "parameter_of",
         "source": "kb:3", "evidence_level": "L0"},
        {"src_id": "software:Gaussian", "dst_id": "method:过渡态搜索", "rel_type": "part_of",
         "source": "kb:77", "evidence_level": "L0"},
    ]
    e_csv, r_csv = tmp_path / "e.csv", tmp_path / "r.csv"
    write_entities(e_csv, ents)
    write_relations(r_csv, rels)
    db = tmp_path / "kg.db"
    store.import_csv(db, e_csv, r_csv)
    return db


def test_schema_idempotent(tmp_path: Path):
    db = tmp_path / "kg.db"
    store.ensure_schema(db)
    store.ensure_schema(db)  # 幂等
    assert db.exists()
    assert store.overview(db)["entities"] == 0


def test_import_counts_and_dangling_report(tmp_path: Path):
    ents = [
        {"id": "concept:a", "type": "concept", "label": "a", "n_sources": "1"},
        {"id": "concept:b", "type": "concept", "label": "b", "n_sources": "1"},
    ]
    rels = [
        {"src_id": "concept:a", "dst_id": "concept:b", "rel_type": "applies_to", "source": "kb:1"},
        {"src_id": "concept:a", "dst_id": "concept:missing", "rel_type": "applies_to", "source": "kb:1"},
    ]
    e_csv, r_csv = tmp_path / "e.csv", tmp_path / "r.csv"
    write_entities(e_csv, ents)
    write_relations(r_csv, rels)
    rep = store.import_csv(tmp_path / "kg.db", e_csv, r_csv)
    assert rep["entities"] == 2
    assert rep["relations"] == 1
    assert len(rep["bad_rows"]) == 1
    assert "dangling" in rep["bad_rows"][0]["reason"]
    assert rep["bad_rows"][0]["line"] == 3  # 表头行 1，数据行从 2 起


def test_gbk_fallback(tmp_path: Path):
    # 写一个真的 GBK 编码 CSV（严格 UTF-8 解码必须失败）。
    p = tmp_path / "e.csv"
    p.write_bytes("id,type,label,smiles,props,n_sources\r\nconcept:苯,concept,苯,,,\r\n".encode("gbk"))
    db = tmp_path / "kg.db"
    rep = store.import_csv(db, p, write_relations(tmp_path / "r.csv", []))
    assert rep["encoding"]["entities"] == "gbk"
    assert store.overview(db)["entities"] == 1


def test_search_chinese_trigram_and_short_token_fallback(sample_db: Path):
    rows = store.search_graph(sample_db, "过渡态", limit=5)
    assert rows and rows[0]["fallback"] == "fts"
    assert any("过渡态" in r["label"] for r in rows)
    # 2 字中文 token <3 → 整体 LIKE
    rows = store.search_graph(sample_db, "搜索", limit=5)
    assert rows and rows[0]["fallback"] == "like"
    # "TS"（2 字符）→ LIKE
    rows = store.search_graph(sample_db, "TS", limit=5)
    assert rows and rows[0]["fallback"] == "like"
    # ASCII 长词 → FTS
    rows = store.search_graph(sample_db, "def2-TZVP", limit=5)
    assert rows and rows[0]["fallback"] == "fts"
    # 混合 token（短+长）：短 token 不进 FTS，长 token 的 FTS 命中即返回
    rows = store.search_graph(sample_db, "TS Gaussian", limit=5)
    assert rows and rows[0]["fallback"] == "fts"
    assert any(r["label"] == "Gaussian" for r in rows)
    # AND 零命中 → OR 档：两个 token 各自存在但无实体同时包含
    rows = store.search_graph(sample_db, "Gaussian 过渡态", limit=5)
    assert rows and rows[0]["fallback"] == "fts_or"
    # 全零 → 整串 LIKE 回退（有整串命中时可见 fallback=like）
    rows = store.search_graph(sample_db, "过渡态搜索", limit=5)
    assert rows and rows[0]["fallback"] in ("fts", "like")


def test_search_hits_after_rebuild_and_like_score_determinism(sample_db: Path):
    a = store.search_graph(sample_db, "TS", limit=5)
    b = store.search_graph(sample_db, "TS", limit=5)
    assert [(r["id"], r["score"]) for r in a] == [(r["id"], r["score"]) for r in b]


def test_neighborhood_hops_and_dedup(sample_db: Path):
    # 种子 过渡态 直接命中（hop=0）；"过渡态搜索"因 trigram 包含也是直接命中（hop=0）；
    # Gaussian 经 过渡态搜索 一跳可达（hop=1），def2-TZVP 两跳（hop=2）。
    # GROUP BY id 取 MIN(hop)。
    rows = store.search_graph(sample_db, "过渡态", limit=10)
    hops = {r["label"]: r["hop"] for r in rows}
    assert hops.get("过渡态") == 0
    assert hops.get("过渡态搜索") == 0
    assert hops.get("Gaussian") == 1
    assert hops.get("def2-TZVP") == 2
    assert len([r for r in rows if r["label"] == "过渡态搜索"]) == 1


def test_corroborated_not_always_false(sample_db: Path):
    ov = store.overview(sample_db)
    assert ov["corroborated"] == 1  # method:过渡态搜索→concept:过渡态 双 source
    eg = store.ego_graph(sample_db, "method:过渡态搜索", hops=1)
    edge = next(e for e in eg["edges"] if e["rel_type"] == "applies_to")
    assert edge["corroborated"] is True


def test_double_import_idempotent(tmp_path: Path, sample_db: Path):
    e_csv, r_csv = tmp_path / "e.csv", tmp_path / "r.csv"
    rep = store.import_csv(sample_db, e_csv, r_csv)  # 同 CSV 二次导入
    assert rep["bad_rows"] == []
    ov = store.overview(sample_db)
    assert ov["entities"] == 5
    assert ov["relations"] == 4  # UNIQUE(src,dst,rel,source) 去重


def test_missing_db_returns_empty(tmp_path: Path):
    assert store.search_graph(tmp_path / "nope.db", "x", 5) == []
    assert store.relations_of_source(tmp_path / "nope.db", "kb:1", 5) == []
    assert store.ego_graph(tmp_path / "nope.db", "concept:x", 1) is None
    ov = store.overview(tmp_path / "nope.db")
    assert ov["db_present"] is False


def test_relations_of_source_uses_index(sample_db: Path):
    rows = store.relations_of_source(sample_db, "kb:2", 5)
    assert len(rows) == 1 and rows[0]["rel_type"] == "applies_to"
    con = store._open_ro(sample_db)
    try:
        plan = con.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM kg_relations WHERE source = 'kb:2'"
        ).fetchall()
        assert any("idx_rel_source" in str(r) for r in plan)
    finally:
        con.close()


def test_ego_truncation_deterministic(tmp_path: Path):
    # 星型：n0 一跳直达其余 19 节点 → 20 > max_nodes=5 触发确定性截断。
    ents = [{"id": f"concept:n{i}", "type": "concept", "label": f"n{i}",
             "n_sources": str((i % 3) + 1)} for i in range(20)]
    rels = [
        {"src_id": "concept:n0", "dst_id": f"concept:n{i}", "rel_type": "part_of",
         "source": f"kb:{i}"}
        for i in range(1, 20)
    ]
    e_csv, r_csv = tmp_path / "e.csv", tmp_path / "r.csv"
    write_entities(e_csv, ents)
    write_relations(r_csv, rels)
    db = tmp_path / "kg.db"
    store.import_csv(db, e_csv, r_csv)
    a = store.ego_graph(db, "concept:n0", hops=2, max_nodes=5)
    b = store.ego_graph(db, "concept:n0", hops=2, max_nodes=5)
    assert a["truncated"] is True
    assert [n["id"] for n in a["nodes"]] == [n["id"] for n in b["nodes"]]
    assert len(a["nodes"]) == 5


def test_full_repo_import_seconds_level(project_root):
    e = Path(project_root) / "kg_data" / "kg-entities.csv"
    r = Path(project_root) / "kg_data" / "kg-relations.csv"
    if not e.exists():
        pytest.skip("repo KG CSVs not present")
    db = Path(tempfile.mkdtemp()) / "kg.db"
    rep = store.import_csv(db, e, r)
    assert rep["entities"] == 15098
    assert rep["relations"] == 10811
    assert rep["bad_rows"] == []
    assert rep["seconds"] < 60  # 秒级
    for q in ("过渡态", "TS", "def2-TZVP"):
        rows = store.search_graph(db, q, limit=5)
        assert rows, f"no hits for {q}"
