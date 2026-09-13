"""Commit prepared notices in standalone manager/pipeline tests."""

from types import SimpleNamespace

from cloudra.runtime_v2.apply import apply_event
from cloudra.runtime_v2.events import EventLog


def commit_notices(notices, session_id):
    messages, through = notices.pending_batch(session_id)
    if through is None:
        return messages
    data = {"messages": messages, "notices_through": through}
    event = notices._emit("context.appended", session_id, data)
    if event is None:
        event = EventLog(strict=True).append(
            "context.appended", stream="agent", project_id="prj",
            session_id=session_id, data=data,
        )
    apply_event(SimpleNamespace(notices=notices, session_contexts={}), event)
    return messages
