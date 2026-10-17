"""Bound complexes and separated products carry different minimum evidence."""
import asyncio
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cloudra.benchmark.integrity import audit_integrity
from cloudra.benchmark.schema import GoldMechanismGraph, MechanismNode
from cloudra.benchmark.selfconsistency import audit_self_consistency
from tests.test_dag_file_science import _species_checks

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("smiles,passed", [("O.O=C=O", False), (["O", "O=C=O"], True)])
def test_dag_component_minima_only_verify_separated_species(tmp_path, smiles, passed):
    checks = _species_checks(tmp_path, smiles,
        ["gaussian/water_opt_freq_g16.out", "orca/co2_freq_orca42.out"])
    assert (checks["geometry"]["status"] == "passed") is passed


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("smiles,passed", [(["O.O=C=O"], False), (["O", "O=C=O"], True)])
def test_benchmark_component_minima_preserve_declared_state(tmp_path, smiles, passed):
    for name, fixture, identity in [
        ("water.log", "gaussian/water_opt_freq_g16.out", "O"),
        ("co2.out", "orca/co2_freq_orca42.out", "O=C=O"),
    ]:
        (tmp_path / name).write_text("# smiles: " + identity + "\n" + (FIXTURES / fixture).read_text())
    graph = GoldMechanismGraph(nodes=[MechanismNode(id="P", role="product", smiles=smiles)])
    (tmp_path / "mechanism_graph.json").write_text(graph.model_dump_json())
    integrity = audit_integrity(tmp_path)
    assert integrity.delivered_graph.nodes[0].smiles == smiles
    report = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings,
        integrity.evidence_files, tmp_path)
    assert report.passed is passed


@pytest.mark.usefixtures("rdkit_chemistry")
def test_separated_source_never_uses_one_component_as_barrier_reference(tmp_path):
    from cloudra.benchmark.barrier_evidence import collect_barrier_evidence
    from tests.test_benchmark import _write_delivery

    _write_delivery(tmp_path, declared=None)
    document = json.loads((tmp_path / "mechanism_graph.json").read_text())
    document["nodes"][0]["smiles"] = ["C1CO[PH3]1", "O"]
    document["nodes"][0].pop("properties")
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(document))
    (tmp_path / "water.log").write_text("# smiles: O\n" +
        (FIXTURES / "gaussian/water_opt_freq_g16.out").read_text())

    evidence = collect_barrier_evidence(tmp_path)

    assert evidence.steps == []
    assert any("separated" in note.lower() and "reference" in note.lower() for note in evidence.notes)


def _irc_sandbox(tmp_path, first_frequency, *, synthetic_ts_optimization=False):
    """Native IRC/TS/source fixtures plus synthetic component parser records."""
    from tests.test_irc_separated_products import FIXTURE, PRODUCTS, materials

    _, _, _, components, binding = materials()
    for name in ("ts.out", "reactant.out"):
        shutil.copyfile(FIXTURE / name, tmp_path / name)
    if synthetic_ts_optimization:
        # Engineering-contract fixture only; this does not assert a real optimized TS.
        path = tmp_path / "ts.out"
        path.write_text("# Synthetic optimization marker for the artifact contract test\n"
            "THE OPTIMIZATION HAS CONVERGED\n" + path.read_text())
    irc_dir = tmp_path / "irc"
    irc_dir.mkdir()
    for name in ("irc.out", "irc_IRC_F.xyz", "irc_IRC_B.xyz"):
        shutil.copyfile(FIXTURE / name, irc_dir / name)
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    binding["ts_log_sha256"] = digest(tmp_path / "ts.out")
    manifest = dict(log_sha256=digest(irc_dir / "irc.out"), atom_binding=binding,
        endpoints={side: dict(filename=name, sha256=digest(irc_dir / name),
            origin="final_endpoint_file", converged=False)
            for side, name in [("forward", "irc_IRC_F.xyz"), ("backward", "irc_IRC_B.xyz")]})
    (irc_dir / "irc_endpoints.json").write_text(json.dumps(manifest))
    paths = []
    for index, (identity, (symbols, positions)) in enumerate(zip(PRODUCTS, components, strict=True)):
        path = tmp_path / f"component{index}.out"
        rows = "\n".join(f"{symbol} {x:.10f} {y:.10f} {z:.10f}"
            for symbol, (x, y, z) in zip(symbols, positions, strict=True))
        frequency = first_frequency if index == 0 else 100
        frequencies = "" if frequency is None else "VIBRATIONAL FREQUENCIES\n 0: " + str(frequency) + " cm**-1\n"
        path.write_text(f"# smiles: {identity}\nO   R   C   A\n"
            "CARTESIAN COORDINATES (ANGSTROEM)\n---------------------------------\n" + rows +
            "\n\n" + frequencies + "ORCA TERMINATED NORMALLY\n")
        paths.append(path)
    return [tmp_path / "ts.out", tmp_path / "reactant.out", irc_dir / "irc.out", *paths], binding


