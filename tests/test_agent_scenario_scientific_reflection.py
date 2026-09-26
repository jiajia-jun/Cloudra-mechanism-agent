"""Scientific failure reflection through the real Agent tool and context pipeline."""

from __future__ import annotations

import pytest

from tests.agent_scenarios import ScenarioHarness, ScriptedProvider, Step


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
        "watch_pairs": [[1, 2]],
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
