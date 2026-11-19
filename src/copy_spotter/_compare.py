"""Comparing every pair of documents."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

from copy_spotter._documents import Document
from copy_spotter._options import ScoreMode, check_block_size
from copy_spotter._progress import ProgressCallback, emit
from copy_spotter._results import Results
from copy_spotter.similarity import DEFAULT_ENGINE, ENGINES, Comparison, Engine, Match, compare, compare_all, coverage


@dataclass(frozen=True, kw_only=True)
class Pair:
    """The comparison of two documents, ``documents[i]`` and ``documents[j]`` with ``i < j``.

    Attributes:
        i: Index of the first document.
        j: Index of the second document.
        ratio: Symmetric similarity score of the pair given by the engine, in percent.
        coverage_i: Percentage of the words of document ``i`` found in document ``j``.
        coverage_j: Percentage of the words of document ``j`` found in document ``i``.
        blocks: Runs of identical words: ``Match(a, b, size)`` means ``words_i[a:a + size]`` equals
            ``words_j[b:b + size]``. Blocks never overlap on either side but can be in any order on the ``j`` side.
    """

    i: int
    j: int
    ratio: float
    coverage_i: float
    coverage_j: float
    blocks: tuple[Match, ...]

    @property
    def matched_words(self) -> int:
        """Number of words of each document covered by the blocks."""
        return sum(block.size for block in self.blocks)

    def scores(self, score: ScoreMode = "coverage") -> tuple[float, float]:
        """Return the scores shown for (``i`` found in ``j``, ``j`` found in ``i``).

        Args:
            score: ``"coverage"`` gives ``(coverage_i, coverage_j)``; ``"ratio"`` gives ``(ratio, ratio)``.
        """
        if score == "ratio":
            return self.ratio, self.ratio
        return self.coverage_i, self.coverage_j


def compare_pair(i: int, j: int, words_i: list[str], words_j: list[str], *, block_size: int, engine: Engine) -> Pair:
    """Compare the words of documents ``i`` and ``j``: the unit of work, pure and picklable."""
    return _make_pair(i, j, compare(words_i, words_j, block_size, engine), len(words_i), len(words_j))


def _make_pair(i: int, j: int, comparison: Comparison, len_i: int, len_j: int) -> Pair:
    ratio, blocks = comparison
    coverage_i, coverage_j = coverage(blocks, len_i, len_j)
    return Pair(i=i, j=j, ratio=ratio, coverage_i=coverage_i, coverage_j=coverage_j, blocks=tuple(blocks))


def compare_documents(
    documents: Sequence[Document],
    *,
    block_size: int = 2,
    engine: Engine = DEFAULT_ENGINE,
    progress: ProgressCallback | None = None,
) -> Results:
    """Compare every pair of documents.

    Args:
        documents: The documents to compare; their names must be unique.
        block_size: Minimum number of consecutive identical words that count as a match.
        engine: ``"shingle"`` finds copied passages in any order; ``"difflib"`` is the legacy in-order matcher.
        progress: Called with a :class:`Progress` event (stage ``"compare"``) before the first pair and after
            each pair.

    Returns:
        The scores and matching blocks of every pair, in ``itertools.combinations`` order.

    Raises:
        ValueError: ``block_size`` is below 1, ``engine`` is unknown or two documents have the same name.
    """
    check_block_size(block_size)
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {', '.join(ENGINES)}, got {engine!r}")
    duplicates = sorted(name for name, count in Counter(document.name for document in documents).items() if count > 1)
    if duplicates:
        raise ValueError(f"document names must be unique, found duplicates: {', '.join(duplicates)}")

    words = [list(document.words) for document in documents]
    indexes = list(combinations(range(len(documents)), 2))
    pairs = []
    # One shared index for the whole corpus (shingle engine): same results as compare_pair() on each pair.
    comparisons = compare_all(words, block_size, engine)
    emit(progress, "compare", 0, len(indexes))
    for (i, j), comparison in zip(indexes, comparisons, strict=True):
        pairs.append(_make_pair(i, j, comparison, len(words[i]), len(words[j])))
        emit(progress, "compare", len(pairs), len(indexes))
    return Results(documents=tuple(documents), pairs=tuple(pairs), block_size=block_size, engine=engine)
