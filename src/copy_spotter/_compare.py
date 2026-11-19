"""Comparing every pair of documents."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations

from copy_spotter._documents import Document
from copy_spotter._exclusions import Excluded, find_exclusions, masked_words
from copy_spotter._normalize import Normalization, check_normalize, normalize_document
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
    normalize: Iterable[Normalization] = (),
    stopwords: Iterable[str] = (),
    ignore_quotes: bool = False,
    ignore_bibliography: bool = False,
    progress: ProgressCallback | None = None,
) -> Results:
    """Compare every pair of documents.

    Args:
        documents: The documents to compare; their names must be unique.
        block_size: Minimum number of consecutive identical words that count as a match.
        engine: ``"shingle"`` finds copied passages in any order; ``"difflib"`` is the legacy in-order matcher.
        normalize: ``("accents",)`` folds accents and compatibility characters before matching, so "élève"
            matches "eleve".
        stopwords: Words left out of the matching, for instance ``stopword_list("en")``: a passage that differs
            only by these words still matches. Stopwords are not counted in the scores.
        ignore_quotes: Leave the passages between quotation marks (straight, curly, guillemets) out of the
            matching. They stay in the documents and in the reports, where they are shown in grey.
        ignore_bibliography: Leave the bibliography out of the matching: the text from the last heading such as
            "References", "Bibliography" or "Works cited" (on a line of its own, past the first 30% of the
            text) to the end.
        progress: Called with a :class:`Progress` event (stage ``"compare"``) before the first pair and after
            each pair.

    Returns:
        The scores and matching blocks of every pair, in ``itertools.combinations`` order. With ``normalize`` or
        ``stopwords``, ``Results.documents`` holds the normalized documents: same names and text, normalized
        words, and no stopwords in ``words`` and ``spans``, so that blocks index the words that were matched.
        Excluded passages are listed in ``Results.excluded``; their words never match but still count in the
        scores, so excluding passages can only lower them.

    Raises:
        ValueError: ``block_size`` is below 1, ``engine`` or a normalization is unknown, or two documents have
            the same name.
    """
    check_block_size(block_size)
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {', '.join(ENGINES)}, got {engine!r}")
    duplicates = sorted(name for name, count in Counter(document.name for document in documents).items() if count > 1)
    if duplicates:
        raise ValueError(f"document names must be unique, found duplicates: {', '.join(duplicates)}")
    normalizations = check_normalize(normalize)
    stopword_set = frozenset(word.lower() for word in stopwords)
    accents = "accents" in normalizations
    options: dict[str, object] = {}
    if normalizations or stopword_set:
        documents = [normalize_document(d, accents=accents, stopwords=stopword_set) for d in documents]
    if normalizations:
        options["normalize"] = list(normalizations)
    if stopword_set:
        options["stopwords"] = len(stopword_set)

    excluded: tuple[tuple[Excluded, ...], ...] = ()
    if ignore_quotes or ignore_bibliography:
        excluded = tuple(
            find_exclusions(d.text, d.spans, quotes=ignore_quotes, bibliography=ignore_bibliography) for d in documents
        )
        options.update({"ignore_quotes": True} if ignore_quotes else {})
        options.update({"ignore_bibliography": True} if ignore_bibliography else {})

    words = [list(document.words) for document in documents]
    if excluded:
        words = [masked_words(w, k, runs) for k, (w, runs) in enumerate(zip(words, excluded, strict=True))]
    pairs = _compare_all_pairs(words, block_size, engine, progress)
    return Results(
        documents=tuple(documents),
        pairs=tuple(pairs),
        block_size=block_size,
        engine=engine,
        options=options,
        excluded=excluded,
    )


def _compare_all_pairs(
    words: list[list[str]], block_size: int, engine: Engine, progress: ProgressCallback | None
) -> list[Pair]:
    indexes = list(combinations(range(len(words)), 2))
    pairs = []
    # One shared index for the whole corpus (shingle engine): same results as compare_pair() on each pair.
    comparisons = compare_all(words, block_size, engine)
    emit(progress, "compare", 0, len(indexes))
    for (i, j), comparison in zip(indexes, comparisons, strict=True):
        pairs.append(_make_pair(i, j, comparison, len(words[i]), len(words[j])))
        emit(progress, "compare", len(pairs), len(indexes))
    return pairs
