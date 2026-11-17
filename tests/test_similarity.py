from __future__ import annotations

from copy_spotter.similarity import Match, compare, difflib_overlap


def test_identical_texts() -> None:
    words = "the quick brown fox".split()
    assert difflib_overlap(words, words) == 100.0


def test_disjoint_texts() -> None:
    assert difflib_overlap(["a", "b"], ["c", "d"]) == 0.0


def test_empty_texts() -> None:
    assert compare([], []).score == 0.0


def test_blocks_respect_min_size() -> None:
    words1 = "one two three x four five".split()
    words2 = "one two three y four five".split()
    assert compare(words1, words2, min_size=3).blocks == [Match(0, 0, 3)]
    assert compare(words1, words2, min_size=2).blocks == [Match(0, 0, 3), Match(4, 4, 2)]


def test_min_size_below_one_is_clamped() -> None:
    assert compare(["a"], ["a"], min_size=0).blocks == [Match(0, 0, 1)]
