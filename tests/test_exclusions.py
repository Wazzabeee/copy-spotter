from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from copy_spotter import Document, compare_documents
from copy_spotter._exclusions import (
    Excluded,
    bibliography_start,
    find_exclusions,
    masked_words,
    merge,
    quote_ranges,
    words_in,
)
from copy_spotter._report import highlight
from copy_spotter.cli import main, parse_args

QUOTED = 'As the author wrote, "the industrial revolution changed the way people lived and worked", and so on.'
SOURCE = "Historians agree that the industrial revolution changed the way people lived and worked in cities."


def _quoted(text: str) -> list[str]:
    return [text[a:b] for a, b in quote_ranges(text)]


# Quotations ----------------------------------------------------------------------------------------------------


def test_quote_marks_of_many_languages() -> None:
    assert _quoted('He said "hello there" and left.') == ['"hello there"']
    assert _quoted("He said “hello there” and left.") == ["“hello there”"]
    assert _quoted("Il a dit « bonjour à tous » puis est parti.") == ["« bonjour à tous »"]
    assert _quoted("Er sagte „guten Tag“ und ging.") == ["„guten Tag“"]
    assert _quoted("Er sagte »guten Tag« und ging.") == ["»guten Tag«"]
    assert _quoted("彼は「こんにちは」と言った。") == ["「こんにちは」"]


def test_several_and_nested_quotes() -> None:
    text = '"one" and "two" then “outer “inner” rest” end'
    # The inner closing mark closes the outer quotation: only outermost pairs are tracked.
    assert _quoted(text) == ['"one"', '"two"', "“outer “inner”"]
    assert _quoted("« a “b” c »") == ["« a “b” c »"]


def test_single_quotes_and_apostrophes_are_ignored() -> None:
    assert _quoted("It's the student's 'own' work, l'élève") == []


def test_unclosed_quote_stops_at_the_paragraph_end() -> None:
    text = 'A stray " mark here.\n\nNext paragraph "quoted" text.'
    assert _quoted(text) == ['"quoted"']
    # A quotation may span a single line break (hard-wrapped text).
    assert _quoted('He wrote "first line\nsecond line" here.') == ['"first line\nsecond line"']


def test_words_in_ranges() -> None:
    document = Document.from_text(QUOTED, "a.txt")
    runs = words_in(document.spans, quote_ranges(document.text))
    assert len(runs) == 1
    start, size = runs[0]
    assert document.words[start : start + size] == tuple(
        "the industrial revolution changed the way people lived and worked".split()
    )
    assert words_in(document.spans, [(0, 1)]) == []  # no whole word inside


def test_merge_and_mask() -> None:
    runs = merge([Excluded(5, 3, "bibliography"), Excluded(0, 2, "quote"), Excluded(6, 4, "quote")])
    assert runs == (Excluded(0, 2, "quote"), Excluded(5, 3, "bibliography"), Excluded(8, 2, "quote"))
    masked = masked_words(["a", "b", "c"], 3, [Excluded(1, 1, "quote")])
    assert masked == ["a", "\x003:1", "c"]


def test_ignore_quotes_drops_quoted_matches_but_keeps_scores_honest() -> None:
    documents = [Document.from_text(QUOTED, "essay.txt"), Document.from_text(SOURCE, "source.txt")]
    plain = compare_documents(documents)
    assert plain.pairs[0].matched_words == 10
    results = compare_documents(documents, ignore_quotes=True)
    pair = results.pairs[0]
    assert pair.blocks == () and pair.coverage_i == pair.coverage_j == 0.0
    assert results.options == {"ignore_quotes": True}
    (run,) = results.excluded[0]
    assert (run.size, run.reason) == (10, "quote")
    assert results.excluded[1] == ()
    # Documents keep every word: excluded words still count in the coverage denominator.
    assert results.documents == tuple(documents)


def test_blocks_stop_at_excluded_words() -> None:
    a = Document.from_text('one two three "four five" six seven eight', "a.txt")
    b = Document.from_text("one two three four five six seven eight", "b.txt")
    pair = compare_documents([a, b], ignore_quotes=True).pairs[0]
    assert sorted((m.a, m.size) for m in pair.blocks) == [(0, 3), (5, 3)]
    assert pair.coverage_i == pair.coverage_j == 75.0


def test_masks_differ_between_documents_and_engines() -> None:
    a = Document.from_text('"same quoted words here" tail', "a.txt")
    b = Document.from_text('"same quoted words here" tail', "b.txt")
    for engine in ("shingle", "difflib"):
        results = compare_documents([a, b], ignore_quotes=True, engine=engine)
        assert results.pairs[0].matched_words == 0, engine


# Bibliography --------------------------------------------------------------------------------------------------

ESSAY = " ".join(f"Sentence number {k} of the essay body talks about the topic." for k in range(30))


@pytest.mark.parametrize(
    "heading",
    ["References", "REFERENCES", "Bibliography", "Works Cited", "7. References", "IV. Bibliography", "References:",
     "Références bibliographiques", "Bibliographie", "Referencias", "Literaturverzeichnis", "Bibliografia"],
)  # fmt: skip
def test_bibliography_headings(heading: str) -> None:
    text = f"{ESSAY}\n\n{heading}\n\nSmith, J. (2020). A book. Publisher.\n"
    start = bibliography_start(text)
    assert start is not None
    assert text[start:].startswith(heading)


