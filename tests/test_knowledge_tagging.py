"""知识卡片标签体系（v13）：词表 / 报错检测 / 打标流水线 / 写回行对齐 / 反贴。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cloudra.knowledge import store
from cloudra.knowledge.tagging import (
    TagVocab,
    cache_key,
    coverage_report,
    detect_error_tags,
    group_by_card,
    parse_llm_tags,
    read_cards,
    source_tag_map,
    tag_cards,
    writeback_tags,
)
from cloudra.runtime_v2.knowledge import flatten_tags

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 词表与报错签名检测
# ---------------------------------------------------------------------------

def test_vocab_loads_from_repo_and_indexes_aliases():
    vocab = TagVocab.load()
    assert vocab.values["domain"], "domain facet 继承字段也应登记在册"
    for facet in ("method", "software", "problem", "error"):
        assert vocab.values[facet], f"{facet} 词表不应为空"
    # 别名倒排：G16 → software:gaussian
    assert vocab.alias_index["g16"] == ("software", "gaussian")
    # ASCII 别名小写入索引，检测不区分大小写
    assert vocab.alias_index["convergence failure"][0] == "error"


def test_detect_error_tags_hits_verbatim_and_avoids_false_positives():
    vocab = TagVocab.load()
    assert "err_l502" in detect_error_tags(
        "log_parser /tmp/TS1.log Convergence failure -- L502", vocab)
    assert "err_galloc" in detect_error_tags(
        "galloc: could not allocate memory", vocab)
    # 干净的成功输出不得误报（P1-1 回归：这些曾是会误命中的别名）
    assert detect_error_tags("log_parser done, frequencies all positive", vocab) == []
    assert detect_error_tags("SCF Done: E(RB3LYP) = -390.02 after 13 cycles", vocab) == []
    assert detect_error_tags("Gaussian license 文件放在哪个目录", vocab) == []
    assert detect_error_tags("服务器是 AVX512 CPU，编译参数如何选", vocab) == []
    assert detect_error_tags("指令集架构的说明文档", vocab) == []
    assert detect_error_tags("如何申请软件授权", vocab) == []
    assert detect_error_tags("g09.user 配置说明", vocab) == []
    assert detect_error_tags("", vocab) == []


# ---------------------------------------------------------------------------
# 卡片分组与 tags 归一
# ---------------------------------------------------------------------------

def _row(cid: str, lang: str, heading: str = "h", content: str = "c") -> dict:
    return {"card_id": cid, "blog_id": cid.split(":")[1], "heading": heading,
            "content": content, "lang": lang, "domain": "量子化学方法"}


def test_group_by_card_collapses_zh_en_pair():
    rows = [_row("kb:1:1", "en"), _row("kb:1:1", "zh"), _row("kb:2:1", "zh")]
    groups = group_by_card(rows)
    assert [g["card_id"] for g in groups] == ["kb:1:1", "kb:2:1"]
    # 文本代表优先 zh 行
    assert groups[0]["text_row"]["lang"] == "zh"
    assert groups[0]["row_indexes"] == [0, 1]


def test_flatten_tags_accepts_dict_list_and_none():
    assert flatten_tags({"error": ["err_l502"], "method": ["dft", None]}) == \
        ["err_l502", "dft"]
    assert flatten_tags(["a", "b"]) == ["a", "b"]
    assert flatten_tags(None) == []
    assert flatten_tags({"error": "not-a-list"}) == []


# ---------------------------------------------------------------------------
# LLM 输出校验：词表内落库，词表外进 pending
# ---------------------------------------------------------------------------

def test_parse_llm_tags_filters_unknown_and_keeps_known():
    vocab = TagVocab.load()
    batch = [{"card_id": "kb:1:1"}, {"card_id": "kb:2:1"}]
    data = {
        "kb:1:1": {"software": ["gaussian"], "error": ["err_l502"],
                   "method": ["totally_made_up"], "problem": ["scf_not_converged"]},
        "kb:9:9": {"method": ["dft"]},  # 未知 cid 应被丢弃
        "junk": "not-a-dict",
    }
    tags, pending = parse_llm_tags(data, batch, vocab)
    assert tags["kb:1:1"] == {"software": ["gaussian"], "error": ["err_l502"],
                              "problem": ["scf_not_converged"]}
    assert "kb:9:9" not in tags
    assert pending == [{"card_id": "kb:1:1", "facet": "method",
                        "value": "totally_made_up"}]


# ---------------------------------------------------------------------------
# 写回：行数与顺序严格不变（vectors.f16.npy 行对齐的硬约束）
# ---------------------------------------------------------------------------

def test_writeback_preserves_row_order_and_shares_tags_across_langs(tmp_path):
    cards = tmp_path / "cards.jsonl"
    rows = [_row("kb:1:1", "en", "en head"), _row("kb:1:1", "zh", "zh 标题"),
            _row("kb:2:1", "zh")]
    cards.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")

    loaded = read_cards(cards)
    stats = writeback_tags(loaded, {"kb:1:1": {"error": ["err_l502"]}}, cards)
    assert stats == {"rows": 3, "cards": 1}

    after = [json.loads(line) for line in cards.read_text(encoding="utf-8").splitlines()]
    assert len(after) == 3
    assert [r["heading"] for r in after] == ["en head", "zh 标题", "h"]
    # 同 card 的 zh/en 两行共享同一份 tags
    assert after[0]["tags"] == {"error": ["err_l502"]}
    assert after[1]["tags"] == {"error": ["err_l502"]}
    assert "tags" not in after[2]


def test_writeback_rejects_file_with_stray_blank_lines(tmp_path):
    """行对齐硬守卫：原文件含中间空行（会被 read_cards 吞掉）时必须硬失败，
    而不是静默重写出更少的行导致 vectors.f16.npy 错位。"""
    cards = tmp_path / "cards.jsonl"
    rows = [_row("kb:1:1", "zh"), _row("kb:2:1", "zh")]
    cards.write_text(
        json.dumps(rows[0], ensure_ascii=False) + "\n\n"
        + json.dumps(rows[1], ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="行数"):
        writeback_tags(read_cards(cards), {"kb:1:1": {"error": ["err_l502"]}}, cards)


# ---------------------------------------------------------------------------
# 缓存：内容哈希键，重跑跳过；内容变了才重打
# ---------------------------------------------------------------------------

def test_cache_key_changes_with_content():
    a = cache_key("kb:1:1", "h", "c")
    assert a == cache_key("kb:1:1", "h", "c")
    assert a != cache_key("kb:1:1", "h", "c2")
    assert a != cache_key("kb:1:2", "h", "c")


# ---------------------------------------------------------------------------
# 端到端（假 LLM）：读卡 → LLM → 校验 → 缓存 → 写回
# ---------------------------------------------------------------------------

class _FakeLLMClient:
    """替身 LLMClient：按 prompt 里的 cid 返回固定 tags（含一个词表外提议）。"""

    calls: list[str] = []

    def __init__(self, api_key: str, base_url: str, model: str | None = None, **kw):
        assert api_key and base_url, "必须显式传 provider（避免测试读到真实 config）"
        _FakeLLMClient.calls.append(base_url)

    async def chat_json(self, system: str, user: str, **kw):
        data = {}
        for line in user.splitlines():
            if line.startswith("cid: "):
                cid = line[5:].strip()
                data[cid] = {"software": ["gaussian"], "error": ["err_l502"],
                             "problem": ["scf_not_converged"],
                             "method": ["mystery_new_method"]}
        return data, None

    async def aclose(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _fake_llm(monkeypatch):
    _FakeLLMClient.calls = []
    import cloudra.infra.llm_client as llm
    monkeypatch.setattr(llm, "LLMClient", _FakeLLMClient)


def test_tag_cards_end_to_end_with_cache_and_writeback(tmp_path, monkeypatch):
    cards = tmp_path / "cards.jsonl"
    cache = tmp_path / "tag_cache.jsonl"
    rows = [_row("kb:1:1", "zh"), _row("kb:1:1", "en"), _row("kb:2:1", "zh", "x", "y")]
    cards.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")

    report = tag_cards(
        vocab=TagVocab.load(), cards_path=cards, cache_path=cache,
        model="fake", base_url="http://fake", api_key="k", batch_size=2,
    )
    assert report["cards_total"] == 2 and report["llm_batches"] == 1
    assert report["cards_with_tags"] == 2
    # 假 LLM 给每张卡都提议了词表外的 mystery_new_method
    assert {p["value"] for p in report["pending"]} == {"mystery_new_method"}
    assert all(p["facet"] == "method" for p in report["pending"])
    assert report["write"]["cards"] == 2
    assert cache.is_file(), "非 dry-run 必须落缓存"

    # 重跑：全部缓存命中，零 LLM 调用
    calls_before = len(_FakeLLMClient.calls)
    report2 = tag_cards(
        vocab=TagVocab.load(), cards_path=cards, cache_path=cache,
        model="fake", base_url="http://fake", api_key="k",
    )
    assert report2["from_cache"] == 2 and len(_FakeLLMClient.calls) == calls_before

    # 内容变了 → 该卡重打
    rows2 = read_cards(cards)
    rows2[-1]["content"] = "changed"
    cards.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows2) + "\n",
        encoding="utf-8")
    report3 = tag_cards(
        vocab=TagVocab.load(), cards_path=cards, cache_path=cache,
        model="fake", base_url="http://fake", api_key="k",
    )
    assert report3["from_cache"] == 1 and report3["llm_batches"] == 1


def test_tag_cards_dry_run_touches_nothing(tmp_path):
    cards = tmp_path / "cards.jsonl"
    rows = [_row("kb:1:1", "zh")]
    cards.write_text(json.dumps(rows[0], ensure_ascii=False), encoding="utf-8")
    before = cards.read_text(encoding="utf-8")

    report = tag_cards(
        vocab=TagVocab.load(), cards_path=cards,
        cache_path=tmp_path / "c.jsonl",
        model="fake", base_url="http://fake", api_key="k", dry_run=True,
    )
    assert report["cards_with_tags"] == 1 and report["write"] == {}
    assert cards.read_text(encoding="utf-8") == before
    assert not (tmp_path / "c.jsonl").exists()


# ---------------------------------------------------------------------------
# 卡片 tags → relations.source 映射 → 图谱反贴（store 集成）
# ---------------------------------------------------------------------------

def test_source_tag_map_merges_cards_by_blog():
    rows = [
        {"card_id": "kb:422:1", "blog_id": "422", "tags": {"problem": ["ts_search"]}},
        {"card_id": "kb:422:2", "blog_id": "422",
         "tags": {"problem": ["ts_search", "opt_not_converged"], "software": ["gaussian"]}},
        {"card_id": "kb:422:3", "blog_id": "422", "tags": {}},  # 无 tags 不影响
        {"card_id": "kb:dyn01:5", "blog_id": "dyn01",
         "tags": {"method": ["md_method"]}},
    ]
    m = source_tag_map(rows)
    assert m["kb:422"] == {"problem": ["ts_search", "opt_not_converged"],
                           "software": ["gaussian"]}
    assert m["kb:dyn01"] == {"method": ["md_method"]}


def test_store_entity_tag_rebuild_and_facet_search(tmp_path):
    """CSV 导入 → 反贴 → search_graph 的 facets/entity_type 过滤与 note 上送。"""
    import csv as _csv

    ent, rel = tmp_path / "e.csv", tmp_path / "r.csv"
    with ent.open("w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["id", "type", "label", "smiles", "props", "n_sources"])
        w.writerow(["concept:%oldchk", "concept", "%oldchk", "", "{}", 1])
        w.writerow(["pitfall:TS.chk被改写", "pitfall", "过渡态文件TS.chk被改写", "", "{}", 1])
    with rel.open("w", encoding="utf-8-sig", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["src_id", "dst_id", "rel_type", "evidence_level", "source",
                    "falsified", "note"])
        w.writerow(["concept:%oldchk", "pitfall:TS.chk被改写", "common_error_of",
                    "L0", "kb:422", "false", "使用%oldchk可避免TS.chk被改写"])
    db = tmp_path / "chem_kg.db"
    store.import_csv(db, ent, rel)

    report = store.rebuild_entity_tags(
        db, {"kb:422": {"error": ["err_l9999"], "problem": ["ts_search"]}})
    assert report["entities"] == 2 and report["rows"] == 4

    # 反贴可幂等重建
    again = store.rebuild_entity_tags(db, {"kb:422": {"error": ["err_l9999"]}})
    assert again["rows"] == 2

    # note 上送：图谱条目 content 携带因果解释
    hits = store.search_graph(db, "%oldchk", limit=5)
    assert hits and "%oldchk可避免" in hits[0]["content"]
    # 实体标签随条目返回
    assert hits[0]["tags"]["error"] == ["err_l9999"]

    # facet / entity_type 过滤：命中、落空、类型限定
    assert store.search_graph(db, "%oldchk", facets={"error": ["err_l9999"]})
    assert store.search_graph(db, "%oldchk", facets={"error": ["err_galloc"]}) == []
    assert store.search_graph(db, "%oldchk", entity_type="pitfall")
    assert store.search_graph(db, "%oldchk", entity_type="software") == []


def test_rebuild_entity_tags_missing_db_raises(tmp_path):
    """缺库不得静默建空库（否则后续检索显示'无命中'而非'库不存在'）。"""
    with pytest.raises(FileNotFoundError, match="knowledge import"):
        store.rebuild_entity_tags(tmp_path / "nope.db", {"kb:1": {"error": ["err_l502"]}})


# ---------------------------------------------------------------------------
# 覆盖率统计
# ---------------------------------------------------------------------------

def test_coverage_report_counts_cards_not_rows():
    rows = [
        _row("kb:1:1", "en"), _row("kb:1:1", "zh", "h", "c"),
        _row("kb:2:1", "zh"),
    ]
    rows[0]["tags"] = {"error": ["err_l502"]}
    rows[1]["tags"] = {"error": ["err_l502"]}
    rep = coverage_report(rows)
    assert rep["cards"] == 2 and rep["tagged_cards"] == 1
    assert rep["coverage_pct"] == 50.0
    assert rep["facet_cards"]["error"] == 50.0


def test_repo_vocab_yaml_is_wellformed():
    raw = yaml.safe_load((REPO_ROOT / "vector_store" / "tag_vocab.yaml").read_text(
        encoding="utf-8"))
    assert raw["facets"]["error"], "词表损坏（error facet 缺失）"
    from cloudra.knowledge.tagging import TAG_FACETS
    for facet, items in raw["facets"].items():
        ids = set()
        for item in items:
            assert item.get("id"), f"{facet} 有缺 id 的条目"
            assert item["id"] not in ids, f"{facet} 有重复 id: {item['id']}"
            ids.add(item["id"])
            if facet in TAG_FACETS:
                assert item.get("aliases"), f"{item['id']} 缺 aliases（匹配靠它）"


def test_parse_tag_filters_bare_tag_goes_to_error():
    from cloudra.knowledge.tagging import parse_tag_filters
    # facet:tag_id 形式
    assert parse_tag_filters(["error:err_l502", "problem:ts_search"]) == \
        {"error": ["err_l502"], "problem": ["ts_search"]}
    # 裸 tag（无冒号）按 error 惯例——文档与 CLI help 承诺的行为
    assert parse_tag_filters(["err_l502"]) == {"error": ["err_l502"]}
    # 前导冒号 / 空串 / 空位 畸形项静默丢弃
    assert parse_tag_filters([":err_l502", "", " : ", "error:"]) == {}
    assert parse_tag_filters([]) == {}
