from __future__ import annotations

import gc
import json
import pickle
import random
import shutil
from itertools import combinations
from pathlib import Path

import pytest

from copy_spotter._compare import Pair, compare_documents, compare_pair
from copy_spotter._documents import Document, Skipped, load_directory
from copy_spotter._progress import Progress
from copy_spotter._report import RESULTS_FILENAME
from copy_spotter.similarity import ENGINES, Engine, Match

from .conftest import PLAGIARISM_DIR, make_docx, make_pair, make_results

SHORT = "the cat sat on the mat"
LONG = "a story begins here and then the cat sat on the mat while the dog slept by the door all day long"


def _docs(*texts: str) -> list[Document]:
    return [Document.from_text(text, f"{k}.txt") for k, text in enumerate(texts)]


def test_default_block_size_leaves_short_common_phrases_out() -> None:
    a = "the cat sat on the mat and then it slept"
    b = "and then the cat sat on the mat today"
    results = compare_documents(_docs(a, b))
    assert results.block_size == 4
    assert [block.size for block in results.pairs[0].blocks] == [6]  # "the cat sat on the mat"
    two = compare_documents(_docs(a, b), block_size=2)
    assert [block.size for block in two.pairs[0].blocks] == [6, 2]  # "and then" also matches with 2


def test_compare_documents_pairs_in_combinations_order() -> None:
    documents = load_directory(PLAGIARISM_DIR)
    results = compare_documents(documents, block_size=3, engine="difflib")
    assert results.documents == tuple(documents)
    assert (results.block_size, results.engine) == (3, "difflib")
    assert [(p.i, p.j) for p in results.pairs] == list(combinations(range(len(documents)), 2))
    for pair in results.pairs:
        words_i, words_j = list(documents[pair.i].words), list(documents[pair.j].words)
        assert pair == compare_pair(pair.i, pair.j, words_i, words_j, block_size=3, engine="difflib")


def test_pair_scores_and_matched_words() -> None:
    pair = compare_documents(_docs(SHORT, LONG)).pairs[0]
    assert (pair.i, pair.j, pair.coverage_i) == (0, 1, 100.0)
    assert pair.coverage_j < 50
    assert pair.matched_words == 6
    assert pair.blocks == (Match(0, 6, 6),)
    assert pair.scores() == (pair.coverage_i, pair.coverage_j)
    assert pair.scores("ratio") == (pair.ratio, pair.ratio)


def test_pair_is_keyword_only_and_picklable() -> None:
    with pytest.raises(TypeError):
        Pair(0, 1, 1.0, 1.0, 1.0, ())  # type: ignore[misc]
    pair = make_pair(0, 1, 10.0, [Match(0, 0, 2)], 20.0, 30.0)
    assert pickle.loads(pickle.dumps(pair)) == pair


