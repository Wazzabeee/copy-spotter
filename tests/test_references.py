from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import pytest

from copy_spotter import Document, Progress, compare_documents
from copy_spotter._compare import compare_pair
from copy_spotter.cli import main, parse_args

SOURCE = "The industrial revolution changed the way people lived and worked in the growing cities of Europe."
ESSAYS = [
    "In my view the industrial revolution changed the way people lived and worked, mostly for the worse.",
    "Factories brought long hours, and the industrial revolution changed the way people lived and worked.",
    "Railways connected markets and made travel faster for merchants and families alike.",
]
OTHER_SOURCE = "Railways connected markets across the continent during the nineteenth century."


def _docs(texts: list[str], prefix: str) -> list[Document]:
    return [Document.from_text(text, f"{prefix}{k}.txt") for k, text in enumerate(texts)]


def _results(**kwargs: Any) -> Any:
    return compare_documents(_docs(ESSAYS, "essay"), references=_docs([SOURCE, OTHER_SOURCE], "ref"), **kwargs)


def test_pairs_with_references() -> None:
    results = _results()
    assert [d.name for d in results.documents] == ["essay0.txt", "essay1.txt", "essay2.txt", "ref0.txt", "ref1.txt"]
    assert results.references == (3, 4)
    assert [results.is_reference(k) for k in range(5)] == [False, False, False, True, True]
    # Submissions among themselves, then each submission with each reference; never reference with reference.
    assert [(p.i, p.j) for p in results.pairs] == [
        (0, 1),
        (0, 2),
        (0, 3),
        (0, 4),
        (1, 2),
        (1, 3),
        (1, 4),
        (2, 3),
        (2, 4),
    ]
    assert results.options == {"references": 2}
    pair = results.pair("essay0.txt", "ref0.txt")
    assert pair.matched_words == 10


@pytest.mark.parametrize("engine", ["shingle", "difflib"])
def test_selected_pairs_match_compare_pair(engine: str) -> None:
    results = _results(engine=engine)
    for pair in results.pairs:
        words_i, words_j = list(results.documents[pair.i].words), list(results.documents[pair.j].words)
        assert pair == compare_pair(pair.i, pair.j, words_i, words_j, block_size=2, engine=engine)  # type: ignore[arg-type]


def test_reference_only() -> None:
    results = _results(compare_submissions=False)
    assert [(p.i, p.j) for p in results.pairs] == [(0, 3), (0, 4), (1, 3), (1, 4), (2, 3), (2, 4)]
    assert results.options == {"references": 2, "compare_submissions": False}
    with pytest.raises(ValueError, match="compare_submissions"):
        _results(compare_submissions=False, ignore_common=50)


def test_reference_names_must_be_unique() -> None:
    with pytest.raises(ValueError, match=r"essay0\.txt"):
        compare_documents(_docs(ESSAYS, "essay"), references=_docs([SOURCE], "essay"))


def test_progress_counts_selected_pairs() -> None:
    events: list[Progress] = []
    _results(compare_submissions=False, progress=events.append)
    assert [(e.done, e.total) for e in events] == [(k, 6) for k in range(7)]


def test_no_references_is_unchanged() -> None:
    documents = _docs(ESSAYS, "essay")
    results = compare_documents(documents)
    assert results.references == () and "references" not in results.options
    data = results.to_dict()
    assert all("role" not in d for d in data["documents"])
    assert next(csv.reader(io.StringIO(results.to_csv())))[-1] == "block_count"


def test_ignore_common_counts_submissions_only() -> None:
    shared = "please submit this assignment through the course portal before friday"
    essays = _docs([f"{shared} one", f"{shared} two", "something else entirely different"], "e")
    # Without the references, 2 of 3 documents is not more than 70%; references must not tip the count.
    references = _docs([f"{shared} source"] * 1 + [f"{shared} again"], "r")
    results = compare_documents(essays, references=references, ignore_common=70)
    assert results.excluded == ()


