"""Comparing every pair of documents."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import combinations

from copy_spotter._documents import Document
from copy_spotter._exclusions import (
    Excluded,
    common_runs,
    find_exclusions,
    masked_words,
    merge,
    template_runs,
)
from copy_spotter._normalize import Normalization, check_normalize, normalize_document
from copy_spotter._options import ScoreMode, check_block_size
from copy_spotter._progress import ProgressCallback, emit
from copy_spotter._results import Results
from copy_spotter.similarity import (
    DEFAULT_ENGINE,
    ENGINES,
    Comparison,
    Engine,
    Match,
    ShingleIndex,
    compare,
    compare_all,
    coverage,
)


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
    block_size: int = 4,
    engine: Engine = DEFAULT_ENGINE,
    normalize: Iterable[Normalization] = (),
    stopwords: Iterable[str] = (),
    ignore_quotes: bool = False,
    ignore_bibliography: bool = False,
    templates: Sequence[Document] = (),
    ignore_common: float | None = None,
    references: Sequence[Document] = (),
    compare_submissions: bool = True,
    progress: ProgressCallback | None = None,
) -> Results:
    """Compare every pair of documents, and each document with reference sources.

    Args:
        documents: The documents to compare (the submissions); their names must be unique.
        block_size: Minimum number of consecutive identical words that count as a match. The default, 4, keeps
            the common 2 and 3 word phrases that any two texts share out of the scores.
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
        templates: Documents whose text everyone was given, such as the assignment prompt or a template: passages
            of at least four words found in a template are left out of the matching. Templates are not compared
            with each other and are not part of the results.
        ignore_common: A percentage: passages found in more than this share of the documents (and in at least
            three of them) are left out of the matching, as text that everyone shares rather than copied text.
            The documents are compared twice. Only submissions are counted, and it needs ``compare_submissions``.
        references: Sources to compare every submission with, such as articles or last year's essays. A
            reference is never compared with another reference. In the results the references come after the
            submissions, and ``Results.references`` holds their indexes.
        compare_submissions: Also compare the submissions with each other (the default). ``False`` compares each
            submission with the references only.
        progress: Called with a :class:`Progress` event (stage ``"compare"``) before the first pair and after
            each pair.

    Returns:
        The scores and matching blocks of every compared pair, in ``itertools.combinations`` order. With
        ``normalize`` or ``stopwords``, ``Results.documents`` holds the normalized documents: same names and
        text, normalized words, and no stopwords in ``words`` and ``spans``, so that blocks index the words that
        were matched.
        Excluded passages are listed in ``Results.excluded``; their words never match but still count in the
        scores, so excluding passages can only lower them.

    Raises:
        ValueError: ``block_size`` is below 1, ``engine`` or a normalization is unknown, ``ignore_common`` is not
            within 0 (excluded) and 100 or is used without ``compare_submissions``, or two documents (references
            included) have the same name.
    """
    check_block_size(block_size)
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {', '.join(ENGINES)}, got {engine!r}")
    submissions = len(documents)
    documents = [*documents, *references]
    duplicates = sorted(name for name, count in Counter(document.name for document in documents).items() if count > 1)
    if duplicates:
        raise ValueError(f"document names must be unique, found duplicates: {', '.join(duplicates)}")
    if ignore_common is not None and not 0 < ignore_common <= 100:
        raise ValueError(f"ignore_common must be a percentage above 0 and at most 100, got {ignore_common}")
    if ignore_common is not None and not compare_submissions:
        raise ValueError("ignore_common needs compare_submissions: it counts the submissions sharing a passage")
    indexes = [
        (i, j)
        for i, j in combinations(range(len(documents)), 2)
        if (j < submissions and compare_submissions) or i < submissions <= j
    ]
    normalizations = check_normalize(normalize)
    stopword_set = frozenset(word.lower() for word in stopwords)
    accents = "accents" in normalizations
    options: dict[str, object] = {}
    if normalizations or stopword_set:
        documents = [normalize_document(d, accents=accents, stopwords=stopword_set) for d in documents]
        templates = [normalize_document(d, accents=accents, stopwords=stopword_set) for d in templates]
    if normalizations:
        options["normalize"] = list(normalizations)
    if stopword_set:
        options["stopwords"] = len(stopword_set)

    excluded: tuple[tuple[Excluded, ...], ...] = ()
    if ignore_quotes or ignore_bibliography or templates:
        found = template_runs([d.words for d in documents], [t.words for t in templates])
        excluded = tuple(
            merge(
                [
                    *find_exclusions(d.text, d.spans, quotes=ignore_quotes, bibliography=ignore_bibliography),
                    *(Excluded(start, size, "template") for start, size in runs),
                ]
            )
            for d, runs in zip(documents, found, strict=True)
        )
        options.update({"ignore_quotes": True} if ignore_quotes else {})
        options.update({"ignore_bibliography": True} if ignore_bibliography else {})
        options.update({"templates": [t.name for t in templates]} if templates else {})

    if references:
        options["references"] = len(references)
        options.update({} if compare_submissions else {"compare_submissions": False})
    total = len(indexes) * (1 if ignore_common is None else 2)
    pairs = _compare_pairs(_masked(documents, excluded), indexes, block_size, engine, progress, total=total)
    if ignore_common is not None:
        options["ignore_common"] = ignore_common
        # "More than ignore_common % of the documents", and never fewer than three: two documents sharing a
        # passage is what copy-spotter looks for, not boilerplate.
        min_documents = max(3, int(submissions * ignore_common / 100) + 1)
        among_submissions = ((p.i, p.j, p.blocks) for p in pairs if p.j < submissions)
        common = common_runs([len(d.words) for d in documents], among_submissions, min_documents)
        if any(common):
            excluded = tuple(
                merge([*runs, *(Excluded(start, size, "common") for start, size in extra)])
                for runs, extra in zip(excluded or ((),) * len(documents), common, strict=True)
            )
            pairs = _compare_pairs(
                _masked(documents, excluded), indexes, block_size, engine, progress, total=total, offset=len(pairs)
            )
        else:
            emit(progress, "compare", total, total)
    return Results(
        documents=tuple(documents),
        pairs=tuple(pairs),
        block_size=block_size,
        engine=engine,
        options=options,
        excluded=excluded,
        references=tuple(range(submissions, len(documents))),
    )


def _masked(documents: Sequence[Document], excluded: Sequence[Sequence[Excluded]]) -> list[list[str]]:
    """Return the words to compare: each document's words, with its excluded words made unmatchable."""
    if not excluded:
        return [list(document.words) for document in documents]
    return [masked_words(d.words, k, runs) for k, (d, runs) in enumerate(zip(documents, excluded, strict=True))]