def _bound_dag_irc(tmp_path, product_smiles, frequency, *, synthetic_ts_optimization=False, whole_product=False):
    from types import SimpleNamespace

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.models import ElementaryStepEdge, GraphData, GraphRef, SpeciesNode

    paths, binding = _irc_sandbox(tmp_path, frequency, synthetic_ts_optimization=synthetic_ts_optimization)
    if whole_product:
        from tests.test_irc_separated_products import FIXTURE
        product = tmp_path / "product.out"
        shutil.copyfile(FIXTURE / "product.out", product)
        paths.append(product)
    payloads, refs = {}, []
    for index, path in enumerate(paths):
        snapshot = snapshot_evidence_file(path, tmp_path)
        if index == 0:
            snapshot.metadata["atom_binding"] = binding
        ref = GraphRef(ref_type="file", ref_id=str(index))
        refs.append(ref)
        payloads[ref.ref_id] = snapshot.model_dump(mode="json")
    graph = GraphData(graph_id="delivery", graph_kind="delivery", revision=0,
        nodes=[SpeciesNode(node_id="R", name="R", smiles="C1CO[PH3]1", refs=[refs[1]]),
               SpeciesNode(node_id="P", name="P", smiles=product_smiles, refs=refs[3:])],
        edges=[ElementaryStepEdge(edge_id="E", name="E", source_node_id="R", target_node_id="P", refs=[refs[0], refs[2]])])
    store = SimpleNamespace(resolve_evidence=lambda ref: payloads[ref.ref_id])

    return graph, store, paths, binding


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("product_smiles,frequency,passed", [
    (["C=C", "O=[PH3]"], 100, True),
    ("C=C.O=[PH3]", 100, False),
    (["C=C", "O=[PH3]"], -100, False),
    (["C=C", "O=[PH3]"], None, False),
])
def test_dag_and_benchmark_share_separated_irc_acceptance(tmp_path, product_smiles, frequency, passed):
    from cloudra.dag.file_science import file_scientific_checks

    graph, store, _, _ = _bound_dag_irc(tmp_path, product_smiles, frequency)

    checks = file_scientific_checks(store, graph, "E", workspace_root=tmp_path)

    assert (checks["short_irc"]["status"] == "passed") is passed, checks["short_irc"]
    document = dict(nodes=[
        dict(id="R", role="reactant", smiles=["C1CO[PH3]1"], properties={"evidence_log": "reactant.out"}),
        dict(id="TS", role="transition_state", smiles=[], properties={"evidence_log": "ts.out"}),
        dict(id="P", role="product", smiles=product_smiles if isinstance(product_smiles, list) else [product_smiles]),
    ], edges=[dict(id="E", **{"from": "R", "to": "P"}, via="TS")])
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(document))
    integrity = audit_integrity(tmp_path)
    report = audit_self_consistency(integrity.delivered_graph, integrity.node_bindings,
        integrity.evidence_files, tmp_path)

    edge = next(check for check in report.checks if check.element_id == "E")
    assert edge.covered is passed, edge.notes
    assert report.passed is passed
    if passed:
        from cloudra.dag.delivery_artifact import prepare_delivery_artifact
        from cloudra.dag.models import DeliveryReport

        store.list_review_requests = lambda **_: []
        # This captured TS fixture is frequency-only: retain a partial artifact,
        # without inventing optimization or TS-energy evidence.
        document["nodes"][1].pop("properties")
        (tmp_path / "mechanism_graph.json").write_text(json.dumps(document))
        artifact = prepare_delivery_artifact(store, graph, DeliveryReport(complete=False), tmp_path,
            disposition="partial")
        assert artifact.scientific_checks["P"]["geometry"]["status"] == "passed"
        assert artifact.scientific_checks["E"]["short_irc"]["status"] == "passed"