def test_fewer_than_two_documents_give_no_pairs() -> None:
    assert compare_documents([]).pairs == ()
    assert compare_documents(_docs("alone")).pairs == ()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"block_size": 0}, "block_size"), ({"engine": "fuzzy"}, "engine")],
)
def test_compare_documents_rejects_invalid_options(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        compare_documents(_docs("a b", "a b"), **kwargs)  # type: ignore[arg-type]


def test_compare_documents_rejects_duplicate_names() -> None:
    documents = [Document.from_text("a b", "same.txt"), Document.from_text("a b", "same.txt")]
    with pytest.raises(ValueError, match=r"unique.*same\.txt"):
        compare_documents(documents)


def test_progress_events() -> None:
    events: list[Progress] = []
    compare_documents(_docs("a b", "b c", "c d"), progress=events.append)
    assert events == [Progress("compare", done, 3) for done in range(4)]


def test_exception_in_progress_callback_aborts() -> None:
    def stop(event: Progress) -> None:
        if event.done == 1:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        compare_documents(_docs("a b", "b c", "c d"), progress=stop)


def _fuzz_documents(seed: int) -> list[Document]:
    """Documents over small or large vocabularies, empty or short ones, with passages copied between them."""
    rng = random.Random(seed)
    vocabulary = [f"w{k}" for k in range(rng.choice([2, 3, 20, 200]))]
    texts: list[list[str]] = []
    for _ in range(rng.randint(2, 6)):
        words = rng.choices(vocabulary, k=rng.choice([0, 1, 2, 10, 150, 400]))
        if texts and len(words) > 20 and len(source := rng.choice(texts)) > 30:
            a = rng.randrange(len(source) - 20)
            words[5 : 5 + 20] = source[a : a + 20]
        texts.append(words)
    return _docs(*(" ".join(words) for words in texts))


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("seed", range(25))
def test_compare_documents_matches_compare_pair_on_every_pair(seed: int, engine: Engine) -> None:
    # compare_documents shares one index across the corpus; compare_pair compares each pair on its own.
    documents = _fuzz_documents(seed)
    words = [list(document.words) for document in documents]
    indexes = list(combinations(range(len(documents)), 2))
    for block_size in (1, 2, 3, 5):
        events: list[Progress] = []
        results = compare_documents(documents, block_size=block_size, engine=engine, progress=events.append)
        expected = [compare_pair(i, j, words[i], words[j], block_size=block_size, engine=engine) for i, j in indexes]
        assert list(results.pairs) == expected
        assert events == [Progress("compare", done, len(indexes)) for done in range(len(indexes) + 1)]


@pytest.mark.parametrize("engine", ENGINES)
def test_exception_in_progress_callback_aborts_any_engine(engine: Engine) -> None:
    seen: list[int] = []

    def stop(event: Progress) -> None:
        seen.append(event.done)
        if event.done == 2:
            raise KeyboardInterrupt

    gc_enabled = gc.isenabled()
    with pytest.raises(KeyboardInterrupt):
        compare_documents(_docs("a b c", "b c d", "c d e", "d e f"), engine=engine, progress=stop)
    assert seen == [0, 1, 2]
    assert gc.isenabled() == gc_enabled


def test_ranked_sorts_by_highest_score_with_ties_in_order() -> None:
    pairs = [
        make_pair(0, 1, 40.0, [], 40.0, 40.0),
        make_pair(0, 2, 18.0, [], 10.0, 100.0),
        make_pair(1, 2, 40.0, [], 1.0, 40.0),
    ]
    results = make_results(["a", "b", "c"], pairs)
    assert [(p.i, p.j) for p in results.ranked()] == [(0, 2), (0, 1), (1, 2)]
    assert [(p.i, p.j) for p in results.ranked("ratio")] == [(0, 1), (1, 2), (0, 2)]
    with pytest.raises(ValueError, match="score"):
        results.ranked("words")  # type: ignore[arg-type]


def test_pair_lookup_by_index_or_name() -> None:
    results = compare_documents(_docs("a b", "b c", "c d", "d e"))
    assert results.pair(1, 3) is results.pairs[4]
    assert results.pair("3.txt", "1.txt") is results.pairs[4]
    assert results.pair(0, "1.txt") is results.pairs[0]
    with pytest.raises(ValueError):
        results.pair(2, "2.txt")
    with pytest.raises(KeyError):
        results.pair("0.txt", "missing.txt")
    with pytest.raises(KeyError):
        results.pair(0, 4)
    partial = make_results(["a", "b", "c"], [make_pair(1, 2, 5.0, [], 5.0, 5.0)])
    assert partial.pair("c", "b") is partial.pairs[0]
    with pytest.raises(KeyError):
        partial.pair("a", "b")


def test_exports_are_sorted_and_validated() -> None:
    results = compare_documents(_docs(SHORT, LONG, "nothing in common"))
    data = results.to_dict()
    assert json.loads(results.to_json()) == data
    assert [(p["index_1"], p["index_2"]) for p in data["pairs"]] == [(p.i, p.j) for p in results.ranked()]
    assert results.to_dict(score="ratio", thresholds=(1, 2, 3))["thresholds"] == [1.0, 2.0, 3.0]
    assert results.to_csv().splitlines()[1].startswith("0.txt,1.txt,100.0,")
    with pytest.raises(ValueError):
        results.to_json(thresholds=(3, 2, 1))
    with pytest.raises(ValueError):
        results.to_csv(score="best")  # type: ignore[arg-type]


def test_html_meta_defaults_to_a_summary() -> None:
    results = compare_documents(_docs(SHORT, LONG), block_size=3)
    html = results.to_html()
    assert "2 documents, minimum block size 3, shingle engine, coverage score, copy-spotter" in html
    assert "my run" in results.to_html(meta="my run", score="ratio")
    with pytest.raises(ValueError):
        results.to_html(thresholds=(1, 2))


def test_html_pages() -> None:
    results = compare_documents(_docs(SHORT, LONG, "x y"))
    pages = results.to_html_pages(meta="")
    assert list(pages) == [RESULTS_FILENAME, "0_1.html", "0_2.html", "1_2.html"]
    assert all(page.startswith("<!DOCTYPE html>") for page in pages.values())


@pytest.mark.parametrize(
    ("report", "files"), [("single", [RESULTS_FILENAME]), ("pages", [RESULTS_FILENAME, "0_1.html"])]
)
def test_save(tmp_path: Path, report: str, files: list[str]) -> None:
    results = compare_documents(_docs(SHORT, LONG))
    path = results.save(tmp_path / "new" / "dir", report=report)  # type: ignore[arg-type]
    assert path == tmp_path / "new" / "dir" / RESULTS_FILENAME
    assert sorted(p.name for p in path.parent.iterdir()) == sorted(files)
    with pytest.raises(ValueError, match="report"):
        results.save(tmp_path, report="zip")  # type: ignore[arg-type]


def test_load_directory(tmp_path: Path) -> None:
    root = tmp_path / "in"
    shutil.copytree(PLAGIARISM_DIR, root / "sub")
    (root / "b.txt").write_text("Some words")
    (root / "empty.txt").touch()
    (root / "broken.docx").write_bytes(b"not a zip")
    (root / "out").mkdir()
    make_docx(root / "out" / "a.docx", ["excluded"])
    skipped: list[Skipped] = []
    events: list[Progress] = []

    flat = load_directory(root, on_skip=skipped.append, progress=events.append)
    assert [d.name for d in flat] == ["b.txt"]
    assert [(s.name, s.reason) for s in skipped] == [("broken.docx", "unreadable"), ("empty.txt", "empty")]
    assert str(skipped[0].error.__cause__) == "File is not a zip file"  # type: ignore[union-attr]
    assert skipped[1].error is None
    assert events == [Progress("read", done, 3) for done in range(4)]

    deep = load_directory(root, recursive=True, exclude=root / "out")
    assert [d.name for d in deep] == ["b.txt"] + [f"sub/{p.name}" for p in sorted(PLAGIARISM_DIR.iterdir())]
    assert load_directory(str(root), recursive=True)[0].name == "b.txt"


def test_load_directory_requires_a_directory(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        load_directory(tmp_path / "missing")
