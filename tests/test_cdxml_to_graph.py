"""Tests for the CDXML reaction-scheme -> SMILES graph tool."""

import os

import pytest

import cloudra.tools.Chemtool.cdxml_to_graph as mod
from cloudra.tools.Chemtool.cdxml_to_graph import (
    CdxmlToGraph,
    CdxmlToGraph_input_schema,
)

pytestmark = pytest.mark.skipif(
    not mod._MOLLI_AVAILABLE or not mod._RDKIT_AVAILABLE,
    reason="molli/RDKit not installed; install with pip install 'cloudra[chem]'",
)

FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "complex_reaction.cdxml",
)


@pytest.fixture
def tool():
    return CdxmlToGraph()


async def _parse(tool, mock_session, *, save_mol2=False, path=FIXTURE):
    return await tool.tool_call(
        CdxmlToGraph_input_schema(cdxml_path=path, save_mol2=save_mol2),
        mock_session,
    )


@pytest.mark.asyncio
async def test_parse_complex_reaction_dag(tool, mock_session):
    """复杂多步反应路线可解析为 SMILES 图，且是 DAG 并给出提案。"""
    result = await _parse(tool, mock_session)

    assert result.is_success is True, result.message
    graph = result.graph
    assert graph["is_dag"] is True
    assert len(graph["nodes"]) >= 4
    assert len(graph["edges"]) >= 3

    # 所有节点都应是带手性的 SMILES（fixture 里有手性中心）
    all_smiles = [n["smiles"] for n in graph["nodes"] if n.get("smiles")]
    assert all_smiles
    assert any("[C@H]" in s or "[C@@H]" in s for s in all_smiles)

    # 路径至少有一条从 reactant complex 到 product complex 的边
    edge = graph["edges"][0]
    assert edge["source_node_id"].startswith("cdx_")
    assert edge["target_node_id"].startswith("cdx_")
    assert "metadata" in edge

    # 至少一条边带溶剂/条件 annotation
    assert any(e.get("annotations") for e in graph["edges"])
    assert any(
        e["metadata"].get("conditions") or e["metadata"].get("solvents")
        for e in graph["edges"]
    )

    # DAG 模式下返回可直接提交的 dag_propose_mechanism payload
    assert result.dag_proposal is not None
    assert len(result.dag_proposal["operations"]) >= len(graph["edges"])
    assert set(result.dag_proposal["stage_contracts"]) >= {
        e["edge_id"] for e in graph["edges"]
    }


@pytest.mark.asyncio
async def test_save_mol2_optional(tool, mock_session, tmp_path):
    """save_mol2=True 时在会话目录下写出 .mol2 文件。"""
    session_path = tmp_path / "session.json"
    mock_session.path = str(session_path)
    result = await _parse(tool, mock_session, save_mol2=True)

    assert result.is_success is True
    assert result.mol2_files
    for frag_id, path in result.mol2_files.items():
        assert os.path.isfile(path), path
        text = open(path).read()
        assert "@<TRIPOS>MOLECULE" in text


@pytest.mark.asyncio
async def test_missing_file(tool, mock_session, tmp_path):
    result = await tool.tool_call(
        CdxmlToGraph_input_schema(cdxml_path=str(tmp_path / "nope.cdxml")),
        mock_session,
    )
    assert result.is_success is False
    assert "File not found" in result.message


def test_build_graph_handles_cycle_detection():
    """非 DAG 图返回参考图而不是 dag_proposal。"""
    from cloudra.tools.Chemtool.cdxml_to_graph import _build_graph

    def info(smi):
        return mod._FragmentInfo(
            frag_id=smi,
            box=(0, 0, 10, 10),
            smiles=smi,
            formula="",
            charge=0,
            multiplicity=1,
            connectivity=[],
        )

    reactions = [
        {
            "arrow_id": "a1",
            "reactants": [info("A")],
            "products": [info("B")],
            "reagents": [],
            "solvents": [],
            "conditions": [],
            "raw_texts": [],
        },
        {
            "arrow_id": "a2",
            "reactants": [info("B")],
            "products": [info("A")],
            "reagents": [],
            "solvents": [],
            "conditions": [],
            "raw_texts": [],
        },
    ]
    graph, dag_proposal, warnings, unresolved = _build_graph(reactions)
    assert graph["is_dag"] is False
    assert graph["cycles"]
    assert dag_proposal is None
    assert unresolved == []


