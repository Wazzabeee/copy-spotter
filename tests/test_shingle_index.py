"""``ShingleIndex`` must return exactly what the original per-pair shingle engine returned."""

from __future__ import annotations

import gc
import pickle
import random
from itertools import combinations

import pytest

from copy_spotter import similarity
from copy_spotter.similarity import ENGINES, Engine, ShingleIndex, compare, compare_all

from . import _reference_shingle as reference

BLOCK_SIZES = (1, 2, 3, 5)


def _random_corpus(rng: random.Random) -> list[list[str]]:
    """A few documents over a small or large vocabulary, some with passages copied from earlier ones."""
    vocabulary = [f"w{k}" for k in range(rng.choice([1, 2, 3, 5, 20, 200]))]
    texts: list[list[str]] = []
    for _ in range(rng.randint(2, 5)):
        words = rng.choices(vocabulary, k=rng.choice([0, 1, 2, 3, 10, 100, 300]))
        if texts and len(words) > 20 and rng.random() < 0.5:
            source = rng.choice(texts)
            if len(source) > 10:
                a = rng.randrange(len(source) - 5)
                size = rng.randint(3, min(60, len(source) - a))
                b = rng.randrange(len(words) - 5)
                words[b : b + size] = source[a : a + size]
        texts.append(words)
    return texts


def _assert_same_as_reference(texts: list[list[str]], min_size: int) -> None:
    index = ShingleIndex(texts, min_size)
    for i, j in combinations(range(len(texts)), 2):
        assert index.compare(i, j) == reference.compare_shingle(texts[i], texts[j], min_size), (i, j)
        assert index.compare(j, i) == reference.compare_shingle(texts[j], texts[i], min_size), (j, i)


@pytest.mark.parametrize("seed", range(300))
def test_index_matches_reference_on_random_corpora(seed: int) -> None:
    rng = random.Random(seed)
    texts = _random_corpus(rng)
    for min_size in BLOCK_SIZES:
        _assert_same_as_reference(texts, min_size)


def _repetitive_corpus() -> list[list[str]]:
    return [
        ["w"] * 300,
        ["w", "w", "x"] * 100,
        ["a", "b"] * 150,
        ["a", "b", "c"] * 40 + ["w"] * 80 + ["a", "b"] * 30,
        [],
        ["w"],
        ["w", "w"],
    ]


@pytest.mark.parametrize("min_size", BLOCK_SIZES)
def test_index_matches_reference_on_repetitive_text(min_size: int) -> None:
    texts = _repetitive_corpus()
    index = ShingleIndex(texts, min_size)
    # Some seed n+1-grams are too frequent to seed runs: the path left to the final linear scan is exercised.
    assert any(
        len(positions) > similarity._MAX_SEED_OCCURRENCES and gram in seeds1
        for seeds1, seeds2 in combinations(index._seeds, 2)
        for gram, positions in seeds2.items()
    )
    _assert_same_as_reference(texts, min_size)


@pytest.mark.parametrize("max_seed", [1, 3])
@pytest.mark.parametrize("seed", range(60))
def test_index_matches_reference_with_low_seed_limit(seed: int, max_seed: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(similarity, "_MAX_SEED_OCCURRENCES", max_seed)
    monkeypatch.setattr(reference, "_MAX_SEED_OCCURRENCES", max_seed)
    texts = _random_corpus(random.Random(1000 + seed))
    for min_size in BLOCK_SIZES:
        _assert_same_as_reference(texts, min_size)


def test_documents_without_shared_ngram() -> None:
    index = ShingleIndex([["a", "b", "c"], ["c", "b", "a"], []], 2)
    assert index.compare(0, 1) == (0.0, [])
    assert index.compare(0, 2) == (0.0, [])
    assert index.compare(2, 2) == (0.0, [])
    assert len(index) == 3


def test_index_can_be_pickled() -> None:
    texts = _random_corpus(random.Random(7))
    index = ShingleIndex(texts, 2)
    copy = pickle.loads(pickle.dumps(index))
    for i, j in combinations(range(len(texts)), 2):
        assert copy.compare(i, j) == index.compare(i, j)


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("min_size", [2, 3])
def test_compare_all_matches_compare(engine: Engine, min_size: int) -> None:
    texts = _random_corpus(random.Random(3)) + _repetitive_corpus()
    expected = [compare(texts[i], texts[j], min_size, engine) for i, j in combinations(range(len(texts)), 2)]
    assert list(compare_all(texts, min_size, engine)) == expected


def test_compare_all_with_fewer_than_two_texts() -> None:
    assert list(compare_all([])) == []
    assert list(compare_all([["a", "b"]])) == []


@pytest.mark.parametrize("enabled", [True, False])
def test_garbage_collector_state_is_restored(enabled: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    texts = [["a", "b", "c"], ["a", "b", "c"]]
    was_enabled = gc.isenabled()
    try:
        gc.enable() if enabled else gc.disable()
        index = ShingleIndex(texts, 2)
        assert gc.isenabled() == enabled
        assert index.compare(0, 1).score == 100.0
        assert gc.isenabled() == enabled
        monkeypatch.setattr(index, "_compare", lambda i, j: 1 / 0)
        with pytest.raises(ZeroDivisionError):
            index.compare(0, 1)
        assert gc.isenabled() == enabled
    finally:
        gc.enable() if was_enabled else gc.disable()
