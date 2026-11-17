from __future__ import annotations

import csv
import io
import json

from copy_spotter import __version__
from copy_spotter._export import CSV_FIELDS, export_csv, export_data, export_json
from copy_spotter.similarity import Match

from .conftest import make_document, make_pair, make_results

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
