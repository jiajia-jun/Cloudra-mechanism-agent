from cloudra.tui.new.transcript import RecordKind, TranscriptStore


def test_renaming_pending_session_derives_its_formal_agent_id():
    store = TranscriptStore()
    pending = store.append_user("_pending", "主消息")

    store.rename_session("_pending", "a-0_run_1")

    assert store.get(pending).agent_id == "a-0"
    assert [record.record_id for record in store.visible_records(agent_prefix="a-0")] == [
        pending.record_id
    ]


def test_renaming_session_preserves_an_explicit_agent_id():
    store = TranscriptStore()
    record = store.append(
        "a-0_run_1",
        RecordKind.USER,
        agent_id="a-0",
        content="主消息",
    )

    store.rename_session("a-0_run_1", "a-1_run_1")

    assert store.get(record).agent_id == "a-0"
    assert [item.record_id for item in store.visible_records(agent_prefix="a-0")] == [
        record.record_id
    ]


def test_store_preserves_order_and_filters_without_copying_payloads():
    store = TranscriptStore()
    first = store.append_user("a-0_run_1", "主消息", message_id="m-1")
    duplicate = store.append_user("a-0_run_1", "主消息", message_id="m-1")
    child = store.append_user("a-3_task_1", "子消息")

    assert duplicate == first
    assert [record.record_id for record in store.records] == [
        first.record_id,
        child.record_id,
    ]
    assert [record.content for record in store.visible_records(agent_prefix="a-3")] == [
        "子消息"
    ]

    store.mark_send_failed(first)
    assert store.get(first).send_failed
    assert store.get(first).revision == 1

    store.rename_session("a-0_run_1", "a-0_run_2")
    assert [record.content for record in store.records_for_session("a-0_run_2")] == [
        "主消息"
    ]

    store.clear_session("a-3_task_1")
    assert [record.content for record in store.records] == ["主消息"]

    store.clear()
    assert store.records == ()


def test_stream_finalizes_in_place_around_tools_and_keeps_full_content():
    store = TranscriptStore()
    stream = store.start_stream("a-0_run_1", "coordinator")

    store.append_stream_chunk("a-0_run_1", "BEGIN-" + "x" * 25_000)
    store.append_tool("a-0_run_1", "Bash", "pwd")
    store.append_reasoning_chunk("a-0_run_1", "check")
    store.append_stream_chunk("a-0_run_1", "-END")
    store.end_stream("a-0_run_1")

    record = store.records[0]
    assert record.record_id == stream.record_id
    assert record.content.startswith("BEGIN-") and record.content.endswith("-END")
    assert len(record.content) == 25_010 and record.reasoning == "check"
    assert record.status == "finished"
    assert store.records[1].kind is RecordKind.TOOL


def test_tool_finish_updates_one_record_and_toggle_revisions_it():
    store = TranscriptStore()
    handle = store.append_tool("s1", "Bash", "pwd")

    assert store.append_tool("s1", "Bash", "pwd", finished=True, result="/tmp") == handle
    assert len(store.records) == 1 and store.get(handle).status == "finished"

    change = store.toggle_collapsed(handle)

    assert change.record_ids == (handle.record_id,)
    assert store.get(handle).collapsed
    assert store.get(handle).revision == 2


def test_unknown_stream_end_is_ignored_and_chunks_start_a_single_active_record():
    store = TranscriptStore()

    assert store.end_stream("s1") is None
    first = store.append_stream_chunk("s1", "one")
    second = store.append_reasoning_chunk("s1", "think")

    assert first == second == store.active_stream("s1")
    assert len(store.records) == 1
    assert store.get(first).content == "one"
    assert store.get(first).reasoning == "think"


def test_implicit_stream_start_reports_insertion_and_duplicate_end_is_ignored():
    store = TranscriptStore()

    handle = store.append_stream_chunk("s1", "one")

    assert store.last_change.record_ids == (handle.record_id,)
    assert store.last_change.order_changed
    assert store.last_change.visibility_changed

    assert store.end_stream("s1") == handle
    revision = store.get(handle).revision
    assert store.end_stream("s1") is None
    assert store.get(handle).revision == revision


def test_unmatched_finished_tool_is_retained_and_long_result_starts_collapsed():
    store = TranscriptStore()

    handle = store.append_tool(
        "s1",
        "Bash",
        "pytest",
        finished=True,
        result="\n".join(str(line) for line in range(9)),
    )

    record = store.get(handle)
    assert record.status == "finished"
    assert record.result == "\n".join(str(line) for line in range(9))
    assert record.collapsed


def test_duplicate_unmatched_finished_tools_remain_independent_records():
    store = TranscriptStore()

    first = store.append_tool("s1", "Bash", "pwd", finished=True, result="/one")
    second = store.append_tool("s1", "Bash", "pwd", finished=True, result="/two")

    assert second != first
    assert [record.result for record in store.records] == ["/one", "/two"]


def test_outermost_batch_unions_changes_once():
    store = TranscriptStore()

    with store.batch():
        stream = store.append_stream_chunk("s1", "text")
        with store.batch():
            tool = store.append_tool("s1", "Bash", "pwd")
        store.end_stream("s1")

    assert store.last_change.record_ids == (stream.record_id, tool.record_id)
    assert store.last_change.order_changed
    assert store.last_change.visibility_changed
