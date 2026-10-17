"""Graph-as-index health uses only the graph and complete source content."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from cloudra.knowledge import store


@pytest.fixture(autouse=True)
def _isolate_cards(tmp_path, monkeypatch):
    from cloudra.knowledge import content
    from cloudra.persistence import paths

    monkeypatch.setattr(paths, "knowledge_cards_path", lambda: tmp_path / "cards.jsonl")
    content._reset_cache()
    yield
    content._reset_cache()


def _build_db(tmp_path: Path) -> Path:
    e_csv = tmp_path / "e.csv"
    with e_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "type", "label", "smiles", "props", "n_sources"])
        writer.writeheader()
        writer.writerow({"id": "concept:过渡态", "type": "concept", "label": "过渡态", "n_sources": "1"})
    r_csv = tmp_path / "r.csv"
    r_csv.write_text("src_id,dst_id,rel_type,evidence_level,source,falsified,note\n", encoding="utf-8-sig")
    db = tmp_path / "knowledge" / "chem_kg.db"
    store.import_csv(db, e_csv, r_csv)
    return db


def _write_cards(tmp_path: Path) -> None:
    cards = [
        {"card_id": "kb:1:0", "heading": "首段", "content": "正文", "lang": "zh"},
        {"card_id": "kb:1:0", "heading": "First", "content": "Text", "lang": "en"},
        {"card_id": "kb:1:1", "heading": "第二段", "content": "续文", "lang": "zh"},
        {"card_id": "org:source:chapter:0", "heading": "章节", "content": "来源正文", "lang": "zh"},
    ]
    (tmp_path / "cards.jsonl").write_text(
        "\n".join(json.dumps(card, ensure_ascii=False) for card in cards), encoding="utf-8"
    )


def test_knowledge_health_has_only_graph_and_content():
    from cloudra.knowledge.health import knowledge_health

    result = knowledge_health()
    assert set(result) == {"graph", "content"}
    assert all(channel["ok"] is False and channel["error"] for channel in result.values())


def test_graph_health_with_imported_db(tmp_path):
    from cloudra.knowledge.health import graph_health

    assert graph_health(_build_db(tmp_path)) == {"ok": True, "entities": 1, "relations": 0}


def test_content_health_counts_sources_not_chunks_or_languages(tmp_path):
    from cloudra.knowledge.health import content_health

    _write_cards(tmp_path)
    assert content_health() == {"ok": True, "sources": 2}


def test_content_health_reports_invalid_json(tmp_path):
    from cloudra.knowledge.health import content_health

    (tmp_path / "cards.jsonl").write_text("broken json", encoding="utf-8")
    result = content_health()
    assert result["ok"] is False
    assert result["error"]


def test_content_health_empty_library_is_unavailable(tmp_path):
    from cloudra.knowledge.health import content_health

    (tmp_path / "cards.jsonl").write_text("", encoding="utf-8")
    assert content_health() == {"ok": False, "sources": 0}


def test_knowledge_health_api_route(tmp_path):
    from fastapi.testclient import TestClient

    from cloudra.services.api_v2 import create_v2_app

    _write_cards(tmp_path)
    response = TestClient(create_v2_app()).get("/api/v2/knowledge/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"graph", "content"}
    assert body["content"] == {"ok": True, "sources": 2}


def test_knowledge_status_cli(tmp_path):
    from click.testing import CliRunner

    from cloudra.cli import cli

    _write_cards(tmp_path)
    result = CliRunner().invoke(cli, ["knowledge", "status"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "chem-kb" in result.output
    assert "2 篇来源" in result.output
    assert result.output.count("✓") == 1
    assert result.output.count("✗") == 1