# Exports and reports -------------------------------------------------------------------------------------------


def test_json_and_csv_roles() -> None:
    results = _results()
    data = results.to_dict()
    assert [d["role"] for d in data["documents"]] == ["submission"] * 3 + ["reference"] * 2
    assert data["options"] == {"references": 2}
    rows = list(csv.DictReader(io.StringIO(results.to_csv())))
    assert len(rows) == 9
    mixed = [row for row in rows if row["document_2"].startswith("ref")]
    assert all((row["role_1"], row["role_2"]) == ("submission", "reference") for row in mixed)


def _embedded(html: str) -> dict[str, Any]:
    match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.DOTALL)
    assert match is not None
    data = json.loads(match.group(1))
    assert isinstance(data, dict)
    return data


def test_single_page_marks_references() -> None:
    html = _results().to_html()
    data = _embedded(html)
    assert [d.get("reference", False) for d in data["documents"]] == [False, False, False, True, True]
    assert "markReferences" in html
    assert "compared with 2 reference sources" in html


def test_pages_report_marks_references_and_skips_reference_pairs() -> None:
    pages = _results().to_html_pages()
    assert len(pages) == 10  # summary + 9 pairs
    summary = pages["_results.html"]
    assert summary.count('class="reference"') == 2 + 2 + 6  # matrix header, matrix rows, pair rows
    assert "3_4.html" not in summary
    assert 'class="reference"' in pages["0_3.html"]
    assert 'class="reference"' not in pages["0_1.html"]


# Command line --------------------------------------------------------------------------------------------------


def test_cli_parsing() -> None:
    args = parse_args(["docs", "--reference", "sources", "--reference", "article.pdf", "--reference-only"])
    assert args.reference == [Path("sources"), Path("article.pdf")]
    assert args.reference_only
    defaults = parse_args(["docs"])
    assert (defaults.reference, defaults.reference_only) == ([], False)


def _write(folder: Path, texts: list[str], prefix: str) -> None:
    folder.mkdir(parents=True)
    for k, text in enumerate(texts):
        (folder / f"{prefix}{k}.txt").write_text(text, encoding="utf-8")


def test_cli_run(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    _write(docs, ESSAYS[:1], "essay")
    _write(docs / "sources", [SOURCE], "web")  # inside the input folder: a reference, not a submission
    (tmp_path / "article.txt").write_text(OTHER_SOURCE, encoding="utf-8")
    json_path = tmp_path / "pairs.json"
    argv = [str(docs), "-r", "-o", str(tmp_path / "out"), "--json", str(json_path), "--no-open"]
    # One submission is enough with references.
    assert main([*argv, "--reference", str(docs / "sources"), "--reference", str(tmp_path / "article.txt")]) == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert [(d["name"], d["role"]) for d in data["documents"]] == [
        ("essay0.txt", "submission"),
        ("sources/web0.txt", "reference"),
        ("article.txt", "reference"),
    ]
    assert len(data["pairs"]) == 2


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--reference-only"], "needs at least one --reference"),
        (["--reference", "{same}"], "different names"),
        (["--reference", "{refs}", "--reference-only", "--ignore-common", "50"], "--ignore-common"),
        (["--reference", "{empty}"], "No readable reference"),
    ],
)
def test_cli_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str) -> None:
    docs = tmp_path / "docs"
    _write(docs, ESSAYS, "essay")
    _write(tmp_path / "refs", [SOURCE], "ref")
    (tmp_path / "empty").mkdir()
    (tmp_path / "essay0.txt").write_text(SOURCE, encoding="utf-8")
    paths = {"same": tmp_path / "essay0.txt", "refs": tmp_path / "refs", "empty": tmp_path / "empty"}
    extra = [arg.format(**{k: str(v) for k, v in paths.items()}) for arg in extra]
    assert main([str(docs), "-o", str(tmp_path / "out"), "--no-open", *extra]) == 1
    assert message in capsys.readouterr().err
