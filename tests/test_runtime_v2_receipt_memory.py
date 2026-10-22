"""Activity summaries must release raw tool payloads while preserving job links."""

import gc
import weakref

from cloudra.runtime_v2.observability import call_summary, tool_receipts
from cloudra.runtime_v2.schemas import EventEnvelope


class Payload(dict):
    pass


def receipt_events(refs):
    base = dict(stream="agent", project_id="p", session_id="a", run_id="r")
    arguments = Payload(input="x" * 100_000)
    raw_result = Payload(is_success=True, data={"job_id": 17, "text": "y" * 100_000})
    refs.extend([weakref.ref(arguments), weakref.ref(raw_result)])
    yield EventEnvelope(
        **base, seq=1, session_seq=1, event_id="requested", type="tool.requested",
        data={"tool_call_id": "call", "tool_name": "submit_compute_job", "arguments_summary": arguments},
    )
    yield EventEnvelope(
        **base, seq=2, session_seq=2, type="tool.result_recorded",
        data={"tool_call_id": "call", "result": raw_result},
    )
    yield EventEnvelope(
        **base, seq=3, session_seq=3, type="tool.finished",
        data={"tool_call_id": "call", "status": "completed", "result_summary": "z" * 100_000},
    )


def test_activity_receipts_release_full_inputs_and_outputs():
    refs = []
    rows = tool_receipts(receipt_events(refs), details=False)
    gc.collect()
    assert all(ref() is None for ref in refs), "summary receipts keep full raw payloads alive"
    summary = call_summary(rows[0])
    assert summary["request_event_id"] == "requested"
    assert summary["compute_job_ids"] == [17]
    assert summary["result_availability"] == "available"
    assert summary["status"] == "completed"
    assert summary["summary_truncated"] is True
    assert summary["result_summary"] == "z" * 500


def test_detailed_receipts_keep_complete_evidence():
    refs = []
    row = tool_receipts(receipt_events(refs), details=True)[0]
    assert row["arguments"]["input"] == "x" * 100_000
    assert row["result"]["data"]["text"] == "y" * 100_000
    assert row["result_summary"] == "z" * 100_000
    assert len(row["events"]) == 3


def test_requested_detail_does_not_retain_other_attempt_payloads():
    refs = []

    def events():
        yield from receipt_events(refs)
        yield EventEnvelope(
            stream="agent", project_id="p", session_id="a", run_id="r", seq=4,
            session_seq=4, event_id="selected", type="tool.requested",
            data={"tool_call_id": "new", "tool_name": "echo", "arguments_summary": {"value": 7}},
        )

    rows = tool_receipts(events(), details=True, request_event_ids={"selected"})
    gc.collect()
    assert all(ref() is None for ref in refs)
    assert len(rows) == 1
    assert rows[0]["request_event_id"] == "selected"
    assert rows[0]["arguments"] == {"value": 7}
