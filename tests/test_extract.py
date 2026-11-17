from __future__ import annotations

from pathlib import Path

import pytest
from odf.opendocument import OpenDocumentText
from odf.text import H, P

from copy_spotter.extract import UnsupportedFileError, extract_text, extract_words, is_supported, tokenize

from .conftest import PLAGIARISM_DIR, make_docx


@pytest.mark.parametrize("path", sorted(PLAGIARISM_DIR.iterdir()), ids=lambda p: p.suffix)
def test_sample_files_have_words(path: Path) -> None:
    words = extract_words(path)
    assert len(words) > 50
    assert "healthcare" in words


def test_tokenize_lowercases_and_drops_punctuation() -> None:
    assert tokenize("Hello, World! It's 2024.") == ["hello", "world", "it", "s", "2024"]


def test_docx_paragraphs_are_not_glued(tmp_path: Path) -> None:
    docx = make_docx(tmp_path / "a.docx", ["Introduction", "Machine learning"])
    assert extract_words(docx) == ["introduction", "machine", "learning"]


def test_odt_keeps_headings_and_paragraph_breaks(tmp_path: Path) -> None:
    document = OpenDocumentText()
    document.text.addElement(H(outlinelevel=1, text="Introduction"))
    document.text.addElement(P(text="Machine learning"))
    document.text.addElement(P(text="Deep learning"))
    path = tmp_path / "a.odt"
    document.save(str(path))
    assert extract_words(path) == ["introduction", "machine", "learning", "deep", "learning"]


def test_txt_non_utf8_encoding(tmp_path: Path) -> None:
    path = tmp_path / "latin1.txt"
    path.write_bytes("café crème".encode("latin-1"))
    assert extract_words(path) == ["café", "crème"]


def test_txt_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "bom.txt"
    path.write_bytes("﻿hello".encode())
    assert extract_text(path) == "hello"


def test_empty_file_returns_no_words(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.touch()
    assert extract_words(path) == []


def test_uppercase_extension(tmp_path: Path) -> None:
    path = tmp_path / "LOUD.TXT"
    path.write_text("Some text")
    assert is_supported(path)
    assert extract_words(path) == ["some", "text"]


def test_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG")
    assert not is_supported(path)
    with pytest.raises(UnsupportedFileError):
        extract_text(path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_text(tmp_path / "missing.txt")
