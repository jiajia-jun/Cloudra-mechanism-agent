from cloudra.tui.new.transcript import TranscriptStore


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
