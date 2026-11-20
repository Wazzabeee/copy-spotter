from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from copy_spotter import compare_documents, load_directory
from copy_spotter._compare import Pair
from copy_spotter._documents import Document
from copy_spotter._report import RESULTS_FILENAME, _render, _template
from copy_spotter._single_page import iter_single, render_single, report_data, script_json
from copy_spotter.similarity import Match, compare, coverage

from .conftest import PLAGIARISM_DIR, make_document, make_pair, make_results

_DATA_RE = re.compile(r'<script type="application/json" id="report-data">(.*?)</script>', re.DOTALL)


def _doc(text: str) -> Document:
    return make_document(text)


def _embedded(html: str) -> dict[str, object]:
    match = _DATA_RE.search(html)
    assert match is not None
    data = json.loads(match.group(1))
    assert isinstance(data, dict)
    return data


def _pair(doc1: Document, doc2: Document) -> Pair:
    score, blocks = compare(doc1.words, doc2.words, 2)
    return make_pair(0, 1, score, blocks, *coverage(blocks, len(doc1.words), len(doc2.words)))


def test_report_data_shape() -> None:
    doc1 = _doc("The Quick brown fox, jumps.")
    doc2 = _doc("A quick BROWN fox sleeps")
    pair = _pair(doc1, doc2)
    data = report_data(make_results(["a.txt", "b.txt"], [pair], [doc1, doc2]), "meta line")
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
                "ratio": pair.ratio,
                "coverage_i": pair.coverage_i,
                "coverage_j": pair.coverage_j,
                "blocks": [[1, 1, 3]],
            }
        ],
    }
    # The original text, with case and punctuation, is embedded and the spans point at its words.
    assert doc1.text[slice(*data["documents"][0]["spans"][1])] == "Quick"
    assert report_data(make_results(["a", "b"], [pair], [doc1, doc2]), score="ratio")["score_mode"] == "ratio"


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
    pairs = [make_pair(0, 1, 12.5, [], 10.0, 15.0)]
    html = render_single(make_results(names, pairs, documents), meta=hostile)
    # Only the template's own two script elements are closed.
    assert html.count("</script>") == 2
    assert "<script>alert" not in html
    assert "<!--" not in html
    assert _embedded(html) == report_data(make_results(names, pairs, documents), hostile)


def test_page_is_self_contained() -> None:
    html = render_single(make_results(["a", "b"], [make_pair(0, 1, 0.0, [], 0.0, 0.0)]))
    for external in ("http://", "https://", "src=", "<link", "@import"):
        assert external not in html


def test_page_has_filters_matrix_and_comparison_view() -> None:
    html = render_single(make_results(["a", "b"], [make_pair(0, 1, 0.0, [], 0.0, 0.0)]))
    for element_id in ("min-score", "name-filter", "pairs", "matrix", "comparison", "left", "right"):
        assert f'id="{element_id}"' in html


def test_save_single_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    pairs = [make_pair(0, 1, 42.0, [], 40.0, 45.0)]
    path = make_results(["a", "b"], pairs).save(out_dir, score="ratio")
    assert path == out_dir / RESULTS_FILENAME
    assert [p.name for p in out_dir.iterdir()] == [RESULTS_FILENAME]
    assert _embedded(path.read_text(encoding="utf-8"))["score_mode"] == "ratio"


def test_thresholds_are_embedded() -> None:
    pairs = [make_pair(0, 1, 0.0, [], 0.0, 0.0)]
    html = render_single(make_results(["a", "b"], pairs, [_doc("x"), _doc("y")]), thresholds=(1, 2, 3))
    assert _embedded(html)["thresholds"] == [1, 2, 3]


def _reference_page(results, meta, **options):  # type: ignore[no-untyped-def]
    """The page as it was rendered before streaming: one script_json of the whole data, put in the template."""
    data = report_data(results, meta, **options)
    uses_addon = any("excluded" in document or "reference" in document for document in data["documents"])
    addon = _template("single_addon.html") if uses_addon else ""
    return _render(_template("single.html"), data=script_json(data), addon=addon)


def _with_features():  # type: ignore[no-untyped-def]
    """Results with excluded passages (quotes, template) and a reference source: the page embeds the add-on."""
    head = "Name: Student number: Course: Introduction to the history of art. "
    source = "Every story says the cat sat on the mat and then it slept all day long near the warm fire."
    submissions = [
        Document.from_text(head + 'He wrote "the cat sat on the mat and then it slept all day long" today.', "s1.txt"),
        Document.from_text(head + source, "s2.txt"),
    ]
    return compare_documents(
        submissions,
        block_size=3,
        ignore_quotes=True,
        templates=[Document.from_text(head, "template.txt")],
        references=[Document.from_text(source, "source.txt")],
    )


HOSTILE_DOCUMENTS = [
    make_document('Ünïcode "quotes" & <b>tags</b>\nnew line\ttab </script>', "a</script>.txt"),
    make_document("plain text with the same words: tags new line", "b & c.txt"),
    make_document("", "empty.txt"),
]


@pytest.mark.parametrize(
    "results",
    [
        make_results(
            [d.name for d in HOSTILE_DOCUMENTS],
            [
                make_pair(0, 1, 40.0, [Match(4, 6, 2), Match(1, 0, 1)], 12.5, 22.2),
                make_pair(0, 2, 0.0, [], 0.0, 0.0),
                make_pair(1, 2, 0.0, [], 0.0, 0.0),
            ],
            HOSTILE_DOCUMENTS,
        ),
        make_results(["a.txt", "b.txt"], [], [make_document("a"), make_document("b")]),
        make_results([], []),
        compare_documents(load_directory(PLAGIARISM_DIR)),
        _with_features(),
    ],
    ids=["hostile-text", "no-pairs", "no-documents", "plagiarism-dir", "exclusions-references"],
)
@pytest.mark.parametrize("score", ["coverage", "ratio"])
def test_streamed_page_is_byte_identical_to_one_render(results, score) -> None:  # type: ignore[no-untyped-def]
    meta = "meta </script> & <!-- é"
    reference = _reference_page(results, meta, score=score, thresholds=(1, 2, 3))
    chunks = list(iter_single(results, meta, score=score, thresholds=(1, 2, 3)))
    assert "".join(chunks) == reference
    assert render_single(results, meta, score=score, thresholds=(1, 2, 3)) == reference
    # Template pieces around the two placeholders, the add-on, the data head, documents, "],pairs:[", pairs, "]}".
    assert len(chunks) == len(results.documents) + len(results.pairs) + 7


def test_streamed_page_embeds_the_addon_only_when_needed() -> None:
    addon = _template("single_addon.html")
    assert addon in render_single(_with_features())
    assert addon not in render_single(compare_documents(load_directory(PLAGIARISM_DIR)))


def test_save_streams_the_same_page_as_to_html(tmp_path: Path) -> None:
    results = compare_documents(load_directory(PLAGIARISM_DIR))
    path = results.save(tmp_path / "out", score="ratio", thresholds=(1, 2, 3), meta="run")
    assert path == tmp_path / "out" / RESULTS_FILENAME
    assert path.read_text(encoding="utf-8") == results.to_html(score="ratio", thresholds=(1, 2, 3), meta="run")


def test_save_checks_its_options_before_writing(tmp_path: Path) -> None:
    results = make_results(["a", "b"], [make_pair(0, 1, 0.0, [], 0.0, 0.0)])
    with pytest.raises(ValueError, match="thresholds"):
        results.save(tmp_path / "out", thresholds=(3, 2, 1))
    assert not (tmp_path / "out").exists()
