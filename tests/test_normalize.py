from __future__ import annotations

import json
from pathlib import Path

import pytest

from copy_spotter import (
    NORMALIZATIONS,
    STOPWORD_LANGUAGES,
    Document,
    compare_documents,
    stopword_list,
)
from copy_spotter._normalize import check_normalize, fold_accents, normalize_document
from copy_spotter._report import highlight
from copy_spotter.cli import main, parse_args

FRENCH = "L'élève a écrit une très belle dissertation sur la révolution française."
PLAIN = "L eleve a ecrit une tres belle dissertation sur la revolution francaise."


def test_fold_accents() -> None:
    assert fold_accents("élève") == "eleve"
    assert fold_accents("ÇA") == "ca"
    assert fold_accents("ﬁnal") == "final"  # ligature from PDF text
    assert fold_accents("x²") == "x2"
    assert fold_accents("straße") == "straße"  # not a diacritic


def test_check_normalize() -> None:
    assert NORMALIZATIONS == ("accents",)
    assert check_normalize(["accents", "accents"]) == ("accents",)
    assert check_normalize([]) == ()
    with pytest.raises(ValueError, match="'case'"):
        check_normalize(["case"])


def test_stopword_lists() -> None:
    assert STOPWORD_LANGUAGES == ("en", "fr", "es", "de", "it", "pt")
    english = stopword_list("en")
    assert {"the", "and", "of"} <= english
    assert "healthcare" not in english
    assert stopword_list("EN", " fr") == english | stopword_list("fr")
    for language in STOPWORD_LANGUAGES:
        words = stopword_list(language)
        assert len(words) > 50
        assert all(word == word.lower() and word.isalpha() for word in words), language
    with pytest.raises(ValueError, match="'xx'"):
        stopword_list("xx")


def test_normalize_document_keeps_text_and_spans() -> None:
    document = Document.from_text("The Élève and the teacher", "a.txt")
    normalized = normalize_document(document, accents=True, stopwords=frozenset({"the", "and"}))
    assert normalized.text == document.text
    assert normalized.words == ("eleve", "teacher")
    assert [normalized.text[a:b] for a, b in normalized.spans] == ["Élève", "teacher"]
    assert normalize_document(document, accents=False, stopwords=frozenset()) is document


def test_stopwords_are_folded_like_the_words() -> None:
    document = Document.from_text("très bien", "a.txt")
    assert normalize_document(document, accents=True, stopwords=frozenset({"très"})).words == ("bien",)
    assert normalize_document(document, accents=False, stopwords=frozenset({"tres"})).words == ("très", "bien")


def test_accents_option_matches_unaccented_copies() -> None:
    documents = [Document.from_text(FRENCH, "a.txt"), Document.from_text(PLAIN, "b.txt")]
    assert compare_documents(documents).pairs[0].coverage_i < 50
    results = compare_documents(documents, normalize=["accents"])
    assert results.pairs[0].coverage_i == results.pairs[0].coverage_j == 100.0
    assert results.options == {"normalize": ["accents"]}
    # The report shows the original, accented text.
    assert results.documents[0].text == FRENCH


def test_stopwords_option_bridges_changed_function_words() -> None:
    a = Document.from_text("the cat sat on the mat near the door", "a.txt")
    b = Document.from_text("a cat sat in a mat near a door", "b.txt")
    assert compare_documents([a, b], block_size=3).pairs[0].blocks == ()
    results = compare_documents([a, b], block_size=3, stopwords=stopword_list("en"))
    pair = results.pairs[0]
    assert [document.words for document in results.documents] == [("cat", "sat", "mat", "near", "door")] * 2
    assert (pair.coverage_i, pair.coverage_j, len(pair.blocks)) == (100.0, 100.0, 1)
    assert results.options == {"stopwords": len(stopword_list("en"))}
    # The block is highlighted from its first to its last word, stopwords included.
    html = highlight(results.documents[0], [(0, 5, 0)])
    assert ">cat sat on the mat near the door</span>" in html


def test_no_options_gives_the_same_results() -> None:
    documents = [Document.from_text(FRENCH, "a.txt"), Document.from_text(PLAIN, "b.txt")]
    default = compare_documents(documents)
    assert compare_documents(documents, normalize=[], stopwords=[]) == default
    assert default.options == {}
    assert default.documents == tuple(documents)
    assert "options" not in default.to_dict()


def test_options_reach_json_and_meta() -> None:
    documents = [Document.from_text(FRENCH, "a.txt"), Document.from_text(PLAIN, "b.txt")]
    results = compare_documents(documents, normalize=["accents"], stopwords=["la", "sur"])
    data = results.to_dict()
    assert data["options"] == {"normalize": ["accents"], "stopwords": 2}
    assert list(data)[:7] == [
        "version",
        "copy_spotter_version",
        "engine",
        "score_mode",
        "block_size",
        "thresholds",
        "options",
    ]
    assert [d["word_count"] for d in data["documents"]] == [10, 10]
    assert "accents folded, 2 stopwords ignored" in results.to_html()


def test_invalid_normalization() -> None:
    with pytest.raises(ValueError, match="normalize"):
        compare_documents([], normalize=["case"])  # type: ignore[list-item]


def test_cli_parsing(tmp_path: Path) -> None:
    args = parse_args(["docs", "--normalize", "accents", "--stopwords", "en,fr"])
    assert args.normalize == ["accents"]
    assert args.stopwords == stopword_list("en", "fr")
    words = tmp_path / "words.txt"
    words.write_text("Foo\nbar, baz\n", encoding="utf-8")
    assert parse_args(["docs", "--stopwords", str(words)]).stopwords == {"foo", "bar", "baz"}
    defaults = parse_args(["docs"])
    assert (defaults.normalize, defaults.stopwords) == ([], None)


@pytest.mark.parametrize("argv", [["--normalize", "case"], ["--stopwords", "klingon"]])
def test_cli_invalid_values(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["docs", *argv])


def test_cli_run_with_normalization(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text(FRENCH, encoding="utf-8")
    (docs / "b.txt").write_text(PLAIN, encoding="utf-8")
    json_path = tmp_path / "pairs.json"
    argv = [str(docs), "-o", str(tmp_path / "out"), "--json", str(json_path), "--no-open"]
    assert main([*argv, "--normalize", "accents", "--stopwords", "fr"]) == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["options"] == {"normalize": ["accents"], "stopwords": len(stopword_list("fr"))}
    assert data["pairs"][0]["coverage_1"] == 100.0
    html = (tmp_path / "out" / "_results.html").read_text(encoding="utf-8")
    assert "accents folded" in html and "stopwords ignored" in html
