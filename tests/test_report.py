from __future__ import annotations

import re
from pathlib import Path

from copy_spotter.report import (
    RESULTS_FILENAME,
    PairResult,
    block_color,
    highlight,
    render_comparison,
    render_results,
    write_report,
)
from copy_spotter.similarity import compare


def _highlighted(html: str) -> list[str]:
    return re.findall(r'<span class="match"[^>]*>(.*?)</span>', html)


def test_highlight_wraps_only_the_matched_words() -> None:
    html = highlight("a b c d e".split(), [(1, 2, 0)])
    assert _highlighted(html) == ["b c"]
    assert html.startswith("a <span")
    assert html.endswith("</span> d e")


def test_highlight_respects_word_boundaries() -> None:
    # "le chat" used to be highlighted inside "le chaton" because blocks were searched as substrings.
    words1 = "x le chat y".split()
    words2 = "le chaton z le chat w".split()
    pair = PairResult(0, 1, *compare(words1, words2, 2))
    html = render_comparison(("a", "b"), (words1, words2), pair)
    assert html.count('class="match"') == 2  # once per side
    assert "chaton" not in "".join(_highlighted(html))


def test_text_is_escaped() -> None:
    html = highlight(["<script>", "alert"], [])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_placeholders_in_document_text_are_not_expanded() -> None:
    words = ["{{right}}", "text"]
    pair = PairResult(0, 1, 50.0, [])
    html = render_comparison(("a", "b"), (words, ["other"]), pair)
    assert "{{right}}" in html


def test_block_colors_are_deterministic_and_distinct() -> None:
    assert block_color(3) == block_color(3)
    assert len({block_color(i) for i in range(20)}) == 20


def test_results_links_are_relative_and_ignore_numeric_names() -> None:
    names = ["2024.txt", "nan.txt", "b.txt"]
    pairs = [PairResult(0, 1, 10.0, []), PairResult(0, 2, 20.0, []), PairResult(1, 2, 30.0, [])]
    html = render_results(names, pairs)
    links = re.findall(r'href="([^"]+)"', html)
    # 3 links in the sorted pair list plus 6 in the matrix, never on a file name.
    assert len(links) == 9
    assert set(links) == {"0_1.html", "0_2.html", "1_2.html"}
    assert links[0] == "1_2.html"  # highest score first


def test_write_report_in_dir_named_results(tmp_path: Path) -> None:
    out_dir = tmp_path / "my_results"
    pairs = [PairResult(0, 1, 42.0, [])]
    results = write_report(out_dir, ["a", "b"], [["x"], ["y"]], pairs)
    assert results == out_dir / RESULTS_FILENAME
    for href in re.findall(r'href="([^"]+)"', results.read_text()):
        assert (out_dir / href).is_file()
