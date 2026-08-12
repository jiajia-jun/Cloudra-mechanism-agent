"""工具参数 JSON 宽松解析 / 修复。"""

from __future__ import annotations

import json
from pathlib import Path

from cloudra.infra.json_args import loads_tool_arguments, try_repair_tool_arguments_json


def test_repair_supervisor_criegee_mutate_fixture():
    """真实故障：6 个 add_node 的 payload.spec 各少一个 `}`。"""
    fixture = (
        Path.home()
        / ".local/share/cloudra/conversations"
        / "conv_20260812_064800_764a39"
        / "contexts"
        / "supervisor.json"
    )
    if not fixture.is_file():
        # CI / 无用户数据时用内嵌缩样
        raw = (
            '{"action":"mutate","operations":['
            '{"op":"add_node","graph":"process","data":{"node_id":"a","payload":{"spec":{"x":1}}}},'
            '{"op":"add_node","graph":"process","data":{"node_id":"b","payload":{"spec":{"x":2}}}}'
            "]}"
        )
        # 上面其实是合法的；构造非法版（每个 op 少一个 }）
        raw = (
            '{"action":"mutate","operations":['
            '{"op":"add_node","graph":"process","data":{"node_id":"a","payload":{"spec":{"x":1}}},'
            '{"op":"add_node","graph":"process","data":{"node_id":"b","payload":{"spec":{"x":2}}}}'
            "]}"
        )
    else:
        line = fixture.read_text(encoding="utf-8").splitlines()[26]
        raw = json.loads(line)["tool_calls"][0]["function"]["arguments"]

    assert json.loads  # silence linters
    try:
        json.loads(raw, strict=False)
        repaired_needed = False
    except json.JSONDecodeError:
        repaired_needed = True
    assert repaired_needed

    repaired = try_repair_tool_arguments_json(raw)
    assert repaired is not None
    data = json.loads(repaired)
    assert data["action"] == "mutate"
    assert len(data["operations"]) >= 2


def test_loads_tool_arguments_repairs_and_returns_dict():
    raw = (
        '{"action":"mutate","operations":['
        '{"op":"add_node","graph":"process","data":{"node_id":"a","payload":{"spec":{"x":1}}},'
        '{"op":"add_node","graph":"process","data":{"node_id":"b","payload":{"spec":{"x":2}}}}'
        "]}"
    )
    data = loads_tool_arguments(raw)
    assert [op["data"]["node_id"] for op in data["operations"]] == ["a", "b"]


def test_loads_tool_arguments_good_json_passthrough():
    data = loads_tool_arguments('{"action": "view", "graph_kind": "process"}')
    assert data == {"action": "view", "graph_kind": "process"}