def _compare_pairs(
    words: list[list[str]],
    indexes: list[tuple[int, int]],
    block_size: int,
    engine: Engine,
    progress: ProgressCallback | None,
    *,
    total: int,
    offset: int = 0,
) -> list[Pair]:
    pairs = []
    if len(indexes) == len(words) * (len(words) - 1) // 2:
        # Every pair: one shared index for the whole corpus (shingle engine), same results as compare_pair().
        comparisons: Iterable[Comparison] = compare_all(words, block_size, engine)
    else:
        comparisons = _selected(words, indexes, block_size, engine)
    if offset == 0:
        emit(progress, "compare", 0, total)
    for (i, j), comparison in zip(indexes, comparisons, strict=True):
        pairs.append(_make_pair(i, j, comparison, len(words[i]), len(words[j])))
        emit(progress, "compare", offset + len(pairs), total)
    return pairs


def _selected(
    words: list[list[str]], indexes: list[tuple[int, int]], block_size: int, engine: Engine
) -> Iterator[Comparison]:
    """Compare only the given pairs, still indexing each document once with the shingle engine."""
    if engine == "shingle":
        index = ShingleIndex(words, block_size)
        for i, j in indexes:
            yield index.compare(i, j)
    else:
        for i, j in indexes:
            yield compare(words[i], words[j], block_size, engine)
