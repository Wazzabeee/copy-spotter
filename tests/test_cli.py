from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from copy_spotter import __version__
from copy_spotter.cli import main, parse_args


def _copy_samples(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


def test_full_run_on_sample_files(plagiarism_dir: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    assert main([str(plagiarism_dir), "-o", str(out_dir), "--no-open"]) == 0
    pages = sorted(p.name for p in out_dir.iterdir())
    # 4 documents: 6 unordered pairs plus the summary page.
    assert len(pages) == 7
    assert "_results.html" in pages


def test_out_dir_is_created(plagiarism_dir: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "does" / "not" / "exist"
    assert main([str(plagiarism_dir), "-o", str(out_dir), "--no-open"]) == 0
    assert (out_dir / "_results.html").is_file()


def test_default_out_dir_is_in_cwd(plagiarism_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    assert main([str(plagiarism_dir), "--no-open"]) == 0
    assert len(list((workdir / "results").glob("*/_results.html"))) == 1
    assert not (tmp_path / "results").exists()


def test_empty_and_unreadable_files_are_skipped(
    plagiarism_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    in_dir = _copy_samples(plagiarism_dir, tmp_path / "in")
    (in_dir / "empty.txt").touch()
    (in_dir / "broken.docx").write_bytes(b"not a zip")
    (in_dir / "notes.md").write_text("ignored")
    assert main([str(in_dir), "-o", str(tmp_path / "out"), "--no-open"]) == 0
    err = capsys.readouterr().err
    assert "skipping empty.txt" in err
    assert "skipping broken.docx" in err
    assert "notes.md" not in err


def test_fewer_than_two_documents(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "only.txt").write_text("alone")
    assert main([str(tmp_path), "--no-open"]) == 1
    assert "at least two" in capsys.readouterr().err


def test_missing_input_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "missing"), "--no-open"]) == 1
    assert "not found" in capsys.readouterr().err


def test_recursive_skips_output_dir(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    (in_dir / "sub").mkdir(parents=True)
    (in_dir / "a.txt").write_text("the quick brown fox")
    (in_dir / "sub" / "b.txt").write_text("the quick brown dog")
    out_dir = in_dir / "results"
    assert main([str(in_dir), "-r", "-o", str(out_dir), "--no-open"]) == 0
    # A second run must not pick up the HTML pages or anything else in the output directory.
    (out_dir / "c.txt").write_text("should be ignored")
    assert main([str(in_dir), "-r", "-o", str(out_dir), "--no-open"]) == 0
    assert "c.txt" not in (out_dir / "_results.html").read_text()
    assert "sub/b.txt" in (out_dir / "_results.html").read_text()


def test_legacy_flag_spellings() -> None:
    args = parse_args(["in", "--out_dir", "out", "--block_size", "5"])
    assert args.out_dir == Path("out")
    assert args.block_size == 5


def test_invalid_block_size() -> None:
    with pytest.raises(SystemExit):
        parse_args(["in", "-s", "0"])


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out
