"""交付文件只用一套格式解析；DAG 科学验收继续单独执行。"""

import asyncio
import json

import pytest
from pydantic import ValidationError

from cloudra.benchmark import integrity
from cloudra.dag.delivery_artifact import prepare_delivery_artifact
from tests.test_dag_delivery_artifact import controller


@pytest.mark.parametrize("document", [{}, {"edges": []}, {"nodes": None}, {"nodes": {}}])
def test_scoring_does_not_treat_missing_or_nonlist_nodes_as_empty_graph(tmp_path, document):
    path = tmp_path / "mechanism_graph.json"
    path.write_text(json.dumps(document))

    assert integrity.load_delivered_graph(path) is None


@pytest.mark.parametrize(
    ("document", "message"),
    [([], "object"), ({}, "nodes"), ({"nodes": None}, "nodes"), ({"nodes": {}}, "nodes")],
)
def test_parser_reports_the_invalid_graph_field(document, message):
    with pytest.raises(ValueError, match=message):
        integrity.parse_delivered_graph(document)


def test_parser_preserves_existing_delivery_aliases_and_optional_edge_id():
    document = {
        "metadata": {"note": "authored delivery"},
        "nodes": [
            {"id": "R", "type": "reactant", "role": "starting complex", "smiles": "O"},
            {"id": "P", "type": "product", "smiles": "O", "extra": "ignored"},
            {"id": "TS", "type": "ts"},
        ],
        "edges": [{"source": "R", "target": "P", "via": "TS", "extra": "ignored"}],
    }

    graph = integrity.parse_delivered_graph(document)

    assert [node.role.value for node in graph.nodes] == ["reactant", "product", "transition_state"]
    assert graph.nodes[0].smiles == ["O"]
    assert graph.nodes[0].label == "starting complex"
    assert graph.nodes[2].smiles == []
    assert graph.edges[0].id == "e0"
    assert (graph.edges[0].from_node, graph.edges[0].to_node, graph.edges[0].via) == ("R", "P", "TS")


def test_parser_reports_a_nonstring_role_as_validation_error():
    document = {"nodes": [{"id": "R", "type": "reactant", "role": []}]}

    with pytest.raises(ValidationError) as error:
        integrity.parse_delivered_graph(document)

    assert error.value.errors()[0]["loc"] == ("role",)


@pytest.mark.parametrize(
    ("edge", "message"),
    [
        ({"from": "R", "to": "missing"}, "missing"),
        ({"from": "R", "to": "R", "via": "R"}, "transition_state"),
    ],
)
def test_parser_retains_endpoint_and_ts_reference_validation(edge, message):
    document = {"nodes": [{"id": "R", "role": "reactant"}], "edges": [edge]}

    with pytest.raises(ValueError, match=message):
        integrity.parse_delivered_graph(document)


def test_scoring_returns_none_for_invalid_json(tmp_path):
    path = tmp_path / "mechanism_graph.json"
    path.write_text("{broken")

    assert integrity.load_delivered_graph(path) is None


@pytest.mark.asyncio
async def test_dag_accepts_the_same_delivery_aliases_without_skipping_scientific_gaps(tmp_path):
    c = await controller(tmp_path)
    document = {
        "nodes": [
            {"id": "R", "type": "reactant", "smiles": "O"},
            {"id": "P", "type": "product", "smiles": "O"},
            {"id": "TS", "type": "ts"},
        ],
        "edges": [{"id": "step", "source": "R", "target": "P", "via": "TS"}],
    }
    await asyncio.to_thread((tmp_path / "mechanism_graph.json").write_text, json.dumps(document))

    gate = await c.audit_stop("partial")

    assert gate.action == "wait_review", gate
    assert not gate.report.complete


def test_dag_still_rejects_duplicate_node_ids_after_shared_parsing(tmp_path):
    document = {"nodes": [
        {"id": "R", "role": "reactant"},
        {"id": "R", "role": "reactant"},
    ]}
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(document))

    with pytest.raises(ValueError, match="duplicate"):
        prepare_delivery_artifact(None, None, None, tmp_path)