@pytest.mark.usefixtures("rdkit_chemistry")
def test_complete_artifact_and_source_ts_barrier_need_no_product_complex_energy(tmp_path):
    """Synthetic optimization marker tests delivery wiring, not scientific computation."""
    from cloudra.benchmark.barrier_evidence import collect_barrier_evidence
    from cloudra.dag.delivery_artifact import prepare_delivery_artifact
    from cloudra.dag.file_science import file_scientific_checks
    from cloudra.dag.models import DeliveryReport

    graph, store, _, _ = _bound_dag_irc(tmp_path, ["C=C", "O=[PH3]"], 100,
        synthetic_ts_optimization=True)
    checks = file_scientific_checks(store, graph, "E", workspace_root=tmp_path)
    assert all(check["status"] == "passed" for check in checks.values()), checks
    document = dict(nodes=[
        dict(id="R", role="reactant", smiles=["C1CO[PH3]1"],
            properties={"evidence_log": "reactant.out", "energy_hartree": -496.585619145052}),
        dict(id="TS", role="transition_state", smiles=[],
            properties={"evidence_log": "ts.out", "energy_hartree": -496.547724352862}),
        dict(id="P", role="product", smiles=["C=C", "O=[PH3]"]),
    ], edges=[dict(id="E", **{"from": "R", "to": "P"}, via="TS", barrier_kcal_mol=23.77934111687871)])
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(document))
    store.list_review_requests = lambda **_: []

    artifact = prepare_delivery_artifact(store, graph, DeliveryReport(complete=True), tmp_path,
        required=True, disposition="complete")
    barriers = collect_barrier_evidence(tmp_path)

    assert artifact.scientific_checks["P"]["geometry"]["status"] == "passed"
    assert all(check["status"] == "passed" for check in artifact.scientific_checks["E"].values())
    assert len(barriers.steps) == 1, barriers.notes
    assert barriers.steps[0].barrier_kcal_mol == pytest.approx(23.77934111687871)


@pytest.mark.usefixtures("rdkit_chemistry")
@pytest.mark.parametrize("product_smiles,frequency,passed", [
    (["C=C", "O=[PH3]"], 100, True),
    ("C=C.O=[PH3]", 100, False),
    (["C=C", "O=[PH3]"], None, False),
])
def test_stage_binding_uses_all_bound_separated_minima(tmp_path, monkeypatch, product_smiles, frequency, passed):
    from cloudra.dag.evidence_inbox import EvidenceInboxMixin
    from cloudra.dag.models import GraphRef, StageState

    graph, store, paths, binding = _bound_dag_irc(tmp_path, product_smiles, frequency)
    ts_ref = GraphRef(ref_type="tool_result", ref_id="parser-ts")
    irc_ref = GraphRef(ref_type="tool_result", ref_id="parser-irc")
    parser_payloads = {ts_ref.ref_id: {"arguments": {"log_path": str(paths[0])}},
                       irc_ref.ref_id: {"arguments": {"log_path": str(paths[2])}}}
    store.resolve_evidence_with_source = lambda ref: ("log_parser", parser_payloads[ref.ref_id])
    inbox = EvidenceInboxMixin()
    inbox.store = store
    inbox.working_directory = tmp_path
    monkeypatch.setattr("cloudra.services.ts_pipeline_store.atom_binding_for_log", lambda *_: binding)
    stages = [StageState(kind=kind, status="supported", ref=ts_ref) for kind in ("ts_opt", "frequency")]

    accepted, reason = inbox._passes_short_irc_check(irc_ref, graph.edges[0], stages, graph)

    assert accepted is passed, reason


