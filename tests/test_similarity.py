from __future__ import annotations

import difflib
import random
from itertools import combinations
from pathlib import Path

import pytest

from copy_spotter import similarity
from copy_spotter.extract import extract_words
from copy_spotter.similarity import ENGINES, Engine, Match, compare, coverage, difflib_overlap

SENTENCE1 = "the quick brown fox jumps over the lazy dog near the river bank".split()
SENTENCE2 = "a completely different sentence about cats sleeping all day long in the sun".split()


def test_identical_texts() -> None:
    words = "the quick brown fox".split()
    assert difflib_overlap(words, words) == 100.0


def test_disjoint_texts() -> None:
    assert difflib_overlap(["a", "b"], ["c", "d"]) == 0.0


@pytest.mark.parametrize("engine", ENGINES)
def test_identical_texts_score_100(engine: Engine) -> None:
    comparison = compare(SENTENCE1, SENTENCE1, engine=engine)
    assert comparison.score == 100.0
    assert comparison.blocks == [Match(0, 0, len(SENTENCE1))]


@pytest.mark.parametrize("engine", ENGINES)
def test_disjoint_texts_score_0(engine: Engine) -> None:
    assert compare("one two three four".split(), "five six seven eight".split(), engine=engine) == (0.0, [])


@pytest.mark.parametrize("engine", ENGINES)
def test_empty_texts(engine: Engine) -> None:
    assert compare([], [], engine=engine).score == 0.0
    assert compare(SENTENCE1, [], engine=engine) == (0.0, [])


def test_shingle_is_the_default_engine() -> None:
    reordered = SENTENCE2 + SENTENCE1
    assert compare(SENTENCE1 + SENTENCE2, reordered) == compare(SENTENCE1 + SENTENCE2, reordered, engine="shingle")


def test_reordered_passages_found_by_shingle_not_difflib() -> None:
    words1 = SENTENCE1 + SENTENCE2
    words2 = SENTENCE2 + SENTENCE1
    shingle = compare(words1, words2, min_size=4, engine="shingle")
    assert shingle.score == 100.0
    assert sorted(shingle.blocks) == [
        Match(0, len(SENTENCE2), len(SENTENCE1)),
        Match(len(SENTENCE1), 0, len(SENTENCE2)),
    ]
    # difflib follows a single alignment, so one of the two passages is lost.
    difflib_result = compare(words1, words2, min_size=4, engine="difflib")
    assert len(difflib_result.blocks) == 1
    assert difflib_result.score < 60


@pytest.mark.parametrize("engine", ENGINES)
def test_blocks_respect_min_size(engine: Engine) -> None:
    words1 = "one two three x four five".split()
    words2 = "one two three y four five".split()
    assert compare(words1, words2, min_size=3, engine=engine).blocks == [Match(0, 0, 3)]
    assert compare(words1, words2, min_size=2, engine=engine).blocks == [Match(0, 0, 3), Match(4, 4, 2)]


def test_min_size_below_one_is_clamped() -> None:
    assert compare(["a"], ["a"], min_size=0, engine="difflib").blocks == [Match(0, 0, 1)]


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


def test_coverage_of_reordered_passages_depends_on_engine() -> None:
    # B contains both sentences of A in the opposite order, plus 30 words of its own.
    own = [f"b{k}" for k in range(30)]
    words1 = SENTENCE1 + SENTENCE2
    words2 = SENTENCE2 + own + SENTENCE1
    shingle = compare(words1, words2, min_size=3, engine="shingle")
    assert sorted(m.b for m in shingle.blocks) != [m.b for m in shingle.blocks]  # out of order on the B side
    expected_b = round(len(words1) / len(words2) * 100, 3)
    assert coverage(shingle.blocks, len(words1), len(words2)) == (100.0, expected_b)
    # difflib follows a single alignment and finds only one of the two sentences.
    difflib_blocks = compare(words1, words2, min_size=3, engine="difflib").blocks
    covered_a, covered_b = coverage(difflib_blocks, len(words1), len(words2))
    assert covered_a < 60
    assert covered_b < expected_b


def test_shingle_needs_at_least_two_words() -> None:
    # Single shared words are noise: the shingle engine never reports runs shorter than two words.
    assert compare(["a"], ["a"], min_size=1, engine="shingle") == (0.0, [])
    assert compare("a x b".split(), "b y a".split(), min_size=1, engine="shingle").blocks == []


