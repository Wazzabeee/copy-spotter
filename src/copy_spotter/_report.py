"""HTML report generation: one summary page plus one side-by-side page per pair of documents."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from html import escape
from importlib.resources import files
from typing import TYPE_CHECKING

from copy_spotter._options import DEFAULT_THRESHOLDS, ScoreMode

if TYPE_CHECKING:
    from copy_spotter._compare import Pair
    from copy_spotter._documents import Document
    from copy_spotter._results import Results

RESULTS_FILENAME = "_results.html"
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def page_name(pair: Pair) -> str:
    """Return the file name of the comparison page of ``pair`` in the multi-page report."""
    return f"{pair.i}_{pair.j}.html"


def _template(name: str) -> str:
    return files("copy_spotter").joinpath(name).read_text(encoding="utf-8")


def _render(template: str, **values: str) -> str:
    # Single pass so placeholders that happen to appear in substituted text are left alone.
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def score_style(score: float, thresholds: Sequence[float] = DEFAULT_THRESHOLDS) -> str:
    """Return the CSS for a similarity score: the higher, the more alarming.

    ``thresholds`` are three increasing percentages: above each one the score gets a more alarming color.
    """
    low, medium, high = thresholds
    if score > high:
        return "color: #990033; font-weight: bold"
    if score > medium:
        return "color: #cc5200"
    if score > low:
        return "color: #b38f00"
    return "color: green"


def block_color(index: int) -> str:
    """Return a readable, deterministic color for the n-th matching block."""
    hue = (index * 137.508) % 360  # golden angle keeps consecutive blocks visually distinct
    return f"hsl({hue:.0f}, 75%, 35%)"


def highlight(document: Document, spans: Iterable[tuple[int, int, int]]) -> str:
    """Return the document's text as HTML, wrapping each ``(start, size, color_index)`` word range in a colored tag.

    Each range covers words ``[start, start + size)`` and is shown from the first word's first character to the
    last word's last character. Ranges may come in any order; a range overlapping an earlier one is trimmed.
    """
    text = document.text
    parts: list[str] = []
    cursor = 0  # characters already written
    next_word = 0  # first word not highlighted yet
    for start, size, color_index in sorted(spans):
        first, stop = max(start, next_word), start + size
        if first >= stop:
            continue
        begin, end = document.spans[first][0], document.spans[stop - 1][1]
        next_word = stop
        parts.append(escape(text[cursor:begin]))
        matched = escape(text[begin:end])
        parts.append(f'<span class="match" style="color: {block_color(color_index)}">{matched}</span>')
        cursor = end
    parts.append(escape(text[cursor:]))
    return "".join(parts)


def _score_span(score: float, thresholds: Sequence[float]) -> str:
    return f'<span style="{score_style(score, thresholds)}">{score:g}%</span>'


def render_comparison(
    results: Results,
    pair: Pair,
    score_mode: ScoreMode = "coverage",
    *,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> str:
    """Return the side-by-side HTML page for one pair of documents."""
    documents = results.documents[pair.i], results.documents[pair.j]
    names = documents[0].name, documents[1].name
    left = highlight(documents[0], [(m.a, m.size, k) for k, m in enumerate(pair.blocks)])
    right = highlight(documents[1], [(m.b, m.size, k) for k, m in enumerate(pair.blocks)])
    return _render(
        _template("comparison.html"),
        title=escape(f"{names[0]} vs {names[1]}"),
        score=_comparison_score(names, pair, score_mode, thresholds),
        left_name=escape(names[0]),
        right_name=escape(names[1]),
        left=left,
        right=right,
    )


def _comparison_score(names: tuple[str, str], pair: Pair, score_mode: ScoreMode, thresholds: Sequence[float]) -> str:
    left_in_right, right_in_left = pair.scores(score_mode)
    if score_mode == "ratio":
        return f"Similarity: {_score_span(left_in_right, thresholds)}"
    left, right = escape(names[0]), escape(names[1])
    return (
        f"{left} found in {right}: {_score_span(left_in_right, thresholds)}"
        f" &middot; {right} found in {left}: {_score_span(right_in_left, thresholds)}"
    )


def _score_link(pair: Pair, score: float, thresholds: Sequence[float]) -> str:
    return f'<a href="{page_name(pair)}" style="{score_style(score, thresholds)}">{score:g}</a>'


def render_results(
    results: Results,
    meta: str = "",
    score_mode: ScoreMode = "coverage",
    *,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> str:
    """Return the summary page: pairs sorted by similarity, then the full matrix.

    In coverage mode the matrix is not symmetric: the cell at row ``i``, column ``j`` is the
    percentage of document ``i`` found in document ``j``.
    """
    names = [document.name for document in results.documents]
    by_cell: dict[tuple[int, int], tuple[Pair, float]] = {}
    for pair in results.pairs:
        i_in_j, j_in_i = pair.scores(score_mode)
        by_cell[pair.i, pair.j] = pair, i_in_j
        by_cell[pair.j, pair.i] = pair, j_in_i

    if score_mode == "ratio":
        pairs_head = '<th>Similarity</th><th class="name">Document</th><th class="name">Document</th>'
        matrix_legend = "Symmetric similarity ratio (%) of each pair of documents."
    else:
        pairs_head = (
            '<th title="% of A found in B">A in B</th><th title="% of B found in A">B in A</th>'
            '<th class="name">Document A</th><th class="name">Document B</th>'
        )
        matrix_legend = "Each cell is the % of the row document found in the column document."

    pair_rows = []
    for p in results.ranked(score_mode):
        shown = p.scores(score_mode)[:1] if score_mode == "ratio" else p.scores(score_mode)
        links = "".join(f"<td>{_score_link(p, s, thresholds)}</td>" for s in shown)
        pair_rows.append(
            f'<tr>{links}<td class="name">{escape(names[p.i])}</td><td class="name">{escape(names[p.j])}</td></tr>'
        )

    header = "".join(f'<th class="name" title="{escape(n)}">{escape(n)}</th>' for n in names)
    matrix_rows = [f'<tr><th class="name"></th>{header}</tr>']
    for i, name in enumerate(names):
        cells = []
        for j in range(len(names)):
            if i == j:
                cells.append('<td class="self">-</td>')
            else:
                cells.append(f"<td>{_score_link(*by_cell[i, j], thresholds)}</td>")
        matrix_rows.append(f'<tr><th class="name" title="{escape(name)}">{escape(name)}</th>{"".join(cells)}</tr>')

    return _render(
        _template("results.html"),
        meta=escape(meta),
        pairs_head=pairs_head,
        pairs="\n".join(pair_rows),
        matrix_legend=matrix_legend,
        matrix="\n".join(matrix_rows),
    )


def render_pages(
    results: Results,
    meta: str = "",
    *,
    score: ScoreMode = "coverage",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> dict[str, str]:
    """Return the multi-page report as ``{file name: html}``: the summary page first, then one page per pair."""
    pages = {RESULTS_FILENAME: render_results(results, meta, score, thresholds=thresholds)}
    for pair in results.pairs:
        pages[page_name(pair)] = render_comparison(results, pair, score, thresholds=thresholds)
    return pages
