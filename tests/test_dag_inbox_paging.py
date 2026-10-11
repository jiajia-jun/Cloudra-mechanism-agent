"""Large DAG evidence inboxes stay bounded and readable by page."""

import json

import pytest

from cloudra.tools.Plantool.dag_tools.dag_view import DagView
from tests.dag_identity import make_session
from tests.test_dag_tools import _agent, _call


@pytest.mark.asyncio
async def test_compact_view_keeps_large_unassigned_evidence_in_a_bounded_inbox(tmp_path, monkeypatch):
    from cloudra.dag.store import DagStore

    # Read-layer fixture models the native NU3 inbox: many unbound facts,
    # each carrying a long diagnostic plus a full immutable reference.
    facts = [dict(category="untargeted_key_fact", fact_id=f"fact_{i}",
                  check="identity", outcome="supports", target_id=None,
                  detail="diagnostic " * 100,
                  source_refs=[dict(ref_type="tool_result", ref_id=f"evidence_{i}",
                                    content_hash="sha256:" + "a" * 64)]) for i in range(182)]
    monkeypatch.setattr(DagStore, "collect_review_exceptions", lambda *_: facts)
    result = await _call(DagView, _agent("bounded-inbox", "dag_guided"),
                         make_session("bounded-inbox", "coordinator"))
    assert result.is_success
    assert len(json.dumps(result.model_dump(), ensure_ascii=False).encode()) < 16_384
    assert result.result["unassigned_evidence_count"] == 182
    assert len(result.result["unassigned_evidence"]) == 20
    assert result.result["unassigned_evidence_next_offset"] == 20
    page = await _call(DagView, _agent("bounded-inbox", "dag_guided"),
                       make_session("bounded-inbox", "coordinator"), offset=180)
    assert [x["fact_id"] for x in page.result["unassigned_evidence"]] == ["fact_180", "fact_181"]
    assert page.result["unassigned_evidence_next_offset"] is None

