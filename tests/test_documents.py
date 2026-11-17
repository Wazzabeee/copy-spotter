from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from copy_spotter._documents import Document, find_documents
from copy_spotter._errors import DocumentReadError, UnsupportedFormatError
from copy_spotter.extract import tokenize

from .conftest import PLAGIARISM_DIR, make_docx


@pytest.mark.parametrize("path", sorted(PLAGIARISM_DIR.iterdir()), ids=lambda p: p.suffix)
def test_from_bytes_equals_from_path(path: Path) -> None:
    from_path = Document.from_path(path)
    from_bytes = Document.from_bytes(path.read_bytes(), path.name)
    assert from_bytes == from_path
    assert from_path.name == path.name
    assert len(from_path.words) == len(from_path.spans) > 50


def test_from_text_cleans_and_tokenizes() -> None:
    document = Document.from_text("Hello,  World!\r\n\r\n\r\nIt's 2024.  ", "a.txt")
    assert document.name == "a.txt"
    assert document.text == "Hello,  World!\n\nIt's 2024."
    assert document.words == ("hello", "world", "it", "s", "2024")
    assert [document.text[a:b] for a, b in document.spans] == ["Hello", "World", "It", "s", "2024"]


def test_from_text_join_lines() -> None:
    assert Document.from_text("one\ntwo", "a").text == "one\ntwo"
    assert Document.from_text("one\ntwo", "a", join_lines=True).text == "one two"


def test_documents_are_immutable_and_hashable() -> None:
    document = Document.from_text("some text", "a.txt")
    assert hash(document) == hash(Document.from_text("some text", "a.txt"))
    with pytest.raises(AttributeError):
        document.name = "b.txt"  # type: ignore[misc]


@pytest.mark.parametrize("fmt", ["txt", ".txt", "TXT", ".TxT"])
def test_from_bytes_format_overrides_name(fmt: str) -> None:
    document = Document.from_bytes(b"Plain words", "upload", format=fmt)
    assert document.words == ("plain", "words")


def test_from_bytes_docx(tmp_path: Path) -> None:
    data = make_docx(tmp_path / "a.docx", ["Introduction", "Machine learning."]).read_bytes()
    assert Document.from_bytes(data, "a.docx").text == "Introduction\nMachine learning."


def test_from_bytes_txt_encodings() -> None:
    assert Document.from_bytes("café".encode("latin-1"), "a.txt").words == ("café",)
    assert Document.from_bytes("﻿hello".encode(), "a.txt").text == "hello"


def test_unsupported_format() -> None:
    with pytest.raises(UnsupportedFormatError, match=r"image\.png.*\.pdf, \.docx, \.odt, \.txt"):
        Document.from_bytes(b"\x89PNG", "image.png")
    with pytest.raises(UnsupportedFormatError):
        Document.from_bytes(b"text", "notes.txt", format="rtf")
    with pytest.raises(ValueError):  # UnsupportedFormatError is a ValueError
        Document.from_bytes(b"text", "no_extension")


@pytest.mark.parametrize("name", ["broken.docx", "broken.odt", "broken.pdf"])
def test_corrupt_file_raises_document_read_error(name: str) -> None:
    with pytest.raises(DocumentReadError, match=f"Could not read {name}") as info:
        Document.from_bytes(b"not a real file", name)
    assert info.value.__cause__ is not None


def test_from_path_name_and_errors(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("Some notes")
    assert Document.from_path(path, name="sub/notes.txt").name == "sub/notes.txt"
    assert Document.from_path(str(path)).words == tuple(tokenize("Some notes"))
    with pytest.raises(FileNotFoundError):
        Document.from_path(tmp_path / "missing.txt")
    with pytest.raises(FileNotFoundError):
        Document.from_path(tmp_path)


def test_find_documents(tmp_path: Path) -> None:
    for name in ("b.txt", "a.PDF", ".hidden.txt", "image.png", "sub/c.docx", "out/d.txt"):
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_text("x")
    names = [p.relative_to(tmp_path).as_posix() for p in find_documents(tmp_path)]
    assert names == ["a.PDF", "b.txt"]
    recursive = find_documents(tmp_path, recursive=True, exclude=tmp_path / "out")
    assert [p.relative_to(tmp_path).as_posix() for p in recursive] == ["a.PDF", "b.txt", "sub/c.docx"]


def test_parsers_are_imported_lazily() -> None:
    code = (
        "import sys, copy_spotter._documents, copy_spotter.extract\n"
        "heavy = [m for m in sys.modules if m.split('.')[0] in ('pdfminer', 'odf')]\n"
        "print(heavy)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"
