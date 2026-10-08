"""TS verdict output remains distinct from invocation and workflow completion."""

import pytest
from pydantic import ValidationError

from cloudra.tools.core.ts_state_view import TsProcessView, build_process_view


def test_verdict_output_rejects_unknown_outcome():
    """An arbitrary result label must not cross the recorded-verdict boundary."""
    with pytest.raises(ValidationError):
        TsProcessView(result={
            "outcome": "complete", "verified": True, "reason": "Claimed completion", "evidence_refs": [],
        })


@pytest.mark.parametrize("terminal,verified", [
    ("verified", True), ("candidate_only", False), ("search_failed", False), ("invalid_input", False),
])
def test_ended_workflow_preserves_recorded_scientific_verdict(tmp_path, terminal, verified):
    state = {
        "format_version": 4, "run_id": "ts_fixture", "revision": 1,
        "run_dir": str(tmp_path), "stage": "verdict", "terminal": terminal,
        "stage_records": [{"stage": "verdict", "status": "done", "detail": "Recorded reason"}],
        "evidence_candidates": ["frequency.out", "irc.out"],
    }
    view = build_process_view(state, [], can_write=False)
    assert view.status == "ended"
    assert view.result == {
        "outcome": terminal, "verified": verified, "reason": "Recorded reason",
        "evidence_refs": ["frequency.out", "irc.out"],
    }
    assert view.model_dump(mode="json")["result"] == view.result
