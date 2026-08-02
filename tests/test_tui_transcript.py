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
