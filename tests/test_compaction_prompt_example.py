"""GH #48 建议 4：摘要 prompt 的最小合法示例必须「自身严格合法」。

背景：thinking 模型首答不合九键 schema 是压缩拒替换的主因之一（GH #48 实测：
objective 裸字符串 / 单元素数组 / 围栏+散文）。形状说明后附一个最小合法示例
用于压低再现率，但示例一旦写得不再合法，就会把模型引向错误形状——所以这里
用与模型输出**同一套**校验把示例钉死，且刻意走严格路径（json.loads +
CompactSummary.model_validate，不经 _strip_code_fence / _promote_summary_shapes
的容错）：示例不合法或依赖容错才能过，本用例直接变红。
"""

import json

from cloudra.runtime_v2.compaction import (
    _COMPACT_INSTRUCTION,
    _MERGE_INSTRUCTION,
    _MINIMAL_EXAMPLE_JSON,
    CompactSummary,
    parse_compact_summary,
)

_EMPTY_LIST_FIELDS = (
    "corrections",
    "constraints",
    "pending",
    "completed",
    "failed_attempts",
    "evidence",
    "next_actions",
)


def test_minimal_example_passes_strict_validation_without_tolerance_paths():
    data = json.loads(_MINIMAL_EXAMPLE_JSON)
    summary = CompactSummary.model_validate(data)
    assert summary.objective.text.strip()
    assert len(summary.active_requests) == 1
    assert summary.active_requests[0].text.strip()
    for field in _EMPTY_LIST_FIELDS:
        assert getattr(summary, field) == []


def test_minimal_example_survives_the_production_parser_with_zero_clamps():
    summary = parse_compact_summary(_MINIMAL_EXAMPLE_JSON, trajectory_len=2)
    assert summary.objective.text.strip()
    assert summary.clamped_sources == 0


def test_minimal_example_is_wired_into_both_summary_instructions():
    assert _MINIMAL_EXAMPLE_JSON in _COMPACT_INSTRUCTION
    assert _MINIMAL_EXAMPLE_JSON in _MERGE_INSTRUCTION


def test_minimal_example_shows_object_and_array_shapes_literally():
    # 三种畸形里最容易复发的是「objective 写成裸字符串/数组」与「空字段写 null
    # 或省略」：示例必须逐字展示 object 与 [] 形状，而不是靠文字描述。
    assert _MINIMAL_EXAMPLE_JSON.lstrip().startswith("{")
    assert '"objective": {' in _MINIMAL_EXAMPLE_JSON
    for field in _EMPTY_LIST_FIELDS + ("active_requests",):
        assert f'"{field}": [' in _MINIMAL_EXAMPLE_JSON
    assert "null" not in _MINIMAL_EXAMPLE_JSON.replace('"null"', "")
