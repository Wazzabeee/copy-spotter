from __future__ import annotations

from copy_spotter.similarity import Match, compare, coverage, difflib_overlap


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


def test_coverage_of_a_short_text_copied_into_a_long_one() -> None:
    short = [f"s{k}" for k in range(30)]
    long = [f"l{k}" for k in range(150)] + short + [f"l{k}" for k in range(150, 270)]
    comparison = compare(short, long)
    assert comparison.score < 20  # the symmetric ratio is diluted by the length difference
    assert coverage(comparison.blocks, len(short), len(long)) == (100.0, 10.0)
    assert coverage(comparison.blocks, len(short), len(long)) == coverage(compare(long, short).blocks, 300, 30)[::-1]


def test_coverage_of_empty_documents() -> None:
    assert coverage([], 0, 0) == (0.0, 0.0)
    assert coverage([], 0, 10) == (0.0, 0.0)
    assert coverage(compare([], ["a", "b"]).blocks, 0, 2) == (0.0, 0.0)


def test_coverage_counts_only_blocks_of_at_least_block_size() -> None:
    words1 = "one two three x four five".split()
    words2 = "one two three y four five".split()
    assert coverage(compare(words1, words2, min_size=2).blocks, 6, 6) == (83.333, 83.333)
    assert coverage(compare(words1, words2, min_size=3).blocks, 6, 6) == (50.0, 50.0)
    assert coverage(compare(words1, words2, min_size=4).blocks, 6, 6) == (0.0, 0.0)


def test_coverage_counts_overlapping_blocks_once() -> None:
    # The same 3 words of A matched twice in B (as a shingle engine may report).
    blocks = [Match(0, 0, 3), Match(0, 5, 3), Match(1, 9, 2)]
    assert coverage(blocks, 6, 12) == (50.0, 66.667)
