from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from copy_spotter import Document, __version__, compare_documents, load_directory
from copy_spotter._export import CSV_FIELDS, export_csv, export_data, export_json, iter_json
from copy_spotter.similarity import Match

from .conftest import PLAGIARISM_DIR, make_document, make_pair, make_results

NAMES = ["a.txt", "b, with comma.txt", "c.txt"]
DOCUMENTS = [make_document(t) for t in ("X y z.", "x Y w v", "q")]
PAIRS = [
    make_pair(0, 1, 57.143, [Match(0, 0, 2)], 66.667, 50.0),
    make_pair(0, 2, 0.0, [], 0.0, 0.0),
    # Blocks out of order on the second side, as the shingle engine can return them.
    make_pair(1, 2, 55.5, [Match(2, 0, 1), Match(0, 3, 1)], 25.0, 70.0),
]


RESULTS = make_results(NAMES, PAIRS, DOCUMENTS)


def test_export_data() -> None:
    data = export_data(RESULTS)
    assert data["version"] == 1
    assert data["copy_spotter_version"] == __version__
    assert (data["engine"], data["score_mode"], data["block_size"]) == ("shingle", "coverage", 2)
    assert data["thresholds"] == [5.0, 10.0, 15.0]
    custom = export_data(RESULTS, thresholds=(1, 2, 3))
    assert custom["thresholds"] == [1, 2, 3]
    assert data["documents"][1] == {"index": 1, "name": "b, with comma.txt", "word_count": 4}
    # Sorted by the higher coverage, highest first.
    assert [(p["index_1"], p["index_2"]) for p in data["pairs"]] == [(1, 2), (0, 1), (0, 2)]
    assert data["pairs"][0] == {
        "document_1": "b, with comma.txt",
        "document_2": "c.txt",
        "index_1": 1,
        "index_2": 2,
        "coverage_1": 25.0,
        "coverage_2": 70.0,
        "ratio": 55.5,
        "matched_words": 2,
        "blocks": [{"start_1": 2, "start_2": 0, "size": 1}, {"start_1": 0, "start_2": 3, "size": 1}],
    }


def test_export_sorted_by_ratio_in_ratio_mode() -> None:
    data = export_data(make_results(NAMES, PAIRS, DOCUMENTS, block_size=3, engine="difflib"), score="ratio")
    assert (data["engine"], data["score_mode"], data["block_size"]) == ("difflib", "ratio", 3)
    assert [p["ratio"] for p in data["pairs"]] == [57.143, 55.5, 0.0]


def test_export_json() -> None:
    text = export_json(RESULTS)
    assert text.endswith("}\n")
    assert json.loads(text) == export_data(RESULTS)


def test_export_csv() -> None:
    text = export_csv(RESULTS)
    assert text.endswith("\r\n")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert tuple(rows[0]) == CSV_FIELDS
    assert len(rows) == 3
    assert rows[0] == {
        "document_1": "b, with comma.txt",
        "document_2": "c.txt",
        "coverage_1": "25.0",
        "coverage_2": "70.0",
        "ratio": "55.5",
        "matched_words": "2",
        "block_count": "2",
    }
    ratio_rows = list(csv.DictReader(io.StringIO(export_csv(RESULTS, score="ratio"))))
    assert [r["ratio"] for r in ratio_rows] == ["57.143", "55.5", "0.0"]


# Names that stress JSON escaping: quotes, a backslash, a line break, non-ASCII, a CSV separator.
ODD_NAMES = ['é "quoted".txt', "back\\slash\nnewline.txt", "日本語, comma.txt"]
EMPTY = make_results(["a.txt", "b.txt"], [], [make_document("a"), make_document("b")])

_QUOTED = 'He wrote "the cat sat on the mat and then it slept all day long" in his notes about the old house.'
_SOURCE = "Every story says the cat sat on the mat and then it slept all day long near the warm fire."
_TEMPLATE = "Name: Student number: Course: Introduction to the history of art."


def _with_features():  # type: ignore[no-untyped-def]
    """Results that use every export field the matching options add: options, roles, exclusions."""
    submissions = [
        Document.from_text(f"Name: Student number: Course: Introduction to the history of art. {_QUOTED}", "s1.txt"),
        Document.from_text(f"Name: Student number: Course: Introduction to the history of art. {_SOURCE}", "s2.txt"),
    ]
    return compare_documents(
        submissions,
        block_size=3,
        normalize=["accents"],
        stopwords=["of"],
        ignore_quotes=True,
        ignore_bibliography=True,
        templates=[Document.from_text(_TEMPLATE, "template.txt")],
        references=[Document.from_text(_SOURCE, "source.txt")],
    )


def _reference_json(results, **options) -> str:  # type: ignore[no-untyped-def]
    """The JSON export as it was written before streaming: one json.dumps of the whole dict."""
    return json.dumps(export_data(results, **options), ensure_ascii=False, indent=2) + "\n"


@pytest.mark.parametrize(
    "results",
    [
        RESULTS,
        make_results(ODD_NAMES, PAIRS, DOCUMENTS),
        EMPTY,
        compare_documents(load_directory(PLAGIARISM_DIR)),
        _with_features(),
    ],
    ids=["small", "odd-names", "no-pairs", "plagiarism-dir", "options-references-exclusions"],
)
@pytest.mark.parametrize("score", ["coverage", "ratio"])
def test_streamed_json_is_byte_identical_to_one_dump(results, score) -> None:  # type: ignore[no-untyped-def]
    reference = _reference_json(results, score=score, thresholds=(1, 2, 3))
    chunks = list(iter_json(results, score=score, thresholds=(1, 2, 3)))
    assert "".join(chunks) == reference
    assert export_json(results, score=score, thresholds=(1, 2, 3)) == reference
    assert len(chunks) == (len(results.pairs) + 2 if results.pairs else 1)  # header, one chunk per pair, end


def test_write_json_and_write_csv_match_the_strings(tmp_path: Path) -> None:
    results = make_results(ODD_NAMES, PAIRS, DOCUMENTS)
    json_path = results.write_json(tmp_path / "pairs.json", score="ratio", thresholds=(1, 2, 3))
    csv_path = results.write_csv(str(tmp_path / "pairs.csv"), score="ratio")
    assert json_path == tmp_path / "pairs.json"
    assert csv_path == tmp_path / "pairs.csv"
    # Text mode: compare as text so that Windows line endings in the JSON file do not matter.
    assert json_path.read_text(encoding="utf-8") == results.to_json(score="ratio", thresholds=(1, 2, 3))
    assert csv_path.read_bytes() == results.to_csv(score="ratio").encode("utf-8")


def test_write_json_and_write_csv_check_their_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="thresholds"):
        RESULTS.write_json(tmp_path / "pairs.json", thresholds=(3, 2, 1))
    with pytest.raises(ValueError, match="score"):
        RESULTS.write_csv(tmp_path / "pairs.csv", score="best")  # type: ignore[arg-type]
    assert not list(tmp_path.iterdir())


def test_streamed_exports_carry_the_option_fields(tmp_path: Path) -> None:
    results = _with_features()
    data = json.loads("".join(iter_json(results)))
    assert set(data["options"]) >= {"normalize", "stopwords", "ignore_quotes", "templates", "references"}
    assert [d["role"] for d in data["documents"]] == ["submission", "submission", "reference"]
    assert any(d["excluded"] for d in data["documents"])
    path = results.write_csv(tmp_path / "pairs.csv")
    assert path.read_bytes() == results.to_csv().encode("utf-8")
    assert path.read_text(encoding="utf-8").splitlines()[0].endswith(",role_1,role_2")
