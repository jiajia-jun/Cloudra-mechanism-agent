"""Default mechanism delivery must retain the IRC direction-proof debt."""

import asyncio
from pathlib import Path

import pytest

from cloudra.base.session_class import Session
from cloudra.dag.controller import DagController
from cloudra.dag.store import DagStore
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_add_species import DagAddSpecies
from cloudra.tools.Plantool.dag_tools.dag_add_step import DagAddStep
from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism
from cloudra.tools.Plantool.dag_tools.dag_review_step import DagReviewStep
from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
from tests.dag_identity import call_dag_tool, make_coordinator, make_supervisor


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["proposal", "add_step"])
async def test_default_step_keeps_short_irc_required(tmp_path, entry):
    get_config().data_dir = tmp_path
    conversation_id = f"default-irc-{entry}"
    agent = make_coordinator(conversation_id, orchestration_mode="dag_record")
    session = Session("s1", str(tmp_path / "session.json"))
    if entry == "proposal":
        result = await call_dag_tool(
            DagProposeMechanism, agent, session,
            rationale="single-step mechanism",
            species=[{"name": "R", "smiles": "C=C"}, {"name": "P", "smiles": "CC"}],
            steps=[{"name": "step1", "from": "R", "to": "P"}],
            delivery_targets=["step1"],
        )
    else:
        for name, smiles in [("R", "C=C"), ("P", "CC")]:
            added = await call_dag_tool(DagAddSpecies, agent, session, name=name, smiles=smiles)
            assert added.is_success
        result = await call_dag_tool(
            DagAddStep, agent, session, name="step1", from_="R", to="P",
        )
    assert result.is_success
    db = await asyncio.to_thread(ConversationDB(conversation_id).init)
    snapshot = await asyncio.to_thread(DagStore(db).load_snapshot)
    stages = {s.kind.value: s for s in snapshot.delivery.edges[0].stages}
    assert stages["short_irc"].required
    assert stages["short_irc"].status.value == "pending"
    assert not stages["ts_guess"].required


@pytest.mark.asyncio
async def test_default_guided_ts_review_cannot_clear_missing_irc(tmp_path):
    get_config().data_dir = tmp_path
    conversation_id = "default-irc-guided-review"
    workspace = Path(__file__).resolve().parents[1]
    agent = make_coordinator(
        conversation_id, orchestration_mode="dag_guided", workspace_dir=str(workspace),
    )
    session = Session("s1", str(tmp_path / "session.json"))
    proposed = await call_dag_tool(
        DagProposeMechanism, agent, session,
        rationale="single-step mechanism",
        species=[{"name": "R", "smiles": "C=C"}, {"name": "P", "smiles": "CC"}],
        steps=[{"name": "step1", "from": "R", "to": "P"}],
        delivery_targets=["step1"],
    )
    assert proposed.is_success
    db = await asyncio.to_thread(ConversationDB(conversation_id).init)
    controller = DagController(db, "s1", "dag_guided", conversation_id=conversation_id)
    accepted = await controller.accept_mechanism(
        draft_id=proposed.result["draft_id"], verdict="accept", rationale="accept working hypothesis",
    )
    assert accepted["accepted"]
    submitted = await call_dag_tool(
        DagSubmitStepEvidence, agent, session, step_name="step1",
        ts_file=str(workspace / "tests/fixtures/xtb/ts_hess_xtb.out"),
        reaction_coordinate_description="candidate transition mode",
    )
    assert submitted.is_success
    supervisor = make_supervisor(conversation_id, workspace_dir=str(workspace))
    reviewed = await call_dag_tool(
        DagReviewStep, supervisor, session, step_name="step1", verdict="supported",
        rationale="submitted saddle frequency evidence is sufficient for its stages",
    )
    assert reviewed.is_success
    report = await asyncio.to_thread(controller.delivery_report)
    snapshot = await asyncio.to_thread(controller.store.load_snapshot)
    edge_id = snapshot.delivery.edges[0].edge_id
    gaps = [g for g in report.unresolved if g.target_id == edge_id and g.code == "missing_stage_evidence"]
    assert not report.complete
    assert len(gaps) == 1
    assert "short_irc" in gaps[0].detail
