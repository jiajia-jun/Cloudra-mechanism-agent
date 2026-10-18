"""PROCESS notes stay ordinary files while their maintenance runs asynchronously."""

from __future__ import annotations

import asyncio

import pytest

from cloudra.base.tools_class import Tool
from cloudra.dag.store import DagStore
from cloudra.persistence.database import ConversationDB
from cloudra.runtime_v2.schemas import Command
from cloudra.runtime_v2.supervision import find_project_supervisor
from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step


@pytest.fixture
def approve_file_changes(monkeypatch):
    """Replace only the external user decision; file preparation and application are real."""
    async def approve(self, session, details, tool_args=None):
        return True, ""

    monkeypatch.setattr(Tool, "ensure_safety", approve)


async def _assert_no_scientific_reviews(harness):
    def reviews():
        store = DagStore(ConversationDB(harness.project.id).init())
        return store.list_review_requests(), store.list_call_reviews(state=None)

    assert await asyncio.to_thread(reviews) == ([], [])


def _completed_calls(harness, agent):
    return [row for row in harness.tool_events(agent) if row["status"] in {"completed", "failed"}]


@pytest.mark.asyncio
@pytest.mark.parametrize('note_path', ['PROCESS.md', 'STEP1_IRC_NOTES.md'])
async def test_process_notes_maintained_without_blocking_research(tmp_path, approve_file_changes, note_path):
    """Missing notify, blocking Supervisor work, or a write capability leak breaks this scenario."""
    review = asyncio.Event()
    research_wait = asyncio.Event()
    original = "# Research process\n\nHypothesis: concerted reaction.\nTest: follow the imaginary mode.\n"
    revised = "# Research process\n\nHypothesis: concerted reaction.\nTest: follow the imaginary mode.\nObservation: the tested guess moved along a different coordinate; keep the hypothesis open.\n"
    if note_path != 'PROCESS.md':
        await asyncio.to_thread((tmp_path / 'PROCESS.md').write_text, original)
    source_reads = [('read', {'path': note_path})]
    if note_path != 'PROCESS.md':
        source_reads.append(('read', {'path': 'PROCESS.md'}))
    provider = ScriptedProvider(by_role={
        'coordinator': [Step(stop=True)],
        "small_mol": [
            Step(tools=[("write", {"path": note_path, "content": original})]),
            Step(tools=[("write", {"path": "next_calculation.txt", "content": "research continues\n"})]),
            Step(wait_for=research_wait),
        ],
        "supervisor": [
            Step(wait_for=review, tools=source_reads),
            Step(tools=[("edit", {
                "path": "PROCESS.md",
                "edits": [{"old_text": "Test: follow the imaginary mode.\n",
                           "new_text": "Test: follow the imaginary mode.\nObservation: the tested guess moved along a different coordinate; keep the hypothesis open.\n"}],
            })]),
            Step(tools=[("write", {"path": "scientific_result.txt", "content": "must not overwrite scientific files"})]),
            Step(stop=True),
        ],
    })
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        updated = await harness.bus.execute(Command(
            type="role.update", target={"role_id": "supervisor"},
            payload={"default_settings": {
                "orchestration_mode": "dag_guided", "invocation_protocol": "traditional",
            }},
        ))
        assert updated.accepted
        coordinator = await harness.spawn('coordinator', protocol='traditional', orchestration_mode='standard')
        await harness.wait_terminal(coordinator)
        researcher = await harness.spawn(
            "small_mol", protocol="traditional", orchestration_mode="dag_guided",
        )
        await harness.wait_for(
            lambda: len(_completed_calls(harness, researcher)) == 2,
            "both research file mutations complete while Supervisor reasoning is held",
        )
        await harness.wait_for(
            lambda: provider.call_count("supervisor") > 0,
            "PROCESS change asynchronously starts Supervisor reasoning", timeout=2,
        )
        supervisor = find_project_supervisor(harness.core, harness.project.id)
        assert supervisor is not None
        assert not review.is_set()
        assert await asyncio.to_thread((tmp_path / "PROCESS.md").read_text) == original
        assert await asyncio.to_thread((tmp_path / "next_calculation.txt").read_text) == "research continues\n"
        calls = _completed_calls(harness, researcher)
        assert [row["tool_name"] for row in calls] == ["write", "write"]
        assert all(row["started"] and row["is_success"] and not row["blocked"] for row in calls)
        await _assert_no_scientific_reviews(harness)

        review.set()
        await harness.wait_terminal(supervisor)
        calls = _completed_calls(harness, supervisor)
        assert [row["tool_name"] for row in calls] == ['read'] * len(source_reads) + ["edit", "write"]
        assert all(row['is_success'] for row in calls[:-1]), harness.describe(supervisor)
        assert calls[-2]["started"] and calls[-2]["result_data"]["status"] == "applied"
        assert not calls[-1]["is_success"]
        assert await asyncio.to_thread((tmp_path / "PROCESS.md").read_text) == revised
        assert not await asyncio.to_thread((tmp_path / "scientific_result.txt").exists)
        await _assert_no_scientific_reviews(harness)
        await harness.settle()
        assert harness.types(supervisor).count("run.started") == 1
        assert len(harness.messages(supervisor)) == 1
        assert len([agent for agent in harness.core.agents.values() if agent.role_id == "supervisor"]) == 1
        assert coordinator.state.value == 'succeeded'
        assert harness.types(coordinator).count('run.started') == 1
    finally:
        review.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_failed_process_change_and_other_files_do_not_notify(tmp_path, approve_file_changes):
    """Only an applied project-root PROCESS change can trigger document maintenance."""
    await asyncio.to_thread((tmp_path / "PROCESS.md").write_text, "existing notes\n")
    hold = asyncio.Event()
    provider = ScriptedProvider(by_role={"small_mol": [
        Step(tools=[("write", {"path": "PROCESS.md", "content": "conflicting rewrite"})]),
        Step(tools=[("write", {"path": "scratch/PROCESS.md", "content": "private scratch notes"})]),
        Step(tools=[("write", {"path": "result.txt", "content": "ordinary result"})]),
        Step(wait_for=hold),
    ]})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        researcher = await harness.spawn(
            "small_mol", protocol="traditional", orchestration_mode="dag_guided",
        )
        await harness.wait_for(lambda: len(_completed_calls(harness, researcher)) == 3, "three file call results")
        calls = _completed_calls(harness, researcher)
        assert calls[0]["result_data"]["status"] == "conflict"
        assert not calls[0]["is_success"]
        assert calls[1]["is_success"] and calls[2]["is_success"]
        assert await asyncio.to_thread((tmp_path / "PROCESS.md").read_text) == "existing notes\n"
        await harness.settle()
        assert find_project_supervisor(harness.core, harness.project.id) is None
        await _assert_no_scientific_reviews(harness)
    finally:
        await harness.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["standard", "dag_record"])
async def test_process_notes_in_other_modes_do_not_create_supervisor(tmp_path, approve_file_changes, mode):
    """An ordinary notes file does not turn an unsupervised project into guided research."""
    hold = asyncio.Event()
    provider = ScriptedProvider(by_role={"small_mol": [
        Step(tools=[("write", {"path": "PROCESS.md", "content": "a provisional hypothesis\n"})]),
        Step(wait_for=hold),
    ]})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        researcher = await harness.spawn("small_mol", protocol="traditional", orchestration_mode=mode)
        await harness.wait_for(lambda: len(_completed_calls(harness, researcher)) == 1, "notes file written")
        assert _completed_calls(harness, researcher)[0]["is_success"], harness.describe(researcher)
        assert await asyncio.to_thread((tmp_path / "PROCESS.md").read_text) == "a provisional hypothesis\n"
        await harness.settle()
        assert find_project_supervisor(harness.core, harness.project.id) is None
        await _assert_no_scientific_reviews(harness)
    finally:
        await harness.aclose()
