"""Golden-file regression tests: the CLI outputs must stay byte for byte what they are today.

Each case runs ``copy-spotter`` through its entry point (``copy_spotter.cli.main``) on the committed documents
in ``tests/golden/inputs`` and compares every file it writes (the HTML report, the ``--json`` and ``--csv``
exports) with ``tests/golden/<case>/``. Only the CLI and its output files are used, so internal refactors and
faster engines are free to change anything else, as long as the outputs do not move.

Before comparing, the copy-spotter version (which hatch-vcs changes on every commit) is replaced with
``<VERSION>`` and the temporary output path with ``<TMP>``. HTML and JSON are compared after mapping ``\\r\\n``
to ``\\n`` (they are written in text mode, so Windows writes CRLF); the CSV is compared as exact bytes (the csv
module always writes CRLF).

After an intended output change, regenerate the goldens and review the diff before committing::

    COPY_SPOTTER_UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py

PDF files are left out of the goldens: their text comes from pdfminer, whose upgrades may move a space or a
line break. ``test_pdf_extraction_is_well_formed`` checks their structure instead.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from copy_spotter import __version__
from copy_spotter.cli import main

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
INPUTS_DIR = GOLDEN_DIR / "inputs"
PLAGIARISM_DIR = Path(__file__).resolve().parent.parent / "data" / "pdf" / "plagiarism"
UPDATE = os.environ.get("COPY_SPOTTER_UPDATE_GOLDEN") == "1"

JSON_NAME, CSV_NAME = "pairs.json", "pairs.csv"

CASES: dict[str, list[str]] = {
    f"{report}-{score}-{engine}": ["--report", report, "--score", score, "--engine", engine]
    for report in ("single", "pages")
    for score in ("coverage", "ratio")
    for engine in ("shingle", "difflib")
}
CASES["single-block5-thresholds"] = ["--report", "single", "-s", "5", "--thresholds", "20,40,60"]
CASES["pages-block5-thresholds"] = ["--report", "pages", "-s", "5", "--thresholds", "20,40,60"]


def _normalize(data: bytes, tmp: Path) -> bytes:
    text = data.decode("utf-8")
    for path in (str(tmp), tmp.as_posix(), json.dumps(str(tmp))[1:-1]):
        text = text.replace(path, "<TMP>")
    text = text.replace(f"copy-spotter {__version__}", "copy-spotter <VERSION>")
    text = text.replace(f'"copy_spotter_version": "{__version__}"', '"copy_spotter_version": "<VERSION>"')
    return text.encode("utf-8")


def _comparable(name: str, data: bytes) -> bytes:
    return data if name.endswith(".csv") else data.replace(b"\r\n", b"\n")


def _run(args: list[str], tmp_path: Path) -> dict[str, bytes]:
    """Run the CLI on the golden inputs and return ``{file name: normalized bytes}`` of everything it wrote."""
    out_dir = tmp_path / "out"
    exports = tmp_path / "exports"
    argv = [
        str(INPUTS_DIR),
        "-o",
        str(out_dir),
        "--json",
        str(exports / JSON_NAME),
        "--csv",
        str(exports / CSV_NAME),
        "--no-open",
        *args,
    ]
    assert main(argv) == 0
    files = [*out_dir.iterdir(), *exports.iterdir()]
    assert all(path.is_file() for path in files)
    return {path.name: _normalize(path.read_bytes(), tmp_path) for path in files}


@pytest.mark.parametrize("case", sorted(CASES))
def test_golden_outputs(case: str, tmp_path: Path) -> None:
    actual = _run(CASES[case], tmp_path)
    expected_dir = GOLDEN_DIR / case
    if UPDATE:
        shutil.rmtree(expected_dir, ignore_errors=True)
        expected_dir.mkdir(parents=True)
        for name, data in actual.items():
            (expected_dir / name).write_bytes(_comparable(name, data))
        return
    assert expected_dir.is_dir(), f"missing goldens for {case}: run with COPY_SPOTTER_UPDATE_GOLDEN=1"
    expected = {path.name: path.read_bytes() for path in expected_dir.iterdir()}
    assert sorted(actual) == sorted(expected)
    for name in sorted(expected):
        assert _comparable(name, actual[name]) == _comparable(name, expected[name]), f"{case}/{name} changed"


def test_goldens_have_no_machine_specific_values() -> None:
    for path in GOLDEN_DIR.rglob("*"):
        if path.is_file() and path.parent != INPUTS_DIR:
            text = path.read_text(encoding="utf-8")
            if path.name in ("_results.html", JSON_NAME):  # the files that print the version
                assert "copy-spotter <VERSION>" in text or '"copy_spotter_version": "<VERSION>"' in text
            assert str(GOLDEN_DIR) not in text
            assert "<TMP>" not in text  # outputs only hold document names, never paths


def _embedded(html: str) -> dict[str, Any]:
    match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.DOTALL)
    assert match is not None
    data = json.loads(match.group(1))
    assert isinstance(data, dict)
    return data


@pytest.mark.parametrize("pdf", sorted(PLAGIARISM_DIR.glob("*.pdf")), ids=lambda path: path.name)
def test_pdf_extraction_is_well_formed(pdf: Path, tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    shutil.copy(pdf, in_dir / pdf.name)
    shutil.copy(INPUTS_DIR / "short.txt", in_dir / "short.txt")
    out_dir, json_path = tmp_path / "out", tmp_path / "pairs.json"
    assert main([str(in_dir), "-o", str(out_dir), "--json", str(json_path), "--no-open"]) == 0

    exported = json.loads(json_path.read_text(encoding="utf-8"))
    counts = {doc["name"]: doc["word_count"] for doc in exported["documents"]}
    assert counts[pdf.name] > 0  # an unreadable PDF would be skipped with a warning only

    data = _embedded((out_dir / "_results.html").read_text(encoding="utf-8"))
    (document,) = [doc for doc in data["documents"] if doc["name"] == pdf.name]
    text, spans = document["text"], document["spans"]
    assert text.strip()
    assert len(spans) == counts[pdf.name]
    previous_end = 0
    for start, end in spans:
        assert previous_end <= start < end <= len(text)
        assert re.fullmatch(r"\w+", text[start:end])
        previous_end = end
