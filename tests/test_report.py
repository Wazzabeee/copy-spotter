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
    score_style,
    write_report,
)
from copy_spotter.similarity import Match, compare, coverage


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
    score, blocks = compare(words1, words2, 2)
    pair = PairResult(0, 1, score, blocks, *coverage(blocks, len(words1), len(words2)))
    html = render_comparison(("a", "b"), (words1, words2), pair)
    assert html.count('class="match"') == 2  # once per side
    assert "chaton" not in "".join(_highlighted(html))


def test_text_is_escaped() -> None:
    html = highlight(["<script>", "alert"], [])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_placeholders_in_document_text_are_not_expanded() -> None:
    words = ["{{right}}", "text"]
    pair = PairResult(0, 1, 50.0, [], 50.0, 50.0)
    html = render_comparison(("a", "b"), (words, ["other"]), pair)
    assert "{{right}}" in html


def test_block_colors_are_deterministic_and_distinct() -> None:
    assert block_color(3) == block_color(3)
    assert len({block_color(i) for i in range(20)}) == 20


def test_results_links_are_relative_and_ignore_numeric_names() -> None:
    names = ["2024.txt", "nan.txt", "b.txt"]
    pairs = [
        PairResult(0, 1, 10.0, [], 10.0, 10.0),
        PairResult(0, 2, 20.0, [], 20.0, 20.0),
        PairResult(1, 2, 30.0, [], 30.0, 30.0),
    ]
    html = render_results(names, pairs)
    links = re.findall(r'href="([^"]+)"', html)
    # 2 links per pair in the sorted pair list plus 6 in the matrix, never on a file name.
    assert len(links) == 12
    assert set(links) == {"0_1.html", "0_2.html", "1_2.html"}
    assert links[0] == "1_2.html"  # highest score first


def test_write_report_in_dir_named_results(tmp_path: Path) -> None:
    out_dir = tmp_path / "my_results"
    pairs = [PairResult(0, 1, 42.0, [], 40.0, 45.0)]
    results = write_report(out_dir, ["a", "b"], [["x"], ["y"]], pairs)
    assert results == out_dir / RESULTS_FILENAME
    for href in re.findall(r'href="([^"]+)"', results.read_text()):
        assert (out_dir / href).is_file()


def _matrix_cells(html: str) -> list[list[str]]:
    matrix = html.split("Similarity matrix", 1)[1]
    rows = re.findall(r"<tr>(.*?)</tr>", matrix)[1:]  # skip the header row
    return [re.findall(r"<td[^>]*>(?:<a [^>]*>)?([^<]*)", row) for row in rows]


def test_matrix_is_asymmetric_in_coverage_mode() -> None:
    # Document 0 is fully copied into the ten times longer document 1.
    pairs = [PairResult(0, 1, 18.182, [], 100.0, 10.0)]
    html = render_results(["short.txt", "long.txt"], pairs)
    assert _matrix_cells(html) == [["-", "100"], ["10", "-"]]
    assert "row document found in the column document" in html


def test_pairs_sorted_by_max_coverage_and_show_both_directions() -> None:
    pairs = [
        PairResult(0, 1, 40.0, [], 40.0, 40.0),
        PairResult(0, 2, 18.0, [], 10.0, 100.0),
        PairResult(1, 2, 1.0, [], 1.0, 1.0),
    ]
    html = render_results(["a", "b", "c"], pairs)
    pair_list = html.split("Similarity matrix", 1)[0]
    rows = re.findall(r"<tbody>(.*?)</tbody>", pair_list, re.S)[0]
    assert re.findall(r'href="([^"]+)"[^>]*>([^<]*)', rows) == [
        ("0_2.html", "10"),
        ("0_2.html", "100"),
        ("0_1.html", "40"),
        ("0_1.html", "40"),
        ("1_2.html", "1"),
        ("1_2.html", "1"),
    ]


def test_ratio_mode_shows_the_symmetric_score_everywhere() -> None:
    pairs = [
        PairResult(0, 1, 18.182, [], 100.0, 10.0),
        PairResult(0, 2, 30.0, [], 5.0, 6.0),
        PairResult(1, 2, 1.0, [], 2.0, 3.0),
    ]
    html = render_results(["a", "b", "c"], pairs, score_mode="ratio")
    assert _matrix_cells(html) == [["-", "18.182", "30"], ["18.182", "-", "1"], ["30", "1", "-"]]
    pair_list = html.split("Similarity matrix", 1)[0]
    assert re.findall(r'href="([^"]+)"[^>]*>([^<]*)', pair_list) == [
        ("0_2.html", "30"),
        ("0_1.html", "18.182"),
        ("1_2.html", "1"),
    ]
    page = render_comparison(("a", "b"), (["x"], ["y"]), pairs[0], score_mode="ratio")
    assert "Similarity:" in page
    assert ">18.182%<" in page
    assert "100" not in page


def test_comparison_page_shows_both_directions() -> None:
    pair = PairResult(0, 1, 18.182, [], 100.0, 10.0)
    page = render_comparison(("short.txt", "long.txt"), (["x"], ["y"]), pair)
    assert re.search(r"short\.txt found in long\.txt: <span[^>]*>100%</span>", page)
    assert re.search(r"long\.txt found in short\.txt: <span[^>]*>10%</span>", page)


def test_score_colors_follow_the_displayed_score() -> None:
    pair = PairResult(0, 1, 18.182, [], 100.0, 1.0)
    html = render_results(["a", "b"], [pair])
    assert f'style="{score_style(100.0)}">100<' in html
    assert f'style="{score_style(1.0)}">1<' in html
    ratio = render_results(["a", "b"], [pair], score_mode="ratio")
    assert f'style="{score_style(18.182)}">18.182<' in ratio


def test_blocks_out_of_order_on_the_right_side_are_highlighted() -> None:
    words1 = "alpha beta gamma delta".split()
    words2 = "gamma delta alpha beta".split()
    pair = PairResult(0, 1, 100.0, [Match(0, 2, 2), Match(2, 0, 2)], 100.0, 100.0)
    html = render_comparison(("a", "b"), (words1, words2), pair)
    assert _highlighted(html) == ["alpha beta", "gamma delta", "gamma delta", "alpha beta"]
    # Each block keeps its color on both sides.
    colors = re.findall(r'style="color: (hsl[^"]+)">([^<]+)</span>', html)
    assert dict(colors[:2]) == {block_color(0): "alpha beta", block_color(1): "gamma delta"}
    assert dict(colors[2:]) == {block_color(1): "gamma delta", block_color(0): "alpha beta"}
