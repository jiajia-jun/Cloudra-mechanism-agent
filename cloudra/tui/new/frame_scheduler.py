"""Event-driven, one-shot scheduling for coalesced presentation frames."""

from __future__ import annotations

import time
from typing import Callable, Protocol


class _Timer(Protocol):
    def stop(self) -> None: ...


class _TimerOwner(Protocol):
    def set_timer(self, delay: float, callback: Callable[[], None]) -> _Timer: ...

    def call_next(self, callback: Callable[..., None], *args: object) -> None: ...


class FrameScheduler:
    """Run at most one queued frame, bounded by ``max_fps`` without polling."""

    def __init__(self, owner: _TimerOwner, callback: Callable[[], None], max_fps: int = 20) -> None:
        if max_fps < 1:
            raise ValueError("max_fps must be positive")
        self._owner, self._callback = owner, callback
        self._interval, self._last_flush = 1.0 / max_fps, 0.0
        self._timer: _Timer | None = None
        self._immediate_pending = False
        self._generation = 0

    @property
    def pending(self) -> bool:
        return self._timer is not None or self._immediate_pending

    def request(self, *, immediate: bool = False) -> None:
        if immediate:
            self.cancel()
            if not self._immediate_pending:
                self._immediate_pending = True
                generation = self._generation
                self._owner.call_next(self._flush_if_current, generation)
            return
        if self._timer is None and not self._immediate_pending:
            delay = max(0.0, self._interval - (time.monotonic() - self._last_flush))
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
        self._immediate_pending = False
        self._last_flush = time.monotonic()
        self._callback()

    def cancel(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.stop()
        self._timer, self._immediate_pending = None, False
