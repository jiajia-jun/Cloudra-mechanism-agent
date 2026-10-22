"""Prompt projections reuse science; reviews and delivery retain full verification."""

import asyncio
from pathlib import Path

import pytest

from cloudra.dag import file_science
from cloudra.dag.controller import DagController
from cloudra.tools.Plantool.dag_tools.dag_review_species import DagReviewSpecies
from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
from tests.dag_identity import call_dag_tool, make_coordinator, make_supervisor
from tests.test_dag_async_evidence_review import FIXTURES_DIR, _seed_review_graph


async def accepted_minimum(tmp_path):
    session, db, store = await asyncio.to_thread(_seed_review_graph, tmp_path, "cached-science")
    import shutil

    from cloudra.dag.models import UpdateNode
    from tests.test_dag_file_review_contract import _mutate

    await asyncio.to_thread(_mutate, store, UpdateNode(op="update_node", graph="delivery", node_id="r",
        changes={"smiles": "O", "stages": [{"kind": "geometry"}]}))
    native = tmp_path / "minimum.out"
    shutil.copyfile(FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out", native)
    out = await call_dag_tool(DagSubmitSpeciesEvidence,
        make_coordinator(db.conversation_id, workspace_dir=str(tmp_path)), session,
        species_name="R", opt_file=str(native))
    assert out.is_success
    reviewed = await call_dag_tool(DagReviewSpecies,
        make_supervisor(db.conversation_id, workspace_dir=str(tmp_path)), session,
        species_name="R", verdict="supported", rationale="accept actual minimum")
    assert reviewed.is_success
    request = await asyncio.to_thread(store.get_review_request, out.result["review_id"])
    snapshot = await asyncio.to_thread(store.resolve_evidence, request.supporting_refs[0])
    return DagController(db, "s1", "dag_guided", working_directory=tmp_path), Path(snapshot["snapshot_path"])


@pytest.mark.asyncio
async def test_prompt_reuses_unchanged_science_but_delivery_reads_and_checks_again(tmp_path, monkeypatch):
    controller, path = await accepted_minimum(tmp_path)
    original = file_science._extract_qm_log
    parsed = []

    def parse(path):
        parsed.append(str(path))
        return original(path)

    monkeypatch.setattr(file_science, "_extract_qm_log", parse)
    await controller.prompt_projection()
    count = len(parsed)
    assert count > 0
    original_bytes, original_text = Path.read_bytes, Path.read_text

    def read_bytes(candidate):
        assert candidate != path, "unchanged prompt must reuse the accepted evidence result"
        return original_bytes(candidate)

    def read_text(candidate, *args, **kwargs):
        assert candidate != path, "unchanged prompt must not parse the same log again"
        return original_text(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text)
    await controller.prompt_projection()
    assert len(parsed) == count
    monkeypatch.setattr(Path, "read_bytes", original_bytes)
    monkeypatch.setattr(Path, "read_text", original_text)
    await asyncio.to_thread(controller.delivery_report)
    assert len(parsed) > count


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["rewrite", "delete"])
async def test_prompt_cache_expires_when_archived_evidence_changes_or_disappears(tmp_path, damage):
    import os

    controller, path = await accepted_minimum(tmp_path)
    await controller.prompt_projection()
    if damage == "delete":
        path.unlink()
    else:
        stat = path.stat()
        original = path.read_bytes()
        path.write_bytes(b"X" + original[1:])
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    await controller.prompt_projection()
    report = await asyncio.to_thread(controller.delivery_report)
    assert any(g.code == "scientific_check_incomplete" and g.target_id == "r" for g in report.unresolved)


