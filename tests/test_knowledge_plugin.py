"""Graph keywords locate sources; return their complete knowledge text."""

from __future__ import annotations

import csv
import json

import pytest

from cloudra.knowledge import plugin as kg_plugin
from cloudra.knowledge import store
from cloudra.knowledge.plugin import ChemKBPlugin
from cloudra.persistence import paths


@pytest.fixture
def knowledge_assets(tmp_path, monkeypatch):
    entities = [
        {"id": "concept:SCF", "label": "自洽场 SCF", "props": '{"label_en":"self consistent field"}'},
        {"id": "software:Gaussian", "label": "Gaussian"},
        {"id": "concept:邻居", "label": "邻居"},
        {"id": "concept:远端", "label": "远端"},
        {"id": "method:偶联", "label": "偶联", "props": '{"label_en":"coupling"}'},
    ]
    relations = [
        {"src_id": "concept:SCF", "dst_id": "software:Gaussian", "source": "kb:10"},
        {"src_id": "concept:SCF", "dst_id": "concept:邻居", "source": "kb:20"},
        {"src_id": "concept:邻居", "dst_id": "concept:远端", "source": "kb:30"},
        {"src_id": "method:偶联", "dst_id": "concept:远端", "source": "org:coupling:2"},
    ]
    for name, rows, fields in (
        ("entities", entities, ["id", "label", "props"]),
        ("relations", relations, ["src_id", "dst_id", "source"]),
    ):
        with (tmp_path / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    db = tmp_path / "chem_kg.db"
    store.import_csv(db, tmp_path / "entities.csv", tmp_path / "relations.csv")
    cards = [
        {"card_id": "kb:10:10", "heading": "第十节", "content": "完整末节内容", "lang": "zh"},
        {"card_id": "kb:10:2", "heading": "第二节", "content": "正文" * 160 + "末尾适用条件", "lang": "zh"},
        {"card_id": "kb:10:1", "heading": "第一节", "content": "开头说明", "lang": "zh"},
        {"card_id": "kb:10:1", "heading": "First section", "content": "English explanation", "lang": "en"},
        {"card_id": "kb:20:1", "heading": "另一来源", "content": "第二篇完整知识稿", "lang": "zh"},
        {"card_id": "kb:30:1", "heading": "未命中的远端来源", "content": "不能靠邻居扩展混进结果", "lang": "zh"},
        {"card_id": "org:coupling:2:1", "blog_id": "org", "heading": "有机来源", "content": "偶联知识正文", "lang": "zh"},
        {"card_id": "kb:99:1", "heading": "unindexed phrase", "content": "正文有关键词但图没有索引", "lang": "zh"},
    ]
    for card in cards:
        card["file"] = f"test/{card['card_id'].rsplit(':', 1)[0]}.md"
        card["fm_title"] = card["card_id"].rsplit(":", 1)[0]
    cards_path = tmp_path / "cards.jsonl"
    cards_path.write_text("".join(json.dumps(card, ensure_ascii=False) + "\n" for card in cards), encoding="utf-8")
    monkeypatch.setattr(kg_plugin, "knowledge_graph_db_path", lambda: db)
    monkeypatch.setattr(paths, "knowledge_cards_path", lambda: cards_path, raising=False)
    from cloudra.knowledge import content

    content._reset_cache()
    yield db, cards_path
    content._reset_cache()


def test_graph_hit_returns_complete_sources_in_section_order(knowledge_assets):
    hits = ChemKBPlugin().search("自洽场")
    assert {hit.source for hit in hits} == {"kb:10", "kb:20"}
    document = next(hit for hit in hits if hit.source == "kb:10")
    assert document.content.index("第一节") < document.content.index("第二节") < document.content.index("第十节")
    assert "末尾适用条件" in document.content
    assert "test/kb:10.md" in document.content
    assert "English explanation" not in document.content


def test_sources_covering_more_query_keywords_rank_first(knowledge_assets):
    hits = ChemKBPlugin().search("Gaussian SCF", limit=1)
    assert [hit.source for hit in hits] == ["kb:10"]


def test_english_source_keeps_untranslated_sections(knowledge_assets):
    document = next(hit for hit in ChemKBPlugin().search("self consistent field") if hit.source == "kb:10")
    assert "English explanation" in document.content
    assert "开头说明" not in document.content
    assert "末尾适用条件" in document.content
    assert "完整末节内容" in document.content


def test_organic_source_uses_card_id_parent_not_blog_id(knowledge_assets):
    hits = ChemKBPlugin().search("coupling")
    assert [hit.source for hit in hits] == ["org:coupling:2"]
    assert "偶联知识正文" in hits[0].content


def test_no_index_hit_does_not_search_content_directly(knowledge_assets):
    assert ChemKBPlugin().search("unindexed phrase") == []


def test_missing_graph_or_content_never_returns_entity_as_answer(knowledge_assets):
    db, cards = knowledge_assets
    cards.unlink()
    with pytest.raises(FileNotFoundError):
        ChemKBPlugin().search("SCF")
    db.unlink()
    with pytest.raises(FileNotFoundError):
        ChemKBPlugin().search("SCF")


def test_zero_limit_is_empty(knowledge_assets):
    assert ChemKBPlugin().search("SCF", limit=0) == []
