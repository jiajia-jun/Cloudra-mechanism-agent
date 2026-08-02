import random

import pytest

from cloudra.tui.new.virtual_lines import HeightIndex, ScrollAnchor, restore_anchor


def test_height_index_maps_rows_and_updates_prefixes():
    index = HeightIndex([2, 3, 1])

    assert index.total == 6
    assert [index.locate(row) for row in range(6)] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
        (1, 2),
        (2, 0),
    ]

    index.replace(1, 5)

    assert index.row_start(2) == 7
    assert index.total == 8


def test_anchor_restores_same_record_offset():
    index = HeightIndex([3, 4, 2])
    anchor = ScrollAnchor(record_id=20, row_offset=2)

    index.replace(0, 7)

    assert restore_anchor(anchor, [10, 20, 30], index) == 9


def test_append_and_rebuild_replace_the_indexed_records():
    index = HeightIndex([2])

    index.append(4)
    assert index.total == 6
    assert index.row_start(1) == 2

    index.rebuild([5, 1, 3])
    assert index.total == 9
    assert [index.locate(row) for row in range(index.total)] == [
        (0, 0),
        (0, 1),
        (0, 2),
        (0, 3),
        (0, 4),
        (1, 0),
        (2, 0),
        (2, 1),
        (2, 2),
    ]


def test_height_index_rejects_invalid_heights_and_row_boundaries():
    with pytest.raises(ValueError, match="record height must be positive"):
        HeightIndex([1, 0])

    index = HeightIndex([])
    assert index.total == 0
    with pytest.raises(IndexError):
        index.locate(0)
    with pytest.raises(IndexError):
        index.row_start(0)
    with pytest.raises(IndexError):
        index.height(0)

    index.append(2)
    with pytest.raises(ValueError, match="record height must be positive"):
        index.append(0)
    with pytest.raises(ValueError, match="record height must be positive"):
        index.replace(0, 0)
    with pytest.raises(ValueError, match="record height must be positive"):
        index.rebuild([1, -1])
    with pytest.raises(IndexError):
        index.locate(-1)
    with pytest.raises(IndexError):
        index.locate(2)


def test_restore_anchor_clamps_offset_and_falls_back_when_record_is_removed():
    index = HeightIndex([2, 4])

    assert restore_anchor(ScrollAnchor(record_id=20, row_offset=99), [10, 20], index) == 5
    assert restore_anchor(ScrollAnchor(record_id=10, row_offset=-3), [10, 20], index) == 0
    assert restore_anchor(ScrollAnchor(record_id=99, row_offset=1), [10, 20], index) == 0


def test_fenwick_index_matches_plain_prefix_sum_oracle_after_seeded_updates():
    randomizer = random.Random(20260802)
    expected = [randomizer.randint(1, 9) for _ in range(17)]
    index = HeightIndex(expected)

    for _ in range(500):
        operation = randomizer.randrange(3)
        if operation == 0:
            height = randomizer.randint(1, 12)
            expected.append(height)
            index.append(height)
        elif operation == 1:
            position = randomizer.randrange(len(expected))
            height = randomizer.randint(1, 12)
            expected[position] = height
            index.replace(position, height)
        else:
            expected = [randomizer.randint(1, 12) for _ in range(randomizer.randrange(1, 40))]
            index.rebuild(expected)

        assert index.total == sum(expected)
        starts = [sum(expected[:position]) for position in range(len(expected))]
        assert [index.height(position) for position in range(len(expected))] == expected
        assert [index.row_start(position) for position in range(len(expected))] == starts
        assert [index.locate(row) for row in range(index.total)] == [
            (position, offset)
            for position, height in enumerate(expected)
            for offset in range(height)
        ]


def test_fenwick_updates_and_lookups_touch_logarithmic_tree_entries():
    class CountingTree(list[int]):
        accesses = 0

        def __getitem__(self, index):
            self.accesses += 1
            return super().__getitem__(index)

        def __setitem__(self, index, value):
            self.accesses += 1
            super().__setitem__(index, value)

    index = HeightIndex([1] * 65_536)
    tree = CountingTree(index._tree)
    index._tree = tree

    index.replace(32_768, 2)
    assert tree.accesses < 100

    tree.accesses = 0
    assert index.locate(32_768) == (32_768, 0)
    assert tree.accesses < 100