def test_one_scientific_check_parses_each_log_once(tmp_path, monkeypatch):
    import shutil

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.models import ElementaryStepEdge, GraphData, OccurrenceNode

    source = tmp_path / "saddle.out"
    shutil.copyfile(FIXTURES_DIR / "xtb" / "ts_hess_xtb.out", source)
    snapshot = snapshot_evidence_file(source, tmp_path)
    from cloudra.dag.models import GraphRef
    ref = GraphRef(ref_type="file", ref_id="minimum", content_hash="sha256:" + snapshot.sha256)
    graph = GraphData(graph_id="delivery", graph_kind="delivery", revision=0,
        nodes=[OccurrenceNode(node_id="r", label="R"), OccurrenceNode(node_id="p", label="P")],
        edges=[ElementaryStepEdge(edge_id="step", name="step", source_node_id="r", target_node_id="p", refs=[ref])])
    from types import SimpleNamespace
    store = SimpleNamespace(resolve_evidence=lambda _: snapshot.model_dump(mode="json"))
    original = file_science._extract_qm_log
    calls = []

    def parse(path):
        calls.append(str(path))
        return original(path)

    monkeypatch.setattr(file_science, "_extract_qm_log", parse)
    checks = file_science.file_scientific_checks(store, graph, "step", workspace_root=tmp_path)
    assert checks["frequency"]["status"] == "passed"
    assert len(calls) == len(set(calls))


def _bound_irc_graph(tmp_path):
    from types import SimpleNamespace

    from cloudra.dag.evidence_ingest import snapshot_evidence_file
    from cloudra.dag.models import ElementaryStepEdge, GraphData, GraphRef, OccurrenceNode
    from tests.test_irc_endpoint_optimization import write_lineage_bundle

    bundle = write_lineage_bundle(tmp_path / 'native')
    minima = {}
    for role in ('reactant', 'product'):
        path = tmp_path / 'native' / (role + '_combined.out')
        frequency = Path(bundle[role + '_freq']).read_text()
        path.write_text(Path(bundle[role + '_opt']).read_text()
            + 'VIBRATIONAL FREQUENCIES' + frequency.partition('VIBRATIONAL FREQUENCIES')[2])
        minima[role] = path
    snapshots = {}
    payloads = {}
    refs = {}
    for name, source in {
        "opt": bundle['ts'], "freq": bundle['ts'],
        "irc": bundle['irc'], "source": minima['reactant'], "target": minima['product'],
    }.items():
        snapshots[name] = snapshot_evidence_file(source, tmp_path)
        payloads[name] = snapshots[name].model_dump(mode="json")
        refs[name] = GraphRef(ref_type="file", ref_id=name, content_hash="sha256:" + snapshots[name].sha256)
    graph = GraphData(graph_id="delivery", graph_kind="delivery", revision=0,
        nodes=[OccurrenceNode(node_id="r", label="R", smiles=bundle['reactant_smiles'], refs=[refs["source"]]),
               OccurrenceNode(node_id="p", label="P", smiles=bundle['product_smiles'], refs=[refs["target"]])],
        edges=[ElementaryStepEdge(edge_id="step", name="step", source_node_id="r", target_node_id="p",
                                  refs=[refs["opt"], refs["freq"], refs["irc"]])])
    store = SimpleNamespace(resolve_evidence=lambda ref: payloads[ref.ref_id])
    return store, graph, snapshots


@pytest.fixture
def verified_irc_graph(tmp_path, rdkit_chemistry):
    return _bound_irc_graph(tmp_path)


@pytest.mark.parametrize("dependency", ["frequency", "irc_sidecar", "irc_manifest", "source", "target"])
@pytest.mark.parametrize("damage", ["rewrite", "delete"])
def test_prompt_cache_tracks_irc_bundle_and_both_endpoint_minima(tmp_path, verified_irc_graph, dependency, damage):
    import os

    store, graph, snapshots = verified_irc_graph
    def check():
        return file_science.file_scientific_checks(store, graph, "step", workspace_root=tmp_path, use_cache=True)
    first = check()
    assert first["frequency"]["status"] == "passed"
    assert first["ts_opt"]["status"] == "passed"
    assert first["short_irc"]["status"] == "passed"
    assert check() == first
    if dependency == "irc_sidecar":
        path = Path(snapshots["irc"].metadata["irc_sidecars"][0]["snapshot_path"])
    elif dependency == "irc_manifest":
        path = Path(snapshots["irc"].metadata["irc_manifest"]["snapshot_path"])
    else:
        path = Path(snapshots[{"frequency": "freq"}.get(dependency, dependency)].snapshot_path)
    if damage == "delete":
        path.unlink()
    else:
        stat = path.stat()
        before = path.read_bytes()
        path.write_bytes(b"X" + before[1:])
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    current = check()
    assert current != first
    if dependency == "frequency":
        assert current["frequency"]["status"] != "passed"
    else:
        assert current["short_irc"]["status"] != "passed"


