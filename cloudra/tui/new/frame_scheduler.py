"""Event-driven, one-shot scheduling for coalesced presentation frames."""

from __future__ import annotations

import time
from typing import Callable, Protocol


class _Timer(Protocol):
    def stop(self) -> None: ...


class _TimerOwner(Protocol):
    def set_timer(self, delay: float, callback: Callable[[], None]) -> _Timer: ...


class FrameScheduler:
    """Run at most one queued frame, bounded by ``max_fps`` without polling."""

    def __init__(
        self,
        owner: _TimerOwner,
        callback: Callable[[], None],
        max_fps: int = 20,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_fps < 1:
            raise ValueError("max_fps must be positive")
        self._owner, self._callback = owner, callback
        self._clock = clock
        self._interval, self._last_flush = 1.0 / min(max_fps, 20), 0.0
        self._timer: _Timer | None = None
        self._generation = 0

    @property
    def pending(self) -> bool:
        return self._timer is not None

    def request(self, *, immediate: bool = False) -> None:
        del immediate  # Every request obeys the same hard presentation interval.
        if self._timer is None:
            delay = max(0.0, self._interval - (self._clock() - self._last_flush))
            generation = self._generation
            self._timer = self._owner.set_timer(
                delay, lambda: self._flush_if_current(generation)
            )

    def _flush_if_current(self, generation: int) -> None:
        if generation == self._generation:
            self.flush()

    def flush(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.stop()
        self._timer = None
        self._last_flush = self._clock()
        self._callback()

    def cancel(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.stop()
        self._timer = None
