"""Offline scoring retains each step's native endpoint lineage independently of energy anchors."""

import hashlib
import json
from pathlib import Path

import pytest

from cloudra.benchmark.integrity import EvidenceFile, NodeBinding
from cloudra.benchmark.schema import GoldMechanismGraph
from cloudra.benchmark.selfconsistency import audit_self_consistency
from tests.test_irc_endpoint_optimization import write_lineage_bundle


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _record(root, path):
    return {"path": str(Path(path).relative_to(root)), "sha256": _sha256(path)}


def _write_manifest(root, graph_sha256, steps):
    path = root / ".cloudra" / "mechanism_evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"graph_sha256": graph_sha256, "steps": steps}))
    return path


def _scoring_bundle(tmp_path, *, second_edge=False):
    bundle = write_lineage_bundle(tmp_path)
    # A separately optimized energy reference remains the same chemical species,
    # but is not the exact final geometry of the actual IRC endpoint Opt.
    anchor = tmp_path / "product_energy_anchor.out"
    anchor.write_text(bundle["product_freq"].read_text().replace("2.17000000", "2.18000000"))
    document = {
        "nodes": [
            {"id": "R", "role": "reactant", "smiles": [bundle["reactant_smiles"]]},
            {"id": "P", "role": "product", "smiles": [bundle["product_smiles"]],
             "properties": {"evidence_log": anchor.name}},
            {"id": "TS", "role": "transition_state", "smiles": []},
        ],
        "edges": [{"id": "E", "from": "R", "to": "P", "via": "TS"}],
    }
    if second_edge:
        document["edges"].append({"id": "other", "from": "R", "to": "P", "via": "TS"})
    graph_path = tmp_path / "mechanism_graph.json"
    graph_path.write_text(json.dumps(document))
    graph = GoldMechanismGraph.model_validate(document)
    bindings = [
        NodeBinding(node_id=node, bound_files=[path.name], matched=True, quality=1.0)
        for node, path in [("R", bundle["reactant_freq"]), ("P", anchor), ("TS", bundle["ts"])]
    ]
    files = [EvidenceFile(path=path.name, kind="orca", size=path.stat().st_size)
             for path in tmp_path.glob("*.out")]
    endpoints = {
        "source": [_record(tmp_path, bundle[key]) for key in ("reactant_opt", "reactant_freq")],
        "target": [_record(tmp_path, bundle[key]) for key in ("product_opt", "product_freq")],
    }
    return bundle, graph_path, graph, bindings, files, endpoints


def test_benchmark_uses_step_endpoints_without_replacing_species_energy_anchor(tmp_path, rdkit_chemistry):
    _, graph_path, graph, bindings, files, endpoints = _scoring_bundle(tmp_path)
    _write_manifest(tmp_path, _sha256(graph_path), {"E": endpoints})

    report = audit_self_consistency(graph, bindings, files, tmp_path)

    assert report.passed, report.notes
    edge = next(check for check in report.checks if check.element_id == "E")
    assert {"product_opt.out", "product_freq.out"} <= set(edge.evidence_used)
    assert bindings[1].bound_files == ["product_energy_anchor.out"]


def test_one_steps_endpoint_evidence_cannot_supply_another_steps_missing_proof(tmp_path, rdkit_chemistry):
    _, graph_path, graph, bindings, files, endpoints = _scoring_bundle(tmp_path, second_edge=True)
    _write_manifest(tmp_path, _sha256(graph_path), {
        "E": endpoints,
        "other": {"source": endpoints["source"], "target": [
            _record(tmp_path, tmp_path / "product_energy_anchor.out"),
        ]},
    })

    report = audit_self_consistency(graph, bindings, files, tmp_path)

    edges = {check.element_id: check for check in report.checks if check.kind == "edge"}
    assert edges["E"].covered, edges["E"].notes
    assert not edges["other"].covered
    assert not report.passed


@pytest.mark.parametrize("fault", ["stale_graph", "changed_log", "missing_log", "outside", "schema"])
def test_unusable_endpoint_sidecar_never_falls_back_to_other_history(tmp_path, fault, rdkit_chemistry):
    bundle, graph_path, graph, bindings, files, endpoints = _scoring_bundle(tmp_path)
    # Without the manifest this ordinary same-geometry binding can pass; an
    # unusable manifest must therefore not disappear into that fallback.
    bindings[1].bound_files = [bundle["product_freq"].name]
    digest = _sha256(graph_path)
    if fault == "stale_graph":
        digest = "0" * 64
    elif fault == "changed_log":
        endpoints["target"][0]["sha256"] = "0" * 64
    elif fault == "missing_log":
        endpoints["target"][0]["path"] = "missing.out"
    elif fault == "outside":
        endpoints["target"][0]["path"] = "../foreign.out"
    else:
        endpoints["target"] = "product_opt.out"
    _write_manifest(tmp_path, digest, {"E": endpoints})

    report = audit_self_consistency(graph, bindings, files, tmp_path)

    assert not report.passed
    assert any("endpoint evidence" in note.lower() and "unusable" in note.lower() for note in report.notes)


def test_absent_endpoint_sidecar_leaves_existing_native_scoring_available(tmp_path):
    from cloudra.benchmark.delivery_evidence import read_step_endpoint_evidence

    assert read_step_endpoint_evidence(tmp_path, "a" * 64) == {}


def test_endpoint_sidecar_roundtrip_is_portable_with_unchanged_native_logs(tmp_path):
    import shutil

    from cloudra.benchmark.delivery_evidence import read_step_endpoint_evidence, write_step_endpoint_evidence
    from cloudra.persistence.paths import mechanism_evidence_path

    source = tmp_path / "source"
    source.mkdir()
    log = source / "endpoint.out"
    log.write_text("native endpoint bytes")
    steps = {"step": {"source": [_record(source, log)], "target": []}}
    write_step_endpoint_evidence(source, "a" * 64, steps)
    assert mechanism_evidence_path(source).is_file()
    restored = tmp_path / "restored"
    shutil.copytree(source, restored)

    assert read_step_endpoint_evidence(restored, "a" * 64) == {
        "step": {"source": ["endpoint.out"], "target": []},
    }


@pytest.mark.parametrize("fault", ["absolute_path", "symlink_outside", "wrong_hash", "unknown_field", "wrong_type"])
def test_writer_rejects_invalid_endpoint_snapshot_records(tmp_path, fault):
    from cloudra.benchmark.delivery_evidence import write_step_endpoint_evidence

    root = tmp_path / "workspace"
    root.mkdir()
    log = root / "endpoint.out"
    log.write_text("native endpoint bytes")
    record = _record(root, log)
    if fault == "absolute_path":
        record["path"] = str(log)
    elif fault == "symlink_outside":
        external = tmp_path / "foreign.out"
        external.write_text(log.read_text())
        log.unlink()
        log.symlink_to(external)
    elif fault == "wrong_hash":
        record["sha256"] = "0" * 64
    elif fault == "unknown_field":
        record["trusted"] = True
    else:
        record["path"] = 7

    with pytest.raises(ValueError, match="endpoint evidence.*unusable"):
        write_step_endpoint_evidence(root, "a" * 64, {"step": {"source": [record], "target": []}})
