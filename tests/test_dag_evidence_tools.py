"""Integration tests for dag_submit_step_evidence, dag_submit_species_evidence,
dag_review_step, and dag_review_species tools.
"""

from pathlib import Path

import pytest

from cloudra.base.session_class import Session
from cloudra.core.agent import Coordinator
from cloudra.infra.config import get_config
from cloudra.persistence.database import ConversationDB
from cloudra.tools.Plantool.dag_tools.dag_accept_mechanism import DagAcceptMechanism
from cloudra.tools.Plantool.dag_tools.dag_propose_mechanism import DagProposeMechanism
from cloudra.tools.Plantool.dag_tools.dag_review_species import DagReviewSpecies
from cloudra.tools.Plantool.dag_tools.dag_review_step import DagReviewStep
from cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence import DagSubmitSpeciesEvidence
from cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence import DagSubmitStepEvidence
from tests.dag_identity import call_dag_tool, make_supervisor

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _setup(tmp_path, conversation_id, mode):
    get_config().data_dir = tmp_path
    agent = Coordinator(
        query="study mechanism",
        conversation_id=conversation_id,
        orchestration_mode=mode,
    )
    # Set working directory to tmp_path
    agent.working_directory = str(tmp_path)
    session = Session("s1", str(tmp_path / "session.json"))
    session.working_dir = str(tmp_path)
    db = ConversationDB(conversation_id, data_dir=tmp_path).init()
    return agent, session, db


@pytest.mark.asyncio
async def test_submit_evidence_in_dag_record(tmp_path):
    agent, session, db = _setup(tmp_path, "rec-ev", "dag_record")

    # 1. Propose mechanism
    prop_out = await call_dag_tool(
        DagProposeMechanism,
        agent,
        session,
        species=[{"name": "R", "smiles": "CC"}, {"name": "P", "smiles": "CC"}],
        steps=[{"name": "step1", "source": "R", "target": "P"}],
        rationale="Initial hypothesis",
    )
    assert prop_out.is_success

    # Copy fixture files into tmp_path workspace
    water_log = tmp_path / "water.out"
    water_log.write_text((FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out").read_text())
    ts_log = tmp_path / "ts.out"
    ts_log.write_text((FIXTURES_DIR / "xtb" / "ts_hess_xtb.out").read_text())

    # 2. Submit species evidence for R -> auto-accepted
    sp_out = await call_dag_tool(
        DagSubmitSpeciesEvidence,
        agent,
        session,
        species_name="R",
        opt_file=str(water_log),
        description="Optimized reactant minimum",
    )
    assert sp_out.is_success
    assert sp_out.result["status"] == "supported"

    from cloudra.dag.store import DagStore

    snapshot = DagStore(db).load_snapshot()
    r_node = [n for n in snapshot.delivery.nodes if getattr(n, "name", "") == "R"][0]
    assert r_node.status == "supported"

    # 3. Submit step evidence for step1 -> auto-accepted
    step_out = await call_dag_tool(
        DagSubmitStepEvidence,
        agent,
        session,
        step_name="step1",
        ts_file=str(ts_log),
        reaction_coordinate_description="C-C cleavage transition state",
    )
    assert step_out.is_success
    assert step_out.result["status"] == "supported"

    snapshot = DagStore(db).load_snapshot()
    step_edge = [e for e in snapshot.delivery.edges if getattr(e, "name", "") == "step1"][0]
    assert step_edge.status == "supported"


@pytest.mark.asyncio
async def test_submit_invalid_ts_rejected(tmp_path):
    agent, session, db = _setup(tmp_path, "rec-inv", "dag_record")

    await call_dag_tool(
        DagProposeMechanism,
        agent,
        session,
        species=[{"name": "R"}, {"name": "P"}],
        steps=[{"name": "step1", "source": "R", "target": "P"}],
        rationale="Hypothesis",
    )

    # Use water (0 imaginary frequencies) as TS evidence -> must fail
    water_log = tmp_path / "water.out"
    water_log.write_text((FIXTURES_DIR / "gaussian" / "water_opt_freq_g16.out").read_text())

    step_out = await call_dag_tool(
        DagSubmitStepEvidence,
        agent,
        session,
        step_name="step1",
        ts_file=str(water_log),
        reaction_coordinate_description="False TS",
    )
    assert not step_out.is_success
    assert "TS validation failed" in step_out.error


@pytest.mark.asyncio
async def test_guided_review_flow(tmp_path):
    agent, session, db = _setup(tmp_path, "guided-ev", "dag_guided")
    supervisor = make_supervisor(agent.conversation_id, workspace_dir=str(tmp_path))

    # 1. Propose mechanism & accept
    prop_out = await call_dag_tool(
        DagProposeMechanism,
        agent,
        session,
        species=[{"name": "R"}, {"name": "P"}],
        steps=[{"name": "step1", "source": "R", "target": "P"}],
        rationale="Hypothesis",
    )
    assert prop_out.is_success

    accept_out = await call_dag_tool(
        DagAcceptMechanism,
        supervisor,
        session,
        verdict="accept",
        rationale="Good mechanism",
    )
    assert accept_out.is_success

    ts_log = tmp_path / "ts.out"
    ts_log.write_text((FIXTURES_DIR / "xtb" / "ts_hess_xtb.out").read_text())

    # 2. Coordinator submits step evidence -> queued for review
    sub_out = await call_dag_tool(
        DagSubmitStepEvidence,
        agent,
        session,
        step_name="step1",
        ts_file=str(ts_log),
        reaction_coordinate_description="Valid TS",
    )
    assert sub_out.is_success
    assert sub_out.result["status"] == "submitted_for_review"

    from cloudra.dag.store import DagStore

    snapshot = DagStore(db).load_snapshot()
    step_edge = [e for e in snapshot.delivery.edges if getattr(e, "name", "") == "step1"][0]
    assert step_edge.status == "pending"

    # 3. Supervisor reviews step -> supported
    rev_out = await call_dag_tool(
        DagReviewStep,
        supervisor,
        session,
        step_name="step1",
        verdict="supported",
        rationale="Verified imaginary mode at -521 cm^-1 matches reaction.",
    )
    assert rev_out.is_success
    assert rev_out.result["verdict"] == "supported"

    snapshot = DagStore(db).load_snapshot()
    step_edge = [e for e in snapshot.delivery.edges if getattr(e, "name", "") == "step1"][0]
    assert step_edge.status == "supported"

    # 4. Supervisor reviews species -> rejected
    rev_sp = await call_dag_tool(
        DagReviewSpecies,
        supervisor,
        session,
        species_name="R",
        verdict="rejected",
        rationale="Conformation is wrong chair isomer",
    )
    assert rev_sp.is_success
    assert rev_sp.result["verdict"] == "rejected"

    snapshot = DagStore(db).load_snapshot()
    r_node = [n for n in snapshot.delivery.nodes if getattr(n, "name", "") == "R"][0]
    assert r_node.status == "rejected"