def test_science_cache_is_bounded_and_returned_results_do_not_share_mutable_state(tmp_path, monkeypatch):
    store, graph, _ = _bound_irc_graph(tmp_path)
    def check():
        return file_science.file_scientific_checks(store, graph, "step", workspace_root=tmp_path, use_cache=True)
    first = check()
    first["frequency"]["status"] = "failed"
    assert check()["frequency"]["status"] == "passed"
    monkeypatch.setattr(file_science, "_SCIENCE_CACHE_BYTES", 1)
    with file_science._SCIENCE_CACHE_LOCK:
        file_science._SCIENCE_CACHE.clear()
    check()
    assert not file_science._SCIENCE_CACHE


@pytest.mark.parametrize('damage', ['delete', 'rewrite', 'symlink'])
def test_cached_irc_recovery_paths_expire_without_revoking_native_science(tmp_path, verified_irc_graph, damage):
    store, graph, snapshots = verified_irc_graph
    path = Path(snapshots['irc'].metadata['irc_end_a_path'])
    incomplete = graph.model_copy(update={'nodes': [
        graph.nodes[0].model_copy(update={'refs': []}), graph.nodes[1],
    ]})

    def check(current):
        return file_science.file_scientific_checks(store, current, 'step',
            workspace_root=tmp_path, use_cache=True)

    first = check(incomplete)
    assert first['short_irc']['status'] == 'incomplete'
    assert str(path) in first['short_irc']['next_action']
    assert check(graph)['short_irc']['status'] == 'passed'
    if damage == 'delete':
        path.unlink()
    elif damage == 'rewrite':
        path.write_text('edited XYZ\n')
    else:
        original = path.with_suffix('.original')
        path.rename(original)
        path.symlink_to(original)

    current = check(incomplete)
    assert current['short_irc']['status'] == 'incomplete'
    assert str(path) not in current['short_irc']['next_action']
    assert current['frequency'] == first['frequency']
    assert current['ts_opt'] == first['ts_opt']
    assert check(graph)['short_irc']['status'] == 'passed'


@pytest.mark.parametrize("endpoint", ["source", "target"])
def test_prompt_cache_tracks_explicit_endpoint_refs_when_nodes_have_no_files(tmp_path, verified_irc_graph, endpoint):
    store, graph, snapshots = verified_irc_graph
    source, target = graph.nodes
    source_ref, target_ref = source.refs[0], target.refs[0]
    graph = graph.model_copy(update={
        "nodes": [node.model_copy(update={"refs": []}) for node in graph.nodes],
        "edges": [graph.edges[0].model_copy(update={"refs": [*graph.edges[0].refs, source_ref, target_ref]})],
    })
    options = dict(workspace_root=tmp_path, use_cache=True,
                   endpoint_refs={"endpoint_a": target_ref.model_dump(mode="json"),
                                  "endpoint_b": source_ref.model_dump(mode="json")})
    first = file_science.file_scientific_checks(store, graph, "step", **options)
    assert first["short_irc"]["status"] == "passed"
    Path(snapshots[endpoint].snapshot_path).unlink()
    current = file_science.file_scientific_checks(store, graph, "step", **options)
    assert current["short_irc"]["status"] != "passed"
