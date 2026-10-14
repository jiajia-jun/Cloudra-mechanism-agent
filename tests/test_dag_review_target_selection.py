"""Directed reviews use the requested target, not the last global queue item."""

from __future__ import annotations

import asyncio
import shutil

import pytest

from cloudra.dag.models import AddEdge, ElementaryStepEdge
from cloudra.dag.review_context import ReviewContextManager
from cloudra.tools.Plantool.dag_tools.dag_review_species import DagReviewSpecies
from cloudra.tools.Plantool.dag_tools.dag_review_step import DagReviewStep
from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
from tests.dag_identity import call_dag_tool, make_coordinator, make_supervisor
from tests.test_dag_async_evidence_review import FIXTURES_DIR, _seed_review_graph
from tests.test_dag_file_review_contract import _mutate


@pytest.fixture(autouse=True)
def _reject_sync_sqlite_on_loop(monkeypatch):
    monkeypatch.setenv("CLOUDRA_DB_SYNC_ON_LOOP", "raise")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["species", "step"])
async def test_directed_file_reviews_can_review_first_target_before_last(tmp_path, kind):
    session, db, store = await asyncio.to_thread(_seed_review_graph, tmp_path, f"review-target-{kind}")
    if kind == "species":
        submit, review = DagSubmitSpeciesEvidence, DagReviewSpecies
        name_key, file_key = "species_name", "opt_file"
        names = ["R", "P"]
        files = ["gaussian/water_opt_freq_g16.out", "benchmark_nu3/product_minimum.out"]
    else:
        await asyncio.to_thread(_mutate, store, AddEdge(op="add_edge", graph="delivery",
            edge=ElementaryStepEdge(edge_id="step2", name="step2", source_node_id="r", target_node_id="p")))
        submit, review = DagSubmitStepEvidence, DagReviewStep
        name_key, file_key = "step_name", "ts_file"
        names = ["step1", "step2"]
        files = ["xtb/ts_hess_xtb.out", "benchmark_synthetic/ts_freq.out"]
    requests = []
    agent = make_coordinator(db.conversation_id, orchestration_mode="dag_guided", workspace_dir=str(tmp_path))
    for name, file in zip(names, files):
        native = tmp_path / (FIXTURES_DIR / file).name
        await asyncio.to_thread(shutil.copyfile, FIXTURES_DIR / file, native)
        submitted = await call_dag_tool(submit, agent, session,
            **{name_key: name, file_key: str(native)})
        assert submitted.is_success, submitted
        requests.append(await asyncio.to_thread(store.get_review_request, submitted.result["review_id"]))
    # Selection must survive a process restart and not rely on the cached last item.
    ReviewContextManager._active_reviews.pop(db.conversation_id, None)
    supervisor = make_supervisor(db.conversation_id, workspace_dir=str(tmp_path))
    first = await call_dag_tool(review, supervisor, session, **{name_key: names[0]},
        verdict="rejected", rationale="Review the first target's submitted calculation")
    assert first.is_success, first
    decision = await asyncio.to_thread(store.get_review_decision_for_request, requests[0].request_id)
    assert decision.evidence_refs == requests[0].supporting_refs
    assert (await asyncio.to_thread(store.get_review_request, requests[0].request_id)).state == "resolved"
    assert (await asyncio.to_thread(store.get_review_request, requests[1].request_id)).state == "queued"
    assert await asyncio.to_thread(store.get_review_decision_for_request, requests[1].request_id) is None
    second = await call_dag_tool(review, supervisor, session, **{name_key: names[1]},
        verdict="rejected", rationale="Review the second target's separate calculation")
    assert second.is_success, second
    decision = await asyncio.to_thread(store.get_review_decision_for_request, requests[1].request_id)
    assert decision.evidence_refs == requests[1].supporting_refs


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["outside_workspace", "missing_file"])
async def test_step_minimum_file_cannot_escape_the_evidence_workspace(tmp_path, fault):
    session, db, store = await asyncio.to_thread(_seed_review_graph, tmp_path, f"endpoint-file-{fault}")
    workspace = tmp_path / "workspace"
    await asyncio.to_thread(workspace.mkdir)
    native = (tmp_path if fault == "outside_workspace" else workspace) / "minimum.out"
    if fault == "outside_workspace":
        await asyncio.to_thread(shutil.copyfile, FIXTURES_DIR / "gaussian/water_opt_freq_g16.out", native)
    ts_file = workspace / "ts_hess_xtb.out"
    await asyncio.to_thread(shutil.copyfile, FIXTURES_DIR / "xtb/ts_hess_xtb.out", ts_file)
    agent = make_coordinator(db.conversation_id, orchestration_mode="dag_guided", workspace_dir=str(workspace))
    submitted = await call_dag_tool(DagSubmitStepEvidence, agent, session,
        step_name="step1", ts_file=str(ts_file), target_minimum_file=str(native))
    assert not submitted.is_success
    assert "target_minimum_file" in submitted.error
    assert (await asyncio.to_thread(store.load_snapshot)).delivery.edges[0].refs == []
    assert await asyncio.to_thread(store.list_review_requests, state="queued") == []


def test_step_submission_schema_exposes_minimum_paths_without_internal_reference_fields():
    schema = DagSubmitStepEvidence.model_fields['input_schema'].default.to_parameters_schema()
    properties = schema['properties']
    assert 'source_minimum_file' in properties and 'target_minimum_file' in properties
    assert 'endpoint_a_ref' not in properties and 'endpoint_b_ref' not in properties
    assert 'content_hash' not in str(schema) and 'revision' not in str(schema)
