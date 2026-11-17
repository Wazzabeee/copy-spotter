from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from copy_spotter.extract import Document, tokenize_with_offsets
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
    return re.findall(r'<span class="match"[^>]*>(.*?)</span>', html, re.DOTALL)


def _doc(text: str) -> Document:
    return tokenize_with_offsets(text)


def test_highlight_wraps_only_the_matched_words() -> None:
    html = highlight(_doc("a b c d e"), [(1, 2, 0)])
    assert _highlighted(html) == ["b c"]
    assert html.startswith("a <span")
    assert html.endswith("</span> d e")


def test_highlight_keeps_case_and_punctuation() -> None:
    text = "Hello, World! The Cat sat; on the mat."
    html = highlight(_doc(text), [(2, 3, 0)])
    assert _highlighted(html) == ["The Cat sat"]
    assert unescape(re.sub(r"<[^>]+>", "", html)) == text


def test_highlight_keeps_paragraph_breaks() -> None:
    text = "First paragraph ends.\n\nSecond one\nstarts here."
    html = highlight(_doc(text), [(2, 3, 0)])
    assert _highlighted(html) == ["ends.\n\nSecond one"]
    assert unescape(re.sub(r"<[^>]+>", "", html)) == text


def test_highlighted_text_is_an_exact_slice_of_the_original() -> None:
    text = 'AI & Healthcare: <b>Machine</b> learning, "deep" learning.\n\nMachine-learning works.'
    document = _doc(text)
    html = highlight(document, [(1, 4, 0), (8, 2, 1)])
    highlighted = [unescape(h) for h in _highlighted(html)]
    assert highlighted == ["Healthcare: <b>Machine</b", "Machine-learning"]
    assert all(h in text for h in highlighted)


def test_highlight_handles_unsorted_and_overlapping_spans() -> None:
    document = _doc("one two three four five six seven")
    html = highlight(document, [(4, 2, 1), (0, 2, 0), (1, 2, 2), (5, 1, 3)])
    assert _highlighted(html) == ["one two", "three", "five six"]
    assert block_color(2) in html and block_color(3) not in html
    assert unescape(re.sub(r"<[^>]+>", "", html)) == document.text


def test_highlight_respects_word_boundaries() -> None:
    # "le chat" used to be highlighted inside "le chaton" because blocks were searched as substrings.
    doc1 = _doc("x le chat y")
    doc2 = _doc("le chaton z le chat w")
    score, blocks = compare(doc1.words, doc2.words, 2)
    pair = PairResult(0, 1, score, blocks, *coverage(blocks, len(doc1.words), len(doc2.words)))
    html = render_comparison(("a", "b"), (doc1, doc2), pair)
    assert html.count('class="match"') == 2  # once per side
    assert "chaton" not in "".join(_highlighted(html))


def test_text_is_escaped() -> None:
    html = highlight(_doc("<script>alert('x') & co</script>"), [(0, 2, 0)])
    assert "<script>" not in html
    assert "&lt;/script&gt;" in html
    assert "&amp; co" in html
    assert unescape(_highlighted(html)[0]) == "script>alert"


def test_placeholders_in_document_text_are_not_expanded() -> None:
    pair = PairResult(0, 1, 50.0, [], 50.0, 50.0)
    html = render_comparison(("a", "b"), (_doc("{{right}} text"), _doc("other")), pair)
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
    results = write_report(out_dir, ["a", "b"], [_doc("x"), _doc("y")], pairs)
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
    page = render_comparison(("a", "b"), (_doc("x"), _doc("y")), pairs[0], score_mode="ratio")
    assert "Similarity:" in page
    assert ">18.182%<" in page
    assert "100" not in page


def test_comparison_page_shows_both_directions() -> None:
    pair = PairResult(0, 1, 18.182, [], 100.0, 10.0)
    page = render_comparison(("short.txt", "long.txt"), (_doc("x"), _doc("y")), pair)
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
    doc1 = _doc("Alpha beta, gamma delta.")
    doc2 = _doc("Gamma delta! Alpha beta?")
    pair = PairResult(0, 1, 100.0, [Match(0, 2, 2), Match(2, 0, 2)], 100.0, 100.0)
    html = render_comparison(("a", "b"), (doc1, doc2), pair)
    assert _highlighted(html) == ["Alpha beta", "gamma delta", "Gamma delta", "Alpha beta"]
    # Each block keeps its color on both sides.
    colors = re.findall(r'style="color: (hsl[^"]+)">([^<]+)</span>', html)
    assert dict(colors[:2]) == {block_color(0): "Alpha beta", block_color(1): "gamma delta"}
    assert dict(colors[2:]) == {block_color(1): "Gamma delta", block_color(0): "Alpha beta"}


def test_shingle_engine_blocks_render_on_original_text() -> None:
    # The shingle engine finds moved passages, so its blocks are out of order on the B side.
    doc1 = _doc("First, the cat sat on the mat.\n\nThen the dog ran in the park!")
    doc2 = _doc("Then the Dog ran in the park.\n\nFirst, the Cat sat on the mat?")
    score, blocks = compare(doc1.words, doc2.words, 3, "shingle")
    assert [m.b for m in blocks] != sorted(m.b for m in blocks)
    pair = PairResult(0, 1, score, blocks, *coverage(blocks, len(doc1.words), len(doc2.words)))
    html = render_comparison(("a", "b"), (doc1, doc2), pair)
    left, right = html.split('id="rightContent"')
    assert [unescape(h) for h in _highlighted(left)] == [
        "First, the cat sat on the mat",
        "Then the dog ran in the park",
    ]
    assert [unescape(h) for h in _highlighted(right)] == [
        "Then the Dog ran in the park",
        "First, the Cat sat on the mat",
    ]
    assert unescape(re.sub(r"<[^>]+>", "", right.split("</h3>", 1)[1])).startswith(doc2.text)


def test_score_style_thresholds() -> None:
    assert score_style(5) == "color: green"
    assert score_style(5.1) == "color: #b38f00"
    assert score_style(15.1) == "color: #990033; font-weight: bold"
    assert score_style(30, (40, 50, 60)) == "color: green"
    assert score_style(55, (40, 50, 60)) == "color: #cc5200"


def test_results_and_comparison_use_thresholds() -> None:
    pair = PairResult(0, 1, 30.0, [], 30.0, 30.0)
    assert "#990033" in render_results(["a", "b"], [pair], thresholds=(10, 20, 25))
    assert "#990033" not in render_results(["a", "b"], [pair], thresholds=(40, 50, 60))
    page = render_comparison(("a", "b"), (_doc("x"), _doc("y")), pair, thresholds=(40, 50, 60))
    assert "#990033" not in page
    assert "color: green" in page