def test_bibliography_heading_joined_with_the_first_entry() -> None:
    # PDF text: the single line break after the heading was joined.
    for entry in ("[1] Smith, J. A book.", "1. Smith, J. A book.", "Smith, J. (2020). A book."):
        text = f"{ESSAY}\n\nReferences {entry}"
        assert bibliography_start(text) == len(ESSAY) + 2, entry


@pytest.mark.parametrize(
    "text",
    [
        f"{ESSAY}\n\nReferences to the war appear in many letters.",  # prose, not a heading
        f"References\n\n{ESSAY}",  # a title or table of contents at the start
        f"{ESSAY} The references are listed below.",
        ESSAY,
    ],
)
def test_no_bibliography(text: str) -> None:
    assert bibliography_start(text) is None


def test_last_heading_wins() -> None:
    text = f"{ESSAY}\n\nSources\n\nfirst list\n\n{ESSAY}\n\nReferences\n\nSmith, J."
    start = bibliography_start(text)
    assert start is not None and text[start:].startswith("References\n\nSmith")


def test_ignore_bibliography() -> None:
    entry = "Smith, J. (2020). The industrial revolution and the city. Oxford University Press."
    a = Document.from_text(f"{ESSAY}\n\nReferences\n\n{entry}", "a.txt")
    b = Document.from_text(f"Short note.\n\nBibliography\n\n{entry}", "b.txt")
    assert compare_documents([a, b]).pairs[0].matched_words > 10
    results = compare_documents([a, b], ignore_bibliography=True)
    # b's heading is in its first 30%: only a's bibliography is excluded, which is enough to drop the match.
    assert results.pairs[0].matched_words == 0
    assert [len(runs) for runs in results.excluded] == [1, 0]
    assert results.excluded[0][0].reason == "bibliography"
    assert results.options == {"ignore_bibliography": True}


def test_find_exclusions_combines_both() -> None:
    text = f'{ESSAY} "a quote"\n\nReferences\n\nSmith, J. "A title". Publisher.'
    document = Document.from_text(text, "a.txt")
    runs = find_exclusions(document.text, document.spans, quotes=True, bibliography=True)
    assert [run.reason for run in runs] == ["quote", "bibliography"]  # the quote inside the bibliography merged
    assert runs[-1].start + runs[-1].size == len(document.words)


# Reports and exports -------------------------------------------------------------------------------------------


def _results() -> Any:
    documents = [Document.from_text(QUOTED, "essay.txt"), Document.from_text(SOURCE, "source.txt")]
    return compare_documents(documents, ignore_quotes=True)


def test_highlight_greys_excluded_words() -> None:
    document = Document.from_text("one two three four", "a.txt")
    html = highlight(document, [(0, 1, 0)], [Excluded(2, 2, "quote")])
    assert html.startswith('<span class="match"')
    assert (
        '<span class="excluded" style="color: #8c8c8c" title="Quotation: left out of the matching">three four' in html
    )
    assert highlight(document, [(0, 1, 0)]) == highlight(document, [(0, 1, 0)], ())


def test_pages_report_greys_excluded_words() -> None:
    pages = _results().to_html_pages()
    assert 'class="excluded"' in pages["0_1.html"]
    assert "quotations ignored" in pages["_results.html"]


def _embedded(html: str) -> dict[str, Any]:
    match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.DOTALL)
    assert match is not None
    data = json.loads(match.group(1))
    assert isinstance(data, dict)
    return data


def test_single_page_embeds_exclusions_and_the_addon() -> None:
    html = _results().to_html()
    data = _embedded(html)
    assert data["documents"][0]["excluded"] == [[4, 10, "quote"]]
    assert "excluded" not in data["documents"][1]
    assert "greyExcluded" in html and html.count("<script>") == 2
    # Without exclusions the add-on is not included.
    plain = compare_documents([Document.from_text(QUOTED, "a.txt"), Document.from_text(SOURCE, "b.txt")]).to_html()
    assert "greyExcluded" not in plain and plain.count("<script>") == 1


def test_json_export_lists_excluded_words() -> None:
    data = _results().to_dict()
    assert data["options"] == {"ignore_quotes": True}
    first, second = data["documents"]
    assert (first["excluded_words"], first["excluded"]) == (10, [{"start": 4, "size": 10, "reason": "quote"}])
    assert (second["excluded_words"], second["excluded"]) == (0, [])
    assert first["word_count"] == 17


def test_cli_flags(tmp_path: Path) -> None:
    args = parse_args(["docs", "--ignore-quotes", "--ignore-bibliography"])
    assert (args.ignore_quotes, args.ignore_bibliography) == (True, True)
    defaults = parse_args(["docs"])
    assert (defaults.ignore_quotes, defaults.ignore_bibliography) == (False, False)

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "essay.txt").write_text(QUOTED, encoding="utf-8")
    (docs / "source.txt").write_text(SOURCE, encoding="utf-8")
    json_path = tmp_path / "pairs.json"
    argv = [str(docs), "-o", str(tmp_path / "out"), "--json", str(json_path), "--no-open", "--ignore-quotes"]
    assert main(argv) == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["options"] == {"ignore_quotes": True}
    assert data["pairs"][0]["matched_words"] == 0
    html = (tmp_path / "out" / "_results.html").read_text(encoding="utf-8")
    assert "quotations ignored" in html and "greyExcluded" in html
