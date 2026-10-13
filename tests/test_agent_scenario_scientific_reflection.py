"""Scientific failure reflection through the real Agent tool and context pipeline."""

from __future__ import annotations

import asyncio

import pytest

from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step


@pytest.mark.asyncio
async def test_repeated_process_inspection_delivers_one_evidence_hint_to_next_turn(tmp_path):
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.ts_pipeline_store import create_process, save_process_record
    from cloudra.tools.core.ts_process import _terminal
    from tests.test_ts_stage_inputs import record_fixture

    release = asyncio.Event()
    args = {}
    provider = ScriptedProvider(by_role={"small_mol": [
        Step(tools=[("ts_inspect", args)], wait_for=release),
        Step(tools=[("ts_inspect", args)]),
        Step(text="Recorded the unresolved evidence", stop=True),
    ]})
    harness = await ScenarioHarness.start(tmp_path, workspace_dir=tmp_path, provider=provider)
    try:
        agent = await harness.spawn("small_mol", protocol="traditional")

        def recorded_candidate():
            db = ComputeDB().init()
            record = record_fixture(tmp_path, owner_conversation_id=harness.project.id,
                                    owner_session_id=agent.id)
            record.evidence_candidates = [str(tmp_path / "observed_irc.out")]
            process = create_process(db, request_key="hint-observed-endpoint", payload={
                "project_id": harness.project.id, "owner_id": agent.id,
                "workspace_dir": str(tmp_path), "input": record.input.model_dump(mode="json"),
            })
            record.pipeline_id = process["process_id"]
            _terminal(record, "verdict", "candidate_only", "Recorded endpoint connection differs")
            save_process_record(db, process_id=process["process_id"], record=record.model_dump(mode="json"))
            return record.run_id

        args["run_id"] = await asyncio.to_thread(recorded_candidate)
        release.set()
        await harness.wait_terminal(agent)
        calls = [row for row in harness.tool_events(agent) if row["tool_name"] == "ts_inspect"]
        assert len(calls) == 2, harness.describe(agent)
        assert all(row["is_success"] for row in calls), calls
        assert all(row["result_data"]["result"]["verified"] is False for row in calls)
        pins = [event for event in harness.events(agent) if event.type == "context.pin_set"
                and event.data["key"].startswith("guidance-scientific-reflection:")]
        assert len(pins) == 1
        content = pins[0].data["content"]
        assert str(tmp_path / "observed_irc.out") in content
        assert any(message.get("role") == "system" and content in message.get("content", "")
                   for _, messages in provider.calls[1:] for message in messages)
    finally:
        release.set()
        await harness.aclose()


@pytest.mark.asyncio
async def test_repeated_monotonic_scan_pins_one_reflection_for_next_turn(tmp_path):
    """Levers: real scan parser, after-tool guidance, pin deduplication, context delivery."""
    pytest.importorskip("ase")

    (tmp_path / "scan.relaxscanact.dat").write_text(
        "0.70 -1.0\n1.00 -0.9\n1.40 -0.8\n", encoding="utf-8",
    )
    for index, distance in enumerate((0.70, 1.00, 1.40), start=1):
        (tmp_path / f"scan.{index:03d}.xyz").write_text(
            f"2\nscan point {index}\nH 0 0 0\nH 0 0 {distance}\n",
            encoding="utf-8",
        )

    scan_call = {
        "mode": "scan_parse",
        "engine": "orca",
        "log_path": str(tmp_path / "scan.out"),
        "watch_pairs": [[0, 1]],
    }
    provider = ScriptedProvider(by_role={
        "dft": [
            Step(tools=[("ts_guess", scan_call)]),
            Step(tools=[("ts_guess", scan_call)]),
            Step(text="Recorded the unresolved scan", stop=True),
        ],
    })
    harness = await ScenarioHarness.start(
        tmp_path, workspace_dir=tmp_path, provider=provider,
    )
    try:
        agent = await harness.spawn("dft", protocol="traditional")
        await harness.wait_terminal(agent)

        calls = [row for row in harness.tool_events(agent) if row["tool_name"] == "ts_guess"]
        assert len(calls) == 2, harness.describe(agent)
        assert len({row["tool_call_id"] for row in calls}) == 2
        assert all(row["started"] and not row["blocked"] and row["is_success"] for row in calls)
        assert all(row["result_data"]["scan_has_internal_peak"] is False for row in calls)
        assert all(row["result_data"]["candidate_unavailable"] is False for row in calls)

        events = harness.events(agent)
        pins = [event for event in events if event.type == "context.pin_set"
                and str(event.data.get("key", "")).startswith("guidance-scientific-reflection:")]
        assert len(pins) == 1
        pin = pins[0]
        pin_index = events.index(pin)
        assert any(
            event.type == "context.appended"
            and event.data.get("notices_through", 0) >= pin.session_seq
            and any(message.get("role") == "system"
                    and message.get("content") == pin.data["content"]
                    for message in event.data.get("messages", []))
            and any(later.type == "llm.request_started" for later in events[index + 1:])
            for index, event in enumerate(events[pin_index + 1:], start=pin_index + 1)
        )
    finally:
        await harness.aclose()
