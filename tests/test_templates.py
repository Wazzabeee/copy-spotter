from __future__ import annotations

import json
from pathlib import Path

import pytest

from copy_spotter import Document, Progress, compare_documents
from copy_spotter._exclusions import TEMPLATE_MIN_WORDS, Excluded, common_runs, template_runs
from copy_spotter.cli import main, parse_args

PROMPT = "Explain in your own words how the industrial revolution changed the daily life of workers in cities."
ANSWERS = [
    "How the industrial revolution changed the daily life of workers in cities: factories set the pace of every day.",
    "How the industrial revolution changed the daily life of workers in cities is a vast question about wages.",
    "Children worked long hours in mills and mines, and housing near the factories was crowded and unhealthy.",
]


def _docs(*texts: str) -> list[Document]:
    return [Document.from_text(text, f"{k}.txt") for k, text in enumerate(texts)]


# Templates -----------------------------------------------------------------------------------------------------


def test_template_runs() -> None:
    words = [Document.from_text(text, "x").words for text in ANSWERS]
    runs = template_runs(words, [Document.from_text(PROMPT, "prompt").words])
    assert runs[0] == [(0, 12)] and runs[1] == [(0, 12)] and runs[2] == []
    assert template_runs(words, []) == [[], [], []]


def test_short_template_phrases_are_kept() -> None:
    assert TEMPLATE_MIN_WORDS == 4
    words = [Document.from_text("one of the best", "x").words, Document.from_text("it is one of us", "y").words]
    template = Document.from_text("this is one of the questions", "t").words
    assert template_runs(words, [template]) == [[], []]  # "one of the" is only three words


def test_templates_drop_shared_prompt_text() -> None:
    documents = _docs(*ANSWERS[:2])
    plain = compare_documents(documents).pairs[0]
    assert plain.matched_words >= 12
    results = compare_documents(documents, templates=[Document.from_text(PROMPT, "prompt.txt")])
    pair = results.pairs[0]
    assert pair.matched_words < plain.matched_words - 10
    assert results.excluded[0] == (Excluded(0, 12, "template"),)
    assert results.options == {"templates": ["prompt.txt"]}
    assert len(results.documents) == 2  # templates are not compared


def test_templates_are_normalized_like_the_documents() -> None:
    documents = _docs("Décrivez la révolution industrielle en France au dix-neuvième siècle", "autre texte")
    template = Document.from_text("decrivez la revolution industrielle en france", "consigne.txt")
    assert compare_documents(documents, templates=[template]).excluded[0] == ()
    results = compare_documents(documents, templates=[template], normalize=["accents"])
    assert results.excluded[0] == (Excluded(0, 6, "template"),)


def test_templates_combine_with_quotes() -> None:
    text = f'{ANSWERS[0]} He said "nothing more to add here"'
    results = compare_documents(
        _docs(text, ANSWERS[1]), templates=[Document.from_text(PROMPT, "p")], ignore_quotes=True
    )
    assert [run.reason for run in results.excluded[0]] == ["template", "quote"]


# Passages common to many documents -----------------------------------------------------------------------------


def test_common_runs() -> None:
    # Three documents of 6 words; words 0-2 shared by all three, word 5 of document 0 shared with document 1 only.
    matches = [(0, 1, [(0, 0, 3), (5, 5, 1)]), (0, 2, [(0, 0, 3)]), (1, 2, [(0, 0, 3)])]
    assert common_runs([6, 6, 6], matches, 3) == [[(0, 3)], [(0, 3)], [(0, 3)]]
    assert common_runs([6, 6, 6], matches, 2) == [[(0, 3), (5, 1)], [(0, 3), (5, 1)], [(0, 3)]]
    assert common_runs([0, 2], [], 3) == [[], []]


SHARED = "please submit this assignment through the course portal before the deadline on friday"


