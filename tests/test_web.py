"""The web app's Python glue (web/copy_spotter_web.py) gives the same results as the library and the CLI."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from copy_spotter import compare_documents, load_directory

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "pdf" / "plagiarism"


@pytest.fixture(scope="module")
def web() -> ModuleType:
    spec = importlib.util.spec_from_file_location("copy_spotter_web", ROOT / "web" / "copy_spotter_web.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sample_files() -> list[tuple[str, bytes]]:
    return [(path.name, path.read_bytes()) for path in sorted(SAMPLES.iterdir(), reverse=True)]


@pytest.mark.parametrize(
    ("block_size", "engine", "score", "thresholds"),
    [(2, "shingle", "coverage", (5.0, 10.0, 15.0)), (3, "difflib", "ratio", (10.0, 20.0, 30.0))],
)
def test_matches_library(
    web: ModuleType, block_size: int, engine: str, score: str, thresholds: tuple[float, float, float]
) -> None:
    out = web.analyze(sample_files(), block_size=block_size, engine=engine, score=score, thresholds=thresholds)
    expected = compare_documents(load_directory(SAMPLES), block_size=block_size, engine=engine)
    assert out["names"] == sorted(path.name for path in SAMPLES.iterdir())
    assert out["skipped"] == []
    assert out["json"] == expected.to_json(score=score, thresholds=thresholds)
    assert out["csv"] == expected.to_csv(score=score)
    assert out["html"] == expected.to_html(score=score, thresholds=thresholds)


def test_names_sorted_like_load_directory(web: ModuleType, tmp_path: Path) -> None:
    names = ["b.txt", "a/z.txt", "a.txt", "a-b.txt"]
    for name in names:
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_text("one two three", encoding="utf-8")
    expected = [document.name for document in load_directory(tmp_path, recursive=True)]
    assert web.analyze([(name, b"one two three") for name in names])["names"] == expected


def test_skips_empty_and_unreadable(web: ModuleType) -> None:
    files = [("empty.txt", b"  \n"), ("broken.pdf", b"not a pdf"), ("ok.txt", b"some words here")]
    out = web.analyze(files)
    assert out["error"] == "Need at least two readable documents, found 1."
    assert [(s["name"], s["reason"]) for s in out["skipped"]] == [("broken.pdf", "unreadable"), ("empty.txt", "empty")]
    assert out["skipped"][0]["detail"]


def test_invalid_option_is_an_error(web: ModuleType) -> None:
    out = web.analyze(sample_files(), thresholds=(15, 10, 5))
    assert "thresholds" in out["error"]
    assert web.analyze(sample_files(), block_size=0)["error"]


def test_progress(web: ModuleType) -> None:
    events: list[tuple[str, int, int]] = []
    web.analyze(sample_files(), progress=lambda *event: events.append(event))
    assert [e for e in events if e[0] == "read"] == [("read", k, 4) for k in range(5)]
    compare = [e for e in events if e[0] == "compare"]
    assert compare[0] == ("compare", 0, 6)
    assert compare[-1] == ("compare", 6, 6)
