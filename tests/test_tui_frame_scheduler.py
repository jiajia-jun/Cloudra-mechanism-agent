"""Behavioral contracts for event-driven transcript frame scheduling."""

from __future__ import annotations

from cloudra.tui.new.frame_scheduler import FrameScheduler


class FakeTimer:
    def __init__(self, owner, callback) -> None:
        self.owner, self.callback, self.stopped = owner, callback, False

    def stop(self) -> None:
        self.stopped = True


class FakeTimerOwner:
    def __init__(self) -> None:
        self.timers, self.next_callbacks = [], []

    @property
    def pending_timer_count(self) -> int:
        return sum(not timer.stopped for timer in self.timers)

    def set_timer(self, delay, callback):
        timer = FakeTimer(self, callback)
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

    scheduler.request(immediate=True)
    owner.run_next_callbacks()

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
