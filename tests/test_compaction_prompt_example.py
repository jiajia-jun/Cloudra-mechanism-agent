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
    _MINIMAL_EXAMPLE_NOTE,
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
    assert set(data) == {"objective", "active_requests", *_EMPTY_LIST_FIELDS}
    assert set(data["objective"]) == {"text", "sources"}
    assert all(type(index) is int for index in data["objective"]["sources"])
    summary = CompactSummary.model_validate(data)
    assert summary.objective.text.strip()
    assert summary.active_requests == []
    for field in _EMPTY_LIST_FIELDS:
        assert getattr(summary, field) == []


def test_minimal_example_adds_no_obligation_beyond_its_hypothetical_line():
    note, separator, displayed_json = _MINIMAL_EXAMPLE_NOTE.rpartition("\n\n")
    assert separator and displayed_json == _MINIMAL_EXAMPLE_JSON
    source_label, role_separator, request = note.splitlines()[-1].partition(" user: ")
    assert role_separator and source_label.startswith("[") and source_label.endswith("]")
    source_index = int(source_label[1:-1])

    data = json.loads(displayed_json)
    assert data["objective"] == {"text": request, "sources": [source_index]}
    assert data["active_requests"] == []
    for field in _EMPTY_LIST_FIELDS:
        assert data[field] == []


def test_minimal_example_survives_the_production_parser_with_zero_clamps():
    summary = parse_compact_summary(_MINIMAL_EXAMPLE_JSON, trajectory_len=1)
    assert summary.objective.text.strip()
    assert summary.objective.sources == [0]
    assert summary.clamped_sources == 0


def test_minimal_example_is_wired_into_both_summary_instructions():
    assert _COMPACT_INSTRUCTION.endswith(_MINIMAL_EXAMPLE_JSON)
    assert _MERGE_INSTRUCTION.endswith(_MINIMAL_EXAMPLE_JSON)
