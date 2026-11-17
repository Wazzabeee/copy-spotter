from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from copy_spotter._documents import Document
from copy_spotter.extract import tokenize_with_offsets

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PLAGIARISM_DIR = DATA_DIR / "pdf" / "plagiarism"

_DOCX_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/>'
    "</Types>"
)


def make_docx(path: Path, paragraphs: list[str]) -> Path:
    """Write a minimal DOCX file with one paragraph per string."""
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", _DOCX_CONTENT_TYPES)
        archive.writestr("word/document.xml", document)
    return path


def make_document(text: str, name: str = "doc.txt") -> Document:
    """Return a document whose display text is exactly ``text`` (no cleanup)."""
    words, spans = tokenize_with_offsets(text)
    return Document(name, text, tuple(words), tuple(spans))


@pytest.fixture
def plagiarism_dir() -> Path:
    return PLAGIARISM_DIR