@pytest.mark.asyncio
@pytest.mark.usefixtures("rdkit_chemistry")
async def test_public_stage_bind_persists_separated_product_proof(tmp_path, monkeypatch):
    from cloudra.dag.controller import DagController
    from cloudra.dag.models import AddEdge, AddNode, GraphActor, MutationBatch, StageState
    from cloudra.persistence.database import ConversationDB

    graph, evidence, paths, binding = await asyncio.to_thread(
        _bound_dag_irc, tmp_path, ["C=C", "O=[PH3]"], 100)
    db = await asyncio.to_thread(lambda: ConversationDB("separated-stage-bind", data_dir=tmp_path / "runtime").init())
    controller = DagController(db, "s1", "dag_record", working_directory=tmp_path)
    await controller.initialize()

    def seed_bound_files():
        refs = {ref.ref_id: controller.store.register_evidence("s1", "minimum file",
            evidence.resolve_evidence(ref), source_type="file") for node in graph.nodes for ref in node.refs}
        ts_ref = controller.store.register_evidence("s1", "log_parser", {"arguments": {"log_path": str(paths[0])}})
        irc_ref = controller.store.register_evidence("s1", "log_parser", {"arguments": {"log_path": str(paths[2])}})
        edge = graph.edges[0].model_copy(update={"refs": [], "stages": [
            StageState(kind=kind, status="supported", ref=ts_ref) for kind in ("ts_opt", "frequency")
        ] + [StageState(kind="short_irc")]})
        result = controller.engine.apply_batch(MutationBatch(session_id="s1", actor=GraphActor.HARNESS,
            actor_id="harness", base_revisions=controller.store.load_bundle().revisions,
            rationale="seed native IRC materials", operations=[
                AddNode(op="add_node", graph="delivery", node=node.model_copy(update={
                    "refs": [refs[ref.ref_id] for ref in node.refs]})) for node in graph.nodes
            ] + [AddEdge(op="add_edge", graph="delivery", edge=edge)]))
        assert result.accepted
        return irc_ref

    irc_ref = await asyncio.to_thread(seed_bound_files)
    monkeypatch.setattr("cloudra.services.ts_pipeline_store.atom_binding_for_log", lambda *_: binding)

    result = await controller.apply_stage_bind(element_id="E", stage_kind="short_irc", ref=irc_ref,
        verdict="agree", tool_succeeded=True)

    assert result.accepted, result.rejection_reason
    snapshot = await asyncio.to_thread(controller.store.load_snapshot)
    assert next(stage for stage in snapshot.delivery.edges[0].stages if stage.kind.value == "short_irc").status.value == "supported"


@pytest.mark.usefixtures("rdkit_chemistry")
def test_whole_product_minimum_cannot_hide_an_extra_separated_product(tmp_path):
    from cloudra.dag.file_science import file_scientific_checks

    products = ["C=C.O=[PH3]", "N"]
    graph, store, _, _ = _bound_dag_irc(tmp_path, products, 100, whole_product=True)
    checks = file_scientific_checks(store, graph, "E", workspace_root=tmp_path)
    assert checks["short_irc"]["status"] != "passed", checks
    document = dict(nodes=[
        dict(id="R", role="reactant", smiles=["C1CO[PH3]1"], properties={"evidence_log": "reactant.out"}),
        dict(id="TS", role="transition_state", smiles=[], properties={"evidence_log": "ts.out"}),
        dict(id="P", role="product", smiles=products),
    ], edges=[dict(id="E", **{"from": "R", "to": "P"}, via="TS")])
    (tmp_path / "mechanism_graph.json").write_text(json.dumps(document))
    integrity = audit_integrity(tmp_path)
    # Exercise the strict proof directly too: graph binding can independently
    # reject N before reaching the scientific check.
    from cloudra.benchmark.selfconsistency import _LogProbe, _strict_irc_proof
    files = {evidence.path: evidence for evidence in integrity.evidence_files}
    proof = _strict_irc_proof(_LogProbe(tmp_path, files), sorted(files), ["reactant.out"],
        ["product.out"], ts_files=["ts.out"], product_smiles=products)
    assert proof is None
