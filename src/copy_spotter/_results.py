"""The results of a comparison and the ways to render them: HTML reports, JSON and CSV."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from copy_spotter import _export, _report, _single_page
from copy_spotter._options import (
    DEFAULT_THRESHOLDS,
    REPORT_LAYOUTS,
    ReportLayout,
    ScoreMode,
    check_score,
    check_thresholds,
)
from copy_spotter._version import __version__
from copy_spotter.similarity import Engine

if TYPE_CHECKING:
    from copy_spotter._compare import Pair
    from copy_spotter._documents import Document
    from copy_spotter._exclusions import Excluded

_IGNORED_PASSAGES = (("ignore_quotes", "quotations"), ("ignore_bibliography", "bibliographies"))


def describe_options(options: Mapping[str, object]) -> str:
    """Return the matching options for the one-line summary of a run: ``""``, or ``", accents folded, ..."``."""
    parts = []
    if options.get("normalize"):
        parts.append("accents folded")
    if options.get("stopwords"):
        parts.append(f"{options['stopwords']} stopwords ignored")
    ignored = [name for key, name in _IGNORED_PASSAGES if options.get(key)]
    templates = options.get("templates")
    if isinstance(templates, list) and templates:
        ignored.append(f"text of {len(templates)} template{'s' if len(templates) > 1 else ''}")
    if options.get("ignore_common") is not None:
        ignored.append(f"passages in more than {options['ignore_common']:g}% of the documents")
    if ignored:
        parts.append(f"{', '.join(ignored)} ignored")
    if options.get("references"):
        only = " only" if options.get("compare_submissions") is False else ""
        count = options["references"]
        parts.append(f"compared with {count} reference source{'' if count == 1 else 's'}{only}")
    return "".join(f", {part}" for part in parts)


@dataclass(frozen=True)
class Results:
    """The outcome of :func:`compare_documents`: every document and every pair.

    The score mode and the color thresholds are not part of the results: they only change how the results are
    sorted and shown, so every rendering method takes them as arguments.

    Attributes:
        documents: The compared documents; pairs refer to them by index.
        pairs: One :class:`Pair` per pair of documents ``i < j``, in ``itertools.combinations`` order.
        block_size: Minimum number of consecutive identical words that counted as a match.
        engine: The matching engine used.
        options: The matching options that were turned on, as JSON values, for instance
            ``{"normalize": ["accents"], "stopwords": 174}`` (the number of stopwords). Empty by default.
        excluded: The passages left out of the matching (quotations, bibliography, template text, common
            passages), one tuple of
            :class:`Excluded` word runs per document, sorted and non-overlapping. Empty (``()``) when no passage
            was excluded.
        references: Indexes of the documents that are reference sources (``compare_documents(references=...)``),
            after the submissions. A reference is only compared with submissions. Empty by default.
    """

    documents: tuple[Document, ...]
    pairs: tuple[Pair, ...]
    block_size: int
    engine: Engine
    options: Mapping[str, object] = field(default_factory=dict, hash=False)
    excluded: tuple[tuple[Excluded, ...], ...] = ()
    references: tuple[int, ...] = ()

    def is_reference(self, index: int) -> bool:
        """Return True if ``documents[index]`` is a reference source rather than a submission."""
        return index in self.references

    def ranked(self, score: ScoreMode = "coverage") -> list[Pair]:
        """Return the pairs sorted by their higher score in the ``score`` mode, highest first.

        Ties keep the ``combinations`` order (by ``i``, then ``j``).

        Raises:
            ValueError: ``score`` is not ``"coverage"`` or ``"ratio"``.
        """
        check_score(score)
        return sorted(self.pairs, key=lambda pair: (-max(pair.scores(score)), pair.i, pair.j))

    def pair(self, a: int | str, b: int | str) -> Pair:
        """Return the pair of two documents given by index or by name, in either order.

        Raises:
            KeyError: A name is unknown or the pair is not in the results.
            ValueError: Both arguments are the same document.
        """
        i, j = sorted(self._index(x) for x in (a, b))
        if i == j:
            raise ValueError(f"a pair needs two different documents, got {a!r} twice")
        n = len(self.documents)
        position = i * n - i * (i + 1) // 2 + j - i - 1  # rank of (i, j) in combinations(range(n), 2)
        if 0 <= position < len(self.pairs) and (self.pairs[position].i, self.pairs[position].j) == (i, j):
            return self.pairs[position]
        for pair in self.pairs:  # results built by hand may hold only some pairs
            if (pair.i, pair.j) == (i, j):
                return pair
        raise KeyError((a, b))

    def _index(self, document: int | str) -> int:
        if isinstance(document, int):
            if not 0 <= document < len(self.documents):
                raise KeyError(document)
            return document
        for index, candidate in enumerate(self.documents):
            if candidate.name == document:
                return index
        raise KeyError(document)

    def _meta(self, meta: str | None, score: ScoreMode) -> str:
        if meta is not None:
            return meta
        return (
            f"{len(self.documents)} documents, minimum block size {self.block_size}, "
            f"{self.engine} engine{describe_options(self.options)}, {score} score, copy-spotter {__version__}"
        )

    def to_dict(
        self, *, score: ScoreMode = "coverage", thresholds: Iterable[float] = DEFAULT_THRESHOLDS
    ) -> dict[str, Any]:
        """Return the JSON export as a dict, pairs sorted with :meth:`ranked`.

        Args:
            score: Score mode used to sort the pairs, recorded as ``score_mode``.
            thresholds: Color thresholds of the HTML report, recorded as ``thresholds``.

        Raises:
            ValueError: Invalid ``score`` or ``thresholds``.
        """
        return _export.export_data(self, score=check_score(score), thresholds=check_thresholds(thresholds))

    def to_json(self, *, score: ScoreMode = "coverage", thresholds: Iterable[float] = DEFAULT_THRESHOLDS) -> str:
        """Return :meth:`to_dict` as indented JSON text, ending with a newline."""
        return _export.export_json(self, score=check_score(score), thresholds=check_thresholds(thresholds))

    def to_csv(self, *, score: ScoreMode = "coverage") -> str:
        """Return one CSV row per pair, sorted with :meth:`ranked`.

        Rows end with ``\\r\\n``, as the csv module writes them: write the text with ``newline=""``.
        """
        return _export.export_csv(self, score=check_score(score))

    def write_json(
        self,
        path: str | Path,
        *,
        score: ScoreMode = "coverage",
        thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
    ) -> Path:
        """Write :meth:`to_json` to ``path`` (UTF-8) pair by pair, without building the whole text in memory.

        The file has the same content as :meth:`to_json`. Its directory must exist. Returns ``path`` as a ``Path``.

        Raises:
            ValueError: Invalid ``score`` or ``thresholds``.
        """
        score, thresholds = check_score(score), check_thresholds(thresholds)
        path = Path(path)
        with path.open("w", encoding="utf-8") as out:
            _export.write_json(self, out, score=score, thresholds=thresholds)
        return path

    def write_csv(self, path: str | Path, *, score: ScoreMode = "coverage") -> Path:
        """Write :meth:`to_csv` to ``path`` (UTF-8) row by row; same content as :meth:`to_csv`.

        Its directory must exist. Returns ``path`` as a ``Path``.

        Raises:
            ValueError: Invalid ``score``.
        """
        score = check_score(score)
        path = Path(path)
        with path.open("w", encoding="utf-8", newline="") as out:
            _export.write_csv(self, out, score=score)
        return path

    def to_html(
        self,
        *,
        score: ScoreMode = "coverage",
        thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
        meta: str | None = None,
    ) -> str:
        """Return the single-page HTML report: self-contained, no external resources, works offline.

        Args:
            score: Score shown and used to sort: ``"coverage"`` or ``"ratio"``.
            thresholds: Three increasing percentages above which scores turn yellow, orange and red.
            meta: One line describing the run, shown under the title. Defaults to a summary of the results.

        Raises:
            ValueError: Invalid ``score`` or ``thresholds``.
        """
        score = check_score(score)
        return _single_page.render_single(
            self, self._meta(meta, score), score=score, thresholds=check_thresholds(thresholds)
        )

    def to_html_pages(
        self,
        *,
        score: ScoreMode = "coverage",
        thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
        meta: str | None = None,
    ) -> dict[str, str]:
        """Return the multi-page HTML report as ``{file name: html}``.

        The summary page comes first, as ``_results.html``, then one ``<i>_<j>.html`` page per pair; pages link to
        each other by these relative names. Arguments are those of :meth:`to_html`.
        """
        score = check_score(score)
        return _report.render_pages(self, self._meta(meta, score), score=score, thresholds=check_thresholds(thresholds))

    def save(
        self,
        out_dir: str | Path,
        *,
        report: ReportLayout = "single",
        score: ScoreMode = "coverage",
        thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
        meta: str | None = None,
    ) -> Path:
        """Write the HTML report into ``out_dir``, created if missing.

        Args:
            out_dir: Directory of the report.
            report: ``"single"`` writes one self-contained file; ``"pages"`` writes a summary page plus one page per
                pair.
            score: See :meth:`to_html`.
            thresholds: See :meth:`to_html`.
            meta: See :meth:`to_html`.

        Returns:
            The path of the page to open, ``out_dir/_results.html``.

        Raises:
            ValueError: Invalid ``report``, ``score`` or ``thresholds``.
        """
        if report not in REPORT_LAYOUTS:
            raise ValueError(f"report must be one of {', '.join(REPORT_LAYOUTS)}, got {report!r}")
        if report == "single":
            pages = {_report.RESULTS_FILENAME: self.to_html(score=score, thresholds=thresholds, meta=meta)}
        else:
            pages = self.to_html_pages(score=score, thresholds=thresholds, meta=meta)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename, html in pages.items():
            (out_dir / filename).write_text(html, encoding="utf-8")
        return out_dir / _report.RESULTS_FILENAME
