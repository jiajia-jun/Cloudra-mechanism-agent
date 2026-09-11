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
