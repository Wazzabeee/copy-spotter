from __future__ import annotations

import inspect
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import copy_spotter

from .conftest import DATA_DIR

README = DATA_DIR.parent / "README.md"


def test_public_names() -> None:
    assert sorted(copy_spotter.__all__) == [
        "CopySpotterError",
        "DEFAULT_THRESHOLDS",
        "Document",
        "DocumentReadError",
        "ENGINES",
        "Engine",
        "Match",
        "Pair",
        "Progress",
        "ReportLayout",
        "Results",
        "SUPPORTED_FORMATS",
        "ScoreMode",
        "Skipped",
        "UnsupportedFormatError",
        "__version__",
        "compare_documents",
        "find_documents",
        "load_directory",
    ]
    for name in copy_spotter.__all__:
        assert hasattr(copy_spotter, name), name


def test_public_values() -> None:
    assert copy_spotter.SUPPORTED_FORMATS == ("pdf", "docx", "odt", "txt")
    assert copy_spotter.ENGINES == ("shingle", "difflib")
    assert copy_spotter.DEFAULT_THRESHOLDS == (5.0, 10.0, 15.0)
    assert isinstance(copy_spotter.__version__, str)


def test_public_classes_and_functions_are_documented() -> None:
    for name in copy_spotter.__all__:
        value = getattr(copy_spotter, name)
        if inspect.isclass(value) or inspect.isfunction(value):
            assert value.__doc__, name


def test_import_does_not_load_heavy_modules() -> None:
    code = (
        "import sys\n"
        "import copy_spotter\n"
        "heavy = ('pdfminer', 'odf', 'tqdm', 'webbrowser')\n"
        "print(sorted({m.split('.')[0] for m in sys.modules if m.split('.')[0] in heavy}))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


def test_readme_example_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    section = README.read_text(encoding="utf-8").split("## Python API", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```python\n(.*?)```", section, re.DOTALL)
    assert blocks
    shutil.copytree(DATA_DIR / "pdf" / "plagiarism", tmp_path / "data" / "pdf" / "plagiarism")
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {}
    for block in blocks:
        exec(compile(block, str(README), "exec"), namespace)
    assert len(capsys.readouterr().out.splitlines()) == 3
    assert (tmp_path / "results" / "api" / "_results.html").is_file()
    assert isinstance(namespace["html"], str)
    assert isinstance(namespace["results"], copy_spotter.Results)