def test_shingle_score_counts_matched_words() -> None:
    words1 = "a b c d e f g h".split()
    words2 = "x y e f g h".split()
    # 4 matched words on each side out of 14 words in total.
    assert compare(words1, words2, engine="shingle") == (round(8 / 14 * 100, 3), [Match(4, 2, 4)])


def test_repeated_passage_is_matched_once_per_occurrence() -> None:
    passage = "to be or not to be".split()
    words1 = [*passage, "x", *passage]
    words2 = passage
    blocks = compare(words1, words2, engine="shingle").blocks
    # The single copy in words2 can back only one block, the rest of words1 stays unmatched.
    assert blocks[0] == Match(0, 0, 6)
    assert sum(m.size for m in blocks) == 6


def _common_free_run(words1: list[str], words2: list[str], used1: set[int], used2: set[int], n: int) -> bool:
    """Brute force: is there a run of ``n`` identical words using only unmatched positions on both sides?"""
    for i in range(len(words1) - n + 1):
        for j in range(len(words2) - n + 1):
            if all(words1[i + k] == words2[j + k] and i + k not in used1 and j + k not in used2 for k in range(n)):
                return True
    return False


@pytest.mark.parametrize("max_seed", [64, 1])  # 1: frequent n-grams are left to the final linear scan
@pytest.mark.parametrize("seed", range(40))
def test_shingle_blocks_are_correct_disjoint_and_complete(
    seed: int, max_seed: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(similarity, "_MAX_SEED_OCCURRENCES", max_seed)
    rng = random.Random(seed)
    vocabulary = [f"w{k}" for k in range(rng.randint(2, 6))]
    words1 = rng.choices(vocabulary, k=rng.randint(0, 60))
    words2 = rng.choices(vocabulary, k=rng.randint(0, 60))
    min_size = rng.randint(1, 5)
    n = max(min_size, 2)
    comparison = compare(words1, words2, min_size, engine="shingle")

    used1: set[int] = set()
    used2: set[int] = set()
    for a, b, size in comparison.blocks:
        assert size >= n
        assert words1[a : a + size] == words2[b : b + size]
        span1 = set(range(a, a + size))
        span2 = set(range(b, b + size))
        assert not used1 & span1, "blocks overlap in words1"
        assert not used2 & span2, "blocks overlap in words2"
        used1 |= span1
        used2 |= span2
    assert not _common_free_run(words1, words2, used1, used2, n)
    total = len(words1) + len(words2)
    assert comparison.score == (round(2 * len(used1) / total * 100, 3) if total else 0.0)
    assert comparison.blocks == sorted(comparison.blocks)


def test_long_passage_is_one_block() -> None:
    passage = [f"p{k}" for k in range(150)]
    words1 = [f"a{k}" for k in range(40)] + passage + [f"a{k}" for k in range(40, 80)]
    words2 = [f"b{k}" for k in range(70)] + passage + [f"b{k}" for k in range(70, 90)]
    assert compare(words1, words2, min_size=5, engine="shingle").blocks == [Match(40, 70, 150)]


@pytest.mark.parametrize("pattern", [["w"], ["w", "w", "x"], ["w", "w", "w", "x"], ["w"] * 20 + ["x"]])
def test_shingle_handles_repetitive_text_quickly(pattern: list[str]) -> None:
    # Every pair of positions is a match here: this must not take quadratic time or memory.
    words1 = ["w"] * 5000
    words2 = pattern * (5000 // len(pattern))
    blocks = compare(words1, words2, engine="shingle").blocks
    assert sum(m.size for m in blocks) == words2.count("w")  # every run of "w" in words2 is matched


def test_difflib_engine_matches_sequence_matcher(plagiarism_dir: Path) -> None:
    texts = [extract_words(path) for path in sorted(plagiarism_dir.iterdir())]
    for words1, words2 in combinations(texts, 2):
        matcher = difflib.SequenceMatcher(a=words1, b=words2)
        expected = [Match(*m) for m in matcher.get_matching_blocks() if m.size >= 3]
        assert compare(words1, words2, 3, engine="difflib") == (round(matcher.ratio() * 100, 3), expected)
