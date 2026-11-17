"""HTML report generation: one summary page plus one side-by-side page per pair of documents."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from importlib.resources import files
from pathlib import Path

from copy_spotter.similarity import Match

RESULTS_FILENAME = "_results.html"
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


@dataclass(frozen=True)
class PairResult:
    """Comparison of documents ``i`` and ``j`` (indexes into the document list)."""

    i: int
    j: int
    score: float
    blocks: list[Match]

    @property
    def filename(self) -> str:
        return f"{self.i}_{self.j}.html"


def _template(name: str) -> str:
    return files("copy_spotter").joinpath(name).read_text(encoding="utf-8")


def _render(template: str, **values: str) -> str:
    # Single pass so placeholders that happen to appear in substituted text are left alone.
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], template)


def score_style(score: float) -> str:
    """Return the CSS for a similarity score: the higher, the more alarming."""
    if score > 15:
        return "color: #990033; font-weight: bold"
    if score > 10:
        return "color: #cc5200"
    if score > 5:
        return "color: #b38f00"
    return "color: green"


def block_color(index: int) -> str:
    """Return a readable, deterministic color for the n-th matching block."""
    hue = (index * 137.508) % 360  # golden angle keeps consecutive blocks visually distinct
    return f"hsl({hue:.0f}, 75%, 35%)"


def highlight(words: Sequence[str], spans: Sequence[tuple[int, int, int]]) -> str:
    """Return the words as HTML, wrapping each ``(start, size, color_index)`` span in a colored tag.

    ``spans`` must be sorted by start and not overlap.
    """
    parts: list[str] = []
    cursor = 0
    for start, size, color_index in spans:
        if start > cursor:
            parts.append(escape(" ".join(words[cursor:start])))
        matched = escape(" ".join(words[start : start + size]))
        parts.append(f'<span class="match" style="color: {block_color(color_index)}">{matched}</span>')
        cursor = start + size
    if cursor < len(words):
        parts.append(escape(" ".join(words[cursor:])))
    return " ".join(parts)


def render_comparison(names: tuple[str, str], words: tuple[Sequence[str], Sequence[str]], pair: PairResult) -> str:
    """Return the side-by-side HTML page for one pair of documents."""
    left = highlight(words[0], [(m.a, m.size, k) for k, m in enumerate(pair.blocks)])
    right = highlight(words[1], [(m.b, m.size, k) for k, m in enumerate(pair.blocks)])
    return _render(
        _template("comparison.html"),
        title=escape(f"{names[0]} vs {names[1]}"),
        score=f"{pair.score:g}",
        left_name=escape(names[0]),
        right_name=escape(names[1]),
        left=left,
        right=right,
    )


def _score_link(pair: PairResult) -> str:
    return f'<a href="{pair.filename}" style="{score_style(pair.score)}">{pair.score:g}</a>'


def render_results(names: Sequence[str], pairs: Sequence[PairResult], meta: str = "") -> str:
    """Return the summary page: pairs sorted by similarity, then the full matrix."""
    by_cell = {}
    for pair in pairs:
        by_cell[pair.i, pair.j] = pair
        by_cell[pair.j, pair.i] = pair

    pair_rows = [
        f'<tr><td>{_score_link(p)}</td><td class="name">{escape(names[p.i])}</td>'
        f'<td class="name">{escape(names[p.j])}</td></tr>'
        for p in sorted(pairs, key=lambda p: p.score, reverse=True)
    ]

    header = "".join(f'<th class="name" title="{escape(n)}">{escape(n)}</th>' for n in names)
    matrix_rows = [f'<tr><th class="name"></th>{header}</tr>']
    for i, name in enumerate(names):
        cells = []
        for j in range(len(names)):
            if i == j:
                cells.append('<td class="self">-</td>')
            else:
                cells.append(f"<td>{_score_link(by_cell[i, j])}</td>")
        matrix_rows.append(f'<tr><th class="name" title="{escape(name)}">{escape(name)}</th>{"".join(cells)}</tr>')

    return _render(
        _template("results.html"),
        meta=escape(meta),
        pairs="\n".join(pair_rows),
        matrix="\n".join(matrix_rows),
    )


def write_report(
    out_dir: Path,
    names: Sequence[str],
    words: Sequence[Sequence[str]],
    pairs: Sequence[PairResult],
    meta: str = "",
) -> Path:
    """Write the summary page and every comparison page into ``out_dir``; return the summary path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for pair in pairs:
        page = render_comparison((names[pair.i], names[pair.j]), (words[pair.i], words[pair.j]), pair)
        (out_dir / pair.filename).write_text(page, encoding="utf-8")
    results = out_dir / RESULTS_FILENAME
    results.write_text(render_results(names, pairs, meta), encoding="utf-8")
    return results
