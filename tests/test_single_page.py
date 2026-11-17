from __future__ import annotations

import json
import re
from pathlib import Path

from copy_spotter.extract import Document, tokenize_with_offsets
from copy_spotter.report import RESULTS_FILENAME, PairResult
from copy_spotter.similarity import compare, coverage
from copy_spotter.single_page import render_single, report_data, script_json, write_single_report

_DATA_RE = re.compile(r'<script type="application/json" id="report-data">(.*?)</script>', re.DOTALL)


def _doc(text: str) -> Document:
    return tokenize_with_offsets(text)


def _embedded(html: str) -> dict[str, object]:
    match = _DATA_RE.search(html)
    assert match is not None
    data = json.loads(match.group(1))
    assert isinstance(data, dict)
    return data


def _pair(doc1: Document, doc2: Document) -> PairResult:
    score, blocks = compare(doc1.words, doc2.words, 2)
    return PairResult(0, 1, score, blocks, *coverage(blocks, len(doc1.words), len(doc2.words)))


def test_report_data_shape() -> None:
    doc1 = _doc("The Quick brown fox, jumps.")
    doc2 = _doc("A quick BROWN fox sleeps")
    pair = _pair(doc1, doc2)
    data = report_data(["a.txt", "b.txt"], [doc1, doc2], [pair], "meta line")
    assert data == {
        "version": 1,
        "meta": "meta line",
        "score_mode": "coverage",
        "thresholds": [5.0, 10.0, 15.0],
        "documents": [
            {"name": "a.txt", "text": doc1.text, "spans": [[0, 3], [4, 9], [10, 15], [16, 19], [21, 26]]},
            {"name": "b.txt", "text": doc2.text, "spans": [list(s) for s in doc2.spans]},
        ],
        "pairs": [
            {
                "i": 0,
                "j": 1,
                "ratio": pair.score,
                "coverage_i": pair.coverage_i,
                "coverage_j": pair.coverage_j,
                "blocks": [[1, 1, 3]],
            }
        ],
    }
    # The original text, with case and punctuation, is embedded and the spans point at its words.
    assert doc1.text[slice(*data["documents"][0]["spans"][1])] == "Quick"
    assert report_data(["a", "b"], [doc1, doc2], [pair], score_mode="ratio")["score_mode"] == "ratio"


def test_script_json_cannot_close_the_script() -> None:
    text = script_json({"x": "</script><script>alert(1)</script> & <!--"})
    assert "<" not in text
    assert ">" not in text
    assert "&" not in text
    assert json.loads(text) == {"x": "</script><script>alert(1)</script> & <!--"}


def test_document_text_and_names_are_escaped() -> None:
    hostile = "</script><script>alert(1)</script>"
    names = [f"{hostile}.txt", "b & <c>.txt"]
    documents = [_doc(f"{hostile} {{{{data}}}}"), _doc("x <!-- y")]
    pairs = [PairResult(0, 1, 12.5, [], 10.0, 15.0)]
    html = render_single(names, documents, pairs, meta=hostile)
    # Only the template's own two script elements are closed.
    assert html.count("</script>") == 2
    assert "<script>alert" not in html
    assert "<!--" not in html
    assert _embedded(html) == report_data(names, documents, pairs, hostile)


def test_page_is_self_contained() -> None:
    html = render_single(["a", "b"], [_doc("x"), _doc("y")], [PairResult(0, 1, 0.0, [], 0.0, 0.0)])
    for external in ("http://", "https://", "src=", "<link", "@import"):
        assert external not in html


def test_page_has_filters_matrix_and_comparison_view() -> None:
    html = render_single(["a", "b"], [_doc("x"), _doc("y")], [PairResult(0, 1, 0.0, [], 0.0, 0.0)])
    for element_id in ("min-score", "name-filter", "pairs", "matrix", "comparison", "left", "right"):
        assert f'id="{element_id}"' in html


def test_write_single_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    pairs = [PairResult(0, 1, 42.0, [], 40.0, 45.0)]
    path = write_single_report(out_dir, ["a", "b"], [_doc("x"), _doc("y")], pairs, score_mode="ratio")
    assert path == out_dir / RESULTS_FILENAME
    assert [p.name for p in out_dir.iterdir()] == [RESULTS_FILENAME]
    assert _embedded(path.read_text(encoding="utf-8"))["score_mode"] == "ratio"


def test_thresholds_are_embedded() -> None:
    pairs = [PairResult(0, 1, 0.0, [], 0.0, 0.0)]
    html = render_single(["a", "b"], [_doc("x"), _doc("y")], pairs, thresholds=(1, 2, 3))
    assert _embedded(html)["thresholds"] == [1, 2, 3]
