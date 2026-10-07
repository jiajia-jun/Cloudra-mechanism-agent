"""模型工具参数的真实解析入口：离线、完整保留、非法时明确失败。"""

from __future__ import annotations

import pytest

from cloudra.runtime_v2.adapters import _parse_merged_tool_calls


def test_tool_arguments_preserve_complete_nested_payload():
    raw = (
        '{"action":"mutate","operations":['
        '{"op":"add_node","graph":"process","data":{"node_id":"a",'
        '"payload":{"spec":{"x":1,"label":"含 {, } 字符"}}}},'
        '{"op":"add_node","graph":"process","data":{"node_id":"b",'
        '"payload":{"spec":{"x":2,"tags":["candidate",null],"enabled":false}}}}'
        ']}'
    )
    calls = _parse_merged_tool_calls([{
        "id": "nested-batch",
        "function": {"name": "dag_mutate", "arguments": raw},
    }])

    assert len(calls) == 1
    assert calls[0].id == "nested-batch"
    assert calls[0].name == "dag_mutate"
    assert calls[0].arguments == {
        "action": "mutate",
        "operations": [
            {
                "op": "add_node",
                "graph": "process",
                "data": {"node_id": "a", "payload": {"spec": {"x": 1, "label": "含 {, } 字符"}}},
            },
            {
                "op": "add_node",
                "graph": "process",
                "data": {"node_id": "b", "payload": {"spec": {"x": 2, "tags": ["candidate", None], "enabled": False}}},
            },
        ],
    }


@pytest.mark.parametrize("raw", [
    "",
    "   ",
    '{"reason":"unfinished}',
    '{"reason":"done",}',
    '{"content":"line1\nline2"}',
    # 历史故障的离线缩样：首个 operation 少一个 }，不许猜测修复。
    '{"action":"mutate","operations":['
    '{"op":"add_node","graph":"process","data":{"node_id":"a","payload":{"spec":{"x":1}}},'
    '{"op":"add_node","graph":"process","data":{"node_id":"b","payload":{"spec":{"x":2}}}}'
    ']}'
])
def test_malformed_tool_arguments_fail_instead_of_becoming_empty_object(raw):
    with pytest.raises(ValueError):
        _parse_merged_tool_calls([{
            "id": "malformed", "function": {"name": "stop", "arguments": raw},
        }])


@pytest.mark.parametrize("raw", ["[]", "null", "true", "3", '"value"'])
def test_non_object_tool_arguments_fail_instead_of_becoming_empty_object(raw):
    with pytest.raises(ValueError):
        _parse_merged_tool_calls([{
            "id": "non-object", "function": {"name": "stop", "arguments": raw},
        }])


@pytest.mark.parametrize("raw", [
    '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e309}',
    '{"nested":[{"x":-1e309}]}',
])
def test_non_finite_tool_argument_values_are_rejected(raw):
    with pytest.raises(ValueError):
        _parse_merged_tool_calls([{
            "id": "non-finite", "function": {"name": "probe", "arguments": raw},
        }])


@pytest.mark.parametrize("raw", [
    '{"x":1,"x":2}', '{"x":1,"\\u0078":2}',
    '{"nested":{"x":1,"x":2}}', '{"nested":[{"x":1,"x":2}]}',
])
def test_duplicate_tool_argument_keys_are_rejected_without_losing_values(raw):
    with pytest.raises(ValueError):
        _parse_merged_tool_calls([{
            "id": "duplicate-key", "function": {"name": "probe", "arguments": raw},
        }])


@pytest.mark.parametrize("raw,expected", [
    ('{"x":1e3,"label":"NaN Infinity -Infinity"}', {"x": 1000.0, "label": "NaN Infinity -Infinity"}),
    ('{"nested":[{"x":1},{"x":2}]}', {"nested": [{"x": 1}, {"x": 2}]}),
    ('{"content":"line1\\nline2\\nline3"}', {"content": "line1\nline2\nline3"}),
])
def test_strict_json_rules_preserve_valid_numbers_strings_and_separate_object_keys(raw, expected):
    calls = _parse_merged_tool_calls([{
        "id": "valid-boundary", "function": {"name": "probe", "arguments": raw},
    }])
    assert len(calls) == 1
    assert calls[0].arguments == expected


@pytest.mark.parametrize("field,value", [
    ("arguments", None), ("arguments", {}), ("arguments", []), ("arguments", 1),
    ("id", None), ("id", ""), ("id", "   "), ("id", 1),
    ("name", None), ("name", ""), ("name", "   "), ("name", 1),
])
def test_invalid_tool_call_envelope_is_rejected(field, value):
    raw = {"id": "tc1", "function": {"name": "stop", "arguments": "{}"}}
    target = raw if field == "id" else raw["function"]
    target[field] = value
    with pytest.raises(ValueError):
        _parse_merged_tool_calls([raw])


@pytest.mark.parametrize("field", ["id", "function", "name", "arguments"])
def test_missing_tool_call_envelope_field_is_rejected(field):
    raw = {"id": "tc1", "function": {"name": "stop", "arguments": "{}"}}
    target = raw if field in {"id", "function"} else raw["function"]
    del target[field]
    with pytest.raises(ValueError):
        _parse_merged_tool_calls([raw])


def test_tool_arguments_preserve_each_call_identity_order_and_empty_object():
    calls = _parse_merged_tool_calls([
        {"id": "first", "function": {"name": "stop", "arguments": '{"reason":"done"}'}},
        {"id": "second", "function": {"name": "dag_view", "arguments": "{}"}},
    ])
    assert [(call.id, call.name, call.arguments) for call in calls] == [
        ("first", "stop", {"reason": "done"}),
        ("second", "dag_view", {}),
    ]


def test_valid_call_does_not_hide_a_later_malformed_call():
    with pytest.raises(ValueError):
        _parse_merged_tool_calls([
            {"id": "valid", "function": {"name": "stop", "arguments": '{"reason":"done"}'}},
            {"id": "invalid", "function": {"name": "stop", "arguments": '{"reason":'}},
        ])
