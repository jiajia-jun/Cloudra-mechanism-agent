"""Behavioral contracts for event-driven transcript frame scheduling."""

from __future__ import annotations

import pytest

from cloudra.tui.new.frame_scheduler import FrameScheduler


class FakeTimer:
    def __init__(self, owner, delay, callback) -> None:
        self.owner, self.delay, self.callback, self.stopped = owner, delay, callback, False

    def stop(self) -> None:
        self.stopped = True


class FakeTimerOwner:
    def __init__(self) -> None:
        self.timers, self.next_callbacks = [], []

    @property
    def pending_timer_count(self) -> int:
        return sum(not timer.stopped for timer in self.timers)

    def set_timer(self, delay, callback):
        timer = FakeTimer(self, delay, callback)
        self.timers.append(timer)
        return timer

    def call_next(self, callback, *args) -> None:
        self.next_callbacks.append(lambda: callback(*args))

    def run_next_callbacks(self) -> None:
        for callback in self.next_callbacks[:]:
            callback()
        self.next_callbacks.clear()


def test_repeated_requests_keep_one_pending_frame():
    """A burst must coalesce to one presentation frame instead of growing work."""
    owner = FakeTimerOwner()
    calls = []
    scheduler = FrameScheduler(owner, lambda: calls.append("frame"), max_fps=20)

    scheduler.request()
    scheduler.request()
    scheduler.request()

    assert owner.pending_timer_count == 1 and scheduler.pending

    owner.timers[0].callback()

    assert calls == ["frame"] and not scheduler.pending


def test_manual_flush_invalidates_an_already_queued_timer_callback():
    """An overdue timer cannot render a second frame after an explicit flush."""
    owner = FakeTimerOwner()
    calls = []
    scheduler = FrameScheduler(owner, lambda: calls.append("frame"), max_fps=20)

    scheduler.request()
    timer = owner.timers[0]
    scheduler.flush()
    timer.callback()

    assert calls == ["frame"] and not scheduler.pending
    assert owner.pending_timer_count == 0


def test_timer_uses_only_the_remaining_20_fps_interval():
    """A frame requested during cooldown waits only for the remaining interval."""
    now = [10.0]
    owner = FakeTimerOwner()
    calls = []
    scheduler = FrameScheduler(owner, lambda: calls.append("frame"), clock=lambda: now[0])

    scheduler.flush()
    now[0] = 10.02
    scheduler.request()

    timer = owner.timers[-1]
    assert timer.delay == pytest.approx(0.03)
    now[0] = 10.05
    timer.callback()
    assert calls == ["frame", "frame"] and not scheduler.pending


def test_immediate_storm_keeps_one_cancellable_callback_and_honours_20_fps_cap():
    """Immediate requests neither pile up callbacks nor bypass the 20 FPS cooldown."""
    now = [10.0]
    owner = FakeTimerOwner()
    calls = []
    scheduler = FrameScheduler(owner, lambda: calls.append("frame"), max_fps=100, clock=lambda: now[0])

    scheduler.flush()
    scheduler.request(immediate=True)
    scheduler.request(immediate=True)
    scheduler.request(immediate=True)

    assert owner.pending_timer_count == 1 and len(owner.timers) == 1
    assert len(owner.next_callbacks) == 0
    timer = owner.timers[-1]
    assert timer.delay == pytest.approx(0.05)

    scheduler.cancel()
    assert owner.pending_timer_count == 0 and not scheduler.pending
    timer.callback()
    assert calls == ["frame"]