def test_registry_contains_tool():
    from cloudra.tools.registry import TOOL_REGISTRY

    assert any(r.tool_name == "cdxml_to_graph" for r in TOOL_REGISTRY)


NO_ARROW_FIXTURE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "no_arrow_structures.cdxml",
)


@pytest.mark.asyncio
async def test_no_arrow_returns_standalone_structures(tool, mock_session):
    """只有结构没有箭头时，返回独立节点而不是空图，且不生成 DAG 提案。"""
    result = await _parse(tool, mock_session, path=NO_ARROW_FIXTURE)

    assert result.is_success is True, result.message
    graph = result.graph
    assert len(graph["nodes"]) == 2
    assert graph["edges"] == []
    assert graph["is_dag"] is True
    assert result.dag_proposal is None
    assert any(
        "no reaction arrows found" in w for w in result.warnings
    )
    assert all(n["smiles"] for n in graph["nodes"])
    assert all(n["role"] is None for n in graph["nodes"])


# ---------------------------------------------------------------------------
# F9：垂直箭头（hx==tx）方向判定必须用 y 分量，不能把 head 钉在左侧
# ---------------------------------------------------------------------------


def _arrow(box, head, tail):
    return {"BoundingBox": box, "Head3D": head, "Tail3D": tail}


def test_horizontal_arrow_regions_unaffected():
    """水平左→右箭头：tail 在左、head 在右（原行为回归）。"""
    regions = mod._arrow_regions(_arrow("100 100 300 150", "300 120 0", "100 120 0"))
    left_box = (30, 90, 60, 160)      # 左侧碎片
    right_box = (330, 90, 360, 160)   # 右侧碎片
    assert mod._contains_center(regions["tail"], left_box) is True
    assert mod._contains_center(regions["head"], right_box) is True
    assert mod._contains_center(regions["tail"], right_box) is False
    assert mod._contains_center(regions["head"], left_box) is False


def test_vertical_upward_arrow_places_head_above_and_tail_below():
    """垂直向上箭头（hx==tx，hy>ty）：head 必须在箭头上方、tail 在下方。"""
    regions = mod._arrow_regions(_arrow("100 100 102 300", "100 300 0", "100 100 0"))
    above = (90, 330, 112, 360)  # 箭头上方的产物区
    below = (90, 60, 112, 90)    # 箭头下方的反应物区
    assert mod._contains_center(regions["head"], above) is True
    assert mod._contains_center(regions["tail"], below) is True
    # 旧实现把 head 钉在左侧垂直条，上方产物会被误归为试剂（top/bottom）
    assert mod._contains_center(regions["tail"], above) is False


def test_vertical_downward_arrow_flips_sides():
    """垂直向下箭头：head 在下方、tail 在上方。"""
    regions = mod._arrow_regions(_arrow("100 100 102 300", "100 100 0", "100 300 0"))
    below = (90, 30, 112, 60)
    above = (90, 330, 112, 360)
    assert mod._contains_center(regions["head"], below) is True
    assert mod._contains_center(regions["tail"], above) is True