def test_ignore_common_drops_passages_most_documents_share() -> None:
    bodies = [
        "the cat chased a red ball across the garden",
        "rivers carry sediment from mountains down to the sea",
        "the cat chased a red ball across the garden",
        "volcanoes erupt when pressure builds under the crust",
    ]
    documents = _docs(*(f"{SHARED}. {body}" for body in bodies))
    plain = compare_documents(documents)
    results = compare_documents(documents, ignore_common=50)
    assert results.options == {"ignore_common": 50}
    for runs in results.excluded:
        assert [(run.start, run.size, run.reason) for run in runs] == [(0, 13, "common")]
    # The real copy between documents 0 and 2 is still found; the others no longer match at all.
    assert results.pair(0, 2).matched_words == 9
    assert results.pair(0, 1).matched_words == 0 < plain.pair(0, 1).matched_words


def test_ignore_common_needs_three_documents_and_the_threshold() -> None:
    documents = _docs(f"{SHARED} one", f"{SHARED} two")
    results = compare_documents(documents, ignore_common=10)
    assert results.excluded == ()
    assert results.pairs[0].matched_words == 13
    documents = _docs(f"{SHARED} one", f"{SHARED} two", f"{SHARED} three", "unrelated text entirely here", "more")
    assert compare_documents(documents, ignore_common=60).excluded == ()  # 3 of 5 is not more than 60%
    assert compare_documents(documents, ignore_common=50).excluded[0] == (Excluded(0, 13, "common"),)


def test_ignore_common_progress_covers_both_passes() -> None:
    events: list[Progress] = []
    documents = _docs(*(f"{SHARED} {k}" for k in range(3)))
    compare_documents(documents, ignore_common=50, progress=events.append)
    assert [(e.done, e.total) for e in events] == [(k, 6) for k in range(7)]
    events.clear()
    compare_documents(_docs("a b c", "d e f", "g h i"), ignore_common=50, progress=events.append)
    assert (events[0].done, events[-1].done, events[-1].total) == (0, 6, 6)


@pytest.mark.parametrize("value", [0, -5, 101])
def test_invalid_ignore_common(value: float) -> None:
    with pytest.raises(ValueError, match="ignore_common"):
        compare_documents(_docs("a b", "c d"), ignore_common=value)


# Reports and command line --------------------------------------------------------------------------------------


def test_json_and_meta() -> None:
    results = compare_documents(_docs(*ANSWERS), templates=[Document.from_text(PROMPT, "prompt.txt")], ignore_common=50)
    data = results.to_dict()
    assert data["options"] == {"templates": ["prompt.txt"], "ignore_common": 50}
    assert data["documents"][0]["excluded"] == [{"start": 0, "size": 12, "reason": "template"}]
    assert "text of 1 template, passages in more than 50% of the documents ignored" in results.to_html()
    assert "Found in a template" in results.to_html_pages()["0_1.html"]


def test_cli_parsing() -> None:
    args = parse_args(["docs", "--exclude", "prompt.pdf", "--exclude", "templates", "--ignore-common", "40%"])
    assert args.exclude == [Path("prompt.pdf"), Path("templates")]
    assert args.ignore_common == 40.0
    defaults = parse_args(["docs"])
    assert (defaults.exclude, defaults.ignore_common) == ([], None)
    for bad in ("0", "150", "lots"):
        with pytest.raises(SystemExit):
            parse_args(["docs", "--ignore-common", bad])


def test_cli_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    for k, answer in enumerate(ANSWERS):
        (docs / f"{k}.txt").write_text(answer, encoding="utf-8")
    (docs / "prompt.md").write_text(PROMPT, encoding="utf-8")  # inside the input folder: not compared
    more = tmp_path / "templates"
    more.mkdir()
    (more / "rubric.txt").write_text("Grading rubric for the essay on cities and workers.", encoding="utf-8")
    json_path = tmp_path / "pairs.json"
    argv = [str(docs), "-o", str(tmp_path / "out"), "--json", str(json_path), "--no-open"]
    assert main([*argv, "--exclude", str(docs / "prompt.md"), "--exclude", str(more), "--ignore-common", "80"]) == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert [d["name"] for d in data["documents"]] == ["0.txt", "1.txt", "2.txt"]
    assert data["options"] == {"templates": ["prompt.md", "rubric.txt"], "ignore_common": 80}
    assert main([*argv, "--exclude", str(tmp_path / "missing.txt")]) == 1
    assert "Not found" in capsys.readouterr().err
