from cloudra.infra.tool_presentation import format_tool_payload


def test_decodes_unicode_and_nested_json_strings():
    payload = '{"result": "{\\\"message\\\": \\\"\\u4f60\\u597d，云端已完成\\\"}"}'
    rendered = format_tool_payload(payload, is_result=True)
    assert "你好，云端已完成" in rendered
    assert "\\u4f60" not in rendered
    assert "{" not in rendered


def test_redacts_secrets_and_bounds_collections():
    payload = {"api_key": "sk-private", "items": list(range(30))}
    rendered = format_tool_payload(payload)
    assert "sk-private" not in rendered
    assert "[已隐藏]" in rendered
    assert "另有 20 项" in rendered


def test_prefers_result_but_keeps_small_metadata():
    rendered = format_tool_payload(
        {"result": "计算完成", "job_id": "42", "state": "done"}, is_result=True
    )
    assert rendered.startswith("计算完成")
    assert "job_id: 42" in rendered


def test_long_text_is_truncated():
    rendered = format_tool_payload("x" * 100, max_chars=20)
    assert rendered.startswith("x" * 20)
    assert rendered.endswith("结果预览已截断")