# ---------------------------------------------------------------------------
# T4：fragment 全文件只解析一次（旧实现解析两遍、第二遍静默丢异常）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fragments_are_parsed_exactly_once(tool, mock_session, monkeypatch):
    """每个 fragment 的 molli→SMILES 解析恰好发生一次：_collect_reactions
    只消费调用方传入的解析结果，不再自行重解析。"""
    calls: list[str] = []
    original = mod._fragment_to_info

    def spy(cdxml_file, frag, **_kwargs):
        calls.append(str(frag.get("id")))
        return original(cdxml_file, frag, **_kwargs)

    monkeypatch.setattr(mod, "_fragment_to_info", spy)
    result = await _parse(tool, mock_session)

    assert result.is_success is True, result.message
    assert calls, "fixture 里应有 fragment 被解析"
    assert len(calls) == len(set(calls)), f"存在重复解析: {calls}"


@pytest.mark.asyncio
async def test_fragment_parse_failure_is_warned_not_silent(tool, mock_session, monkeypatch):
    """单趟解析中失败的 fragment 必须落 warning（不再被第二遍 except 静默吞掉）。"""
    original = mod._fragment_to_info

    def fail_first(cdxml_file, frag, **_kwargs):
        if not getattr(fail_first, "_done", False):
            fail_first._done = True
            raise ValueError("simulated fragment parse failure")
        return original(cdxml_file, frag, **_kwargs)

    monkeypatch.setattr(mod, "_fragment_to_info", fail_first)
    result = await _parse(tool, mock_session)

    assert result.is_success is True, result.message
    assert any("simulated fragment parse failure" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# T5：溶剂识别按完整 token 精确比对；条件抽取为显式 token 扫描（无正则）
# ---------------------------------------------------------------------------


def _classify(raw: str) -> dict:
    reactions = [{"solvents": [], "conditions": [], "reagents": []}]
    mod._classify_text(raw, "top/bottom", reactions)
    return reactions[0]


def test_solvent_matching_uses_whole_tokens():
    """子串匹配的旧假阳性必须消失："lipase" 不含溶剂 "ipa"、"DMAP" 不含 "dma"；
    真正的溶剂 token（含多词条目）照常命中。"""
    hit = _classify("lipase from Candida rugosa")
    assert hit["solvents"] == []
    assert "lipase from Candida rugosa" in hit["reagents"]

    hit = _classify("DMAP")
    assert hit["solvents"] == []
    assert "DMAP" in hit["reagents"]

    assert "THF" in _classify("THF")["solvents"]
    assert _classify("ethyl acetate")["solvents"]
    assert _classify("CH2Cl2, anhydrous")["solvents"]


def test_parse_condition_text_explicit_token_scanning():
    """条件抽取：温度/时间/搅拌/压力/气体的 token 扫描结果与旧正则语义一致。"""
    cond = mod._parse_condition_text("-78 °C, 12 h, 300 rpm, 2 bar, N2")
    assert cond["temperature"] == "-78 C"
    assert cond["reaction_time"] == "12 hr"
    assert cond["stir_speed"] == "300 RPM"
    assert cond["pressure"] == "2 BAR"
    assert cond["gas"] == "N2"

    cond = mod._parse_condition_text("rt, 30 min")
    assert cond["temperature"] == "rt"
    assert cond["reaction_time"] == "0.5 hr"

    cond = mod._parse_condition_text("80°C overnight")
    assert cond["temperature"] == "80 C"
    assert cond["reaction_time"] == "overnight"

    # 数值与单位不配对时不猜：裸单位/无单位都不给结构化条件
    cond = mod._parse_condition_text("some additive")
    assert all(cond[k] is None for k in ("temperature", "reaction_time", "stir_speed", "pressure", "gas"))


def test_module_has_no_regex():
    """校验路径一律不准有正则：本模块不得再 import re（AGENTS.md 硬约束）。"""
    source = open(mod.__file__, encoding="utf-8").read()
    import_lines = [
        line.strip() for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any(
        line == "import re" or line.startswith("import re ") or line == "from re import"
        or line.startswith("from re import ")
        for line in import_lines
    ), import_lines
    assert "re.sub(" not in source and "re.search(" not in source and "re.match(" not in source
    assert not hasattr(mod, "re")
