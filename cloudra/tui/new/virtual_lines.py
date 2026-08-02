"""Variable-height row indexing for the virtual transcript."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class ScrollAnchor:
    """The record and in-record row kept at the top of a viewport."""

    record_id: int
    row_offset: int


class HeightIndex:
    """Map transcript records with positive heights to virtual row numbers."""

    def __init__(self, heights: Iterable[int] = ()) -> None:
        self._heights: list[int] = []
        self._tree: list[int] = [0]
        self.rebuild(heights)

    @property
    def total(self) -> int:
        return self._prefix(len(self._heights))

    def height(self, index: int) -> int:
        return self._heights[index]

    def replace(self, index: int, height: int) -> None:
        if height < 1:
            raise ValueError("record height must be positive")
        delta = height - self._heights[index]
        self._heights[index] = height
        self._add(index + 1, delta)

    def append(self, height: int) -> None:
        if height < 1:
            raise ValueError("record height must be positive")
        position = len(self._heights) + 1
        span_start = position - (position & -position)
        inherited_height = self._prefix(position - 1) - self._prefix(span_start)
        self._heights.append(height)
        self._tree.append(inherited_height + height)

    def rebuild(self, heights: Iterable[int]) -> None:
        rebuilt_heights = list(heights)
        if any(height < 1 for height in rebuilt_heights):
            raise ValueError("record height must be positive")
        self._heights = rebuilt_heights
        self._tree = [0, *rebuilt_heights]
        for position in range(1, len(self._tree)):
            parent = position + (position & -position)
            if parent < len(self._tree):
                self._tree[parent] += self._tree[position]

    def row_start(self, index: int) -> int:
        if index < 0 or index >= len(self._heights):
            raise IndexError(index)
        return self._prefix(index)

    def locate(self, row: int) -> tuple[int, int]:
        if row < 0 or row >= self.total:
            raise IndexError(row)
        record_index = self._lower_bound(row + 1)
        return record_index, row - self.row_start(record_index)

    def _add(self, position: int, delta: int) -> None:
        while position < len(self._tree):
            self._tree[position] += delta
            position += position & -position

    def _prefix(self, position: int) -> int:
        total = 0
        while position:
            total += self._tree[position]
            position -= position & -position
        return total

    def _lower_bound(self, target: int) -> int:
        position = 0
        bit = 1 << (len(self._heights).bit_length() - 1)
        while bit:
            candidate = position + bit
            if candidate < len(self._tree) and self._tree[candidate] < target:
                position = candidate
                target -= self._tree[candidate]
            bit >>= 1
        return position


def restore_anchor(anchor: ScrollAnchor, ids: Sequence[int], index: HeightIndex) -> int:
    """Return the row where ``anchor`` belongs after a height/filter update."""

    try:
        record_index = ids.index(anchor.record_id)
    except ValueError:
        return 0
    row_offset = min(max(anchor.row_offset, 0), index.height(record_index) - 1)
    return index.row_start(record_index) + row_offset
