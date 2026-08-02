"""Deterministically profile the pre-virtualization Textual ``ChatLog``."""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import json
import pstats
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from textual.app import App, ComposeResult
from textual.widgets import Input

from cloudra.tui.new.widgets.chat_log import ChatLog


_STYLES = Path(__file__).parents[1] / "cloudra" / "tui" / "new" / "styles.tcss"


@dataclass(frozen=True)
class ProfileResult:
    elapsed_seconds: float
    python_calls: int
    max_commit_seconds: float
    input_p95_seconds: float
    child_count: int
    record_count: int


class _ProfileApp(App[None]):
    CSS_PATH = _STYLES

    def __init__(self) -> None:
        super().__init__()
        self._input_processed = asyncio.Event()

    def compose(self) -> ComposeResult:
        yield ChatLog(id="chat-log")
        yield Input(id="profile-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Mark completion of the same submitted-input path users exercise."""
        self._input_processed.set()


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, (len(ordered) * 95 + 99) // 100 - 1))
    return ordered[index]


async def _input_submission_latency(pilot, app: _ProfileApp, input_widget: Input, round_index: int) -> float:
    """Measure submission-to-handler latency through Textual's real Input event path."""
    app._input_processed.clear()
    input_widget.value = f"profile input {round_index}"
    input_widget.focus()
    started = perf_counter()
    await pilot.press("enter")
    await app._input_processed.wait()
    return perf_counter() - started


async def run_profile(
    history_count: int = 1_000,
    stream_count: int = 16,
    rounds: int = 30,
) -> ProfileResult:
    """Run one fixed-size ChatLog workload under ``Textual.run_test``."""
    if history_count < 0 or stream_count < 1 or rounds < 1:
        raise ValueError("history_count must be >= 0; stream_count and rounds must be >= 1")

    app = _ProfileApp()
    profiler = cProfile.Profile()
    latencies: list[float] = []
    max_commit_seconds = 0.0

    async with app.run_test(size=(100, 36)) as pilot:
        chat_log = app.query_one("#chat-log", ChatLog)
        input_widget = app.query_one("#profile-input", Input)
        profiler.enable()
        started = perf_counter()

        for index in range(history_count):
            chat_log.append_system(f"history-{index % 8}", f"历史记录 {index}")
        await pilot.pause()

        for round_index in range(rounds):
            commit_started = perf_counter()
            for stream_index in range(stream_count):
                chat_log.append_stream_chunk(
                    f"stream-{stream_index}",
                    f"round {round_index} from stream {stream_index}\n",
                    f"agent-{stream_index}",
                )
            chat_log._flush_streams()
            latencies.append(await _input_submission_latency(pilot, app, input_widget, round_index))
            await pilot.pause()
            max_commit_seconds = max(max_commit_seconds, perf_counter() - commit_started)

        for stream_index in range(stream_count):
            chat_log.end_stream(f"stream-{stream_index}")
        await pilot.pause()

        elapsed_seconds = perf_counter() - started
        profiler.disable()
        child_count = len(chat_log.children)
        record_count = sum(len(records) for records in chat_log._messages.values())

    python_calls = pstats.Stats(profiler).total_calls
    return ProfileResult(
        elapsed_seconds=elapsed_seconds,
        python_calls=python_calls,
        max_commit_seconds=max_commit_seconds,
        input_p95_seconds=_p95(latencies),
        child_count=child_count,
        record_count=record_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=int, default=1_000)
    parser.add_argument("--streams", type=int, default=16)
    parser.add_argument("--rounds", type=int, default=30)
    args = parser.parse_args()
    result = asyncio.run(run_profile(args.history, args.streams, args.rounds))
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()
